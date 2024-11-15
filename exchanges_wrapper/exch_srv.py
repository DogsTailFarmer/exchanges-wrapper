#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import grpclib.exceptions

from exchanges_wrapper import __version__ as VER_EW
from crypto_ws_api import __version__ as VER_CW
import time
import weakref
import gc
import traceback
import asyncio
import functools
import ujson as json
import logging.handlers
from decimal import Decimal

import exchanges_wrapper.martin as mr
from exchanges_wrapper import WORK_PATH, LOG_FILE, errors, Server, Status, GRPCError, graceful_exit
from exchanges_wrapper.client import Client
from exchanges_wrapper.definitions import Side, OrderType, TimeInForce, ResponseType
from exchanges_wrapper.lib import (
    OrderTradesEvent,
    get_account,
    REST_RATE_LIMIT_INTERVAL,
    FILTER_TYPE_MAP,
)
from exchanges_wrapper.errors import ExchangeError
#
HEARTBEAT = 1  # Sec
MAX_QUEUE_SIZE = 100
#
logger = logging.getLogger(__name__)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=10)
fh.setFormatter(formatter)
fh.setLevel(logging.DEBUG)
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
sh.setLevel(logging.INFO)
#
root_logger = logging.getLogger()
root_logger.setLevel(min([fh.level, sh.level]))
root_logger.addHandler(fh)
root_logger.addHandler(sh)

logging.basicConfig()
logging.getLogger('hpack').setLevel(logging.INFO)


class OpenClient:
    open_clients = []

    def __init__(self, _account_name: str):
        if account := get_account(_account_name):
            self.name = _account_name
            self.real_market = not account['test_net']
            self.client = Client(account)
            self.ts_rlc = time.time()
            OpenClient.open_clients.append(self)
        else:
            raise UserWarning(f"Account {_account_name} not registered into {WORK_PATH}/config/exch_srv_cfg.toml")

    @classmethod
    def get_id(cls, _account_name):
        return next(
            (
                id(client)
                for client in cls.open_clients
                if client.name == _account_name
            ),
            0,
        )

    @classmethod
    def get_client(cls, _id):
        res = next((client for client in cls.open_clients if id(client) == _id), None)
        if res is None:
            logger.warning(f"No client exist: {_id}")
            raise GRPCError(status=Status.UNAVAILABLE, message="No client exist")
        return res

    @classmethod
    def remove_client(cls, _account_name):
        cls.open_clients[:] = [i for i in cls.open_clients if i.name != _account_name]


# noinspection PyPep8Naming,PyMethodMayBeStatic
class Martin(mr.MartinBase):
    rate_limit_reached_time = None
    rate_limiter = None

    async def rate_limit_control(self, exchange, ts_rlc, _call_from='default'):
        if exchange == 'bitfinex':
            rate_limit_interval = REST_RATE_LIMIT_INTERVAL.get(exchange, {}).get(_call_from, 0)
            ts_diff = time.time() - ts_rlc
            if ts_diff < rate_limit_interval:
                sleep_duration = rate_limit_interval - ts_diff
                await asyncio.sleep(sleep_duration)

    async def open_client_connection(self, request: mr.OpenClientConnectionRequest) -> mr.OpenClientConnectionId:
        logger.info(f"OpenClientConnection start trade: {request.account_name}:{request.trade_id}")
        client_id = OpenClient.get_id(request.account_name)
        if client_id:
            logger.debug(f"OpenClientConnection: {request.account_name}:{request.trade_id}:{client_id}")
            open_client = OpenClient.get_client(client_id)
            open_client.client.http.rate_limit_reached = False
        else:
            logger.debug(f"OpenClientConnection: {request.account_name}:{request.trade_id}: set new client_id")
            try:
                open_client = OpenClient(request.account_name)
                client_id = id(open_client)
                if open_client.client.master_name == 'Huobi':
                    # For HuobiPro get master account uid and account_id
                    main_account = get_account(open_client.client.master_name)
                    main_client = Client(main_account)
                    await asyncio.wait_for(main_client.set_htx_ids(), timeout=HEARTBEAT * 60)
                    if main_client.account_uid and main_client.account_id:
                        open_client.client.main_account_uid = main_client.account_uid
                        open_client.client.main_account_id = main_client.account_id
                        logger.info(f"Huobi UID: {main_client.account_uid} and account ID: {main_client.account_id}")
                    else:
                        logger.warning("No account IDs were received for the Huobi master account")
                    await main_client.close()
            except UserWarning as ex:
                print(f"OpenClientConnection: {ex}")
                raise GRPCError(status=Status.FAILED_PRECONDITION, message=str(ex))

        try:
            await asyncio.wait_for(open_client.client.load(request.symbol), timeout=HEARTBEAT * 60)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except asyncio.exceptions.TimeoutError:
            await OpenClient.get_client(client_id).client.session.close()
            OpenClient.remove_client(request.account_name)
            raise GRPCError(status=Status.UNAVAILABLE, message=f"'{open_client.name}' timeout error")
        except Exception as ex:
            logger.warning(f"OpenClientConnection for '{open_client.name}' exception: {ex}")
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
            raise GRPCError(status=Status.RESOURCE_EXHAUSTED, message=str(ex))

        # Set rate_limiter
        Martin.rate_limiter = max(Martin.rate_limiter or 0, request.rate_limiter)
        return mr.OpenClientConnectionId(
            client_id=client_id,
            srv_version=f"{VER_CW}:{VER_EW}",
            exchange=open_client.client.exchange,
            real_market=open_client.real_market
        )

    async def reset_rate_limit(self, request: mr.OpenClientConnectionId) -> mr.SimpleResponse:
        Martin.rate_limiter = max(Martin.rate_limiter or 0, request.rate_limiter)
        _success = False
        client = OpenClient.get_client(request.client_id).client
        if Martin.rate_limit_reached_time:
            if time.time() - Martin.rate_limit_reached_time > 30:
                client.http.rate_limit_reached = False
                Martin.rate_limit_reached_time = None
                logger.info("RateLimit error clear, trying one else time")
                _success = True
        elif client.http.rate_limit_reached:
            Martin.rate_limit_reached_time = time.time()
        return mr.SimpleResponse(success=_success)

    async def send_request(self, client_method_name, request, rate_limit=False, **kwargs):
        open_client_instance = OpenClient.get_client(request.client_id)
        client = open_client_instance.client

        msg_header = self.build_msg_header(client_method_name, open_client_instance, request)

        if rate_limit:
            await self.rate_limit_control(client.exchange, open_client_instance.ts_rlc)

        if client.exchange == 'bitfinex':
            await client.request_event.wait()
            client.request_event.clear()

        try:
            res = await asyncio.wait_for(getattr(client, client_method_name)(**kwargs), timeout=HEARTBEAT * 60)
        except asyncio.exceptions.CancelledError:
            raise GRPCError(status=Status.UNAVAILABLE, message=f"{msg_header} Server Shutdown")
        except asyncio.exceptions.TimeoutError:
            self.log_and_raise_grpc_error(msg_header, Status.RESOURCE_EXHAUSTED, "timeout error")
        except (errors.RateLimitReached, errors.QueryCanceled) as ex:
            Martin.rate_limit_reached_time = time.time()
            self.log_and_raise_grpc_error(msg_header, Status.RESOURCE_EXHAUSTED, f"RateLimitReached: {ex}")
        except errors.HTTPError as ex:
            self.log_and_raise_grpc_error(msg_header, Status.FAILED_PRECONDITION, f"HTTPError: {ex}")
        except ExchangeError as ex:
            self.log_and_raise_grpc_error(msg_header, Status.OUT_OF_RANGE, str(ex))
        except Exception as ex:
            logger.error(f"{msg_header} exception: {ex}")
            logger.debug(traceback.format_exc())
            raise GRPCError(status=Status.UNKNOWN, message=f"{msg_header} exception: {ex}")
        else:
            if rate_limit:
                open_client_instance.ts_rlc = time.time()
            return res, client, msg_header
        finally:
            client.request_event.set()

    def build_msg_header(self, client_method_name, open_client_instance, request):
        msg_header = f"Send request: {client_method_name}:{open_client_instance.name}:"
        if hasattr(request, 'symbol'):
            msg_header += f"{request.symbol}:"
        if hasattr(request, 'order_id'):
            msg_header += f"{request.order_id}:"
        if hasattr(request, 'client_order_id'):
            msg_header += f"({request.client_order_id}):"
        return msg_header

    def log_and_raise_grpc_error(self, msg_header, status, msg):
        logger.warning(f"{msg_header} {msg}")
        raise GRPCError(status=status, message=f"{msg_header} {msg}")

    async def fetch_server_time(self, request: mr.OpenClientConnectionId) -> mr.FetchServerTimeResponse:
        res, _, _ = await self.send_request('fetch_server_time', request, rate_limit=True)
        server_time = res.get('serverTime')
        return mr.FetchServerTimeResponse(server_time=server_time)

    async def one_click_arrival_deposit(self, request: mr.MarketRequest) -> mr.SimpleResponse():
        res, _, _ = await self.send_request('one_click_arrival_deposit', request, tx_id=request.symbol)
        return mr.SimpleResponse(success=True, result=json.dumps(str(res)))

    async def fetch_open_orders(self, request: mr.MarketRequest) -> mr.FetchOpenOrdersResponse:
        response = mr.FetchOpenOrdersResponse()
        res, client, _ = await self.send_request(
            'fetch_open_orders',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
            symbol=request.symbol
        )
        for order in res:
            order_id = order['orderId']
            response.orders.append(json.dumps(order))
            if client.exchange in ('bitfinex', 'huobi'):
                client.active_order(order_id, order['origQty'], order['executedQty'])

        if client.exchange in ('bitfinex', 'huobi'):
            client.active_orders_clear()

        response.rate_limiter = Martin.rate_limiter
        return response

    async def fetch_order(self, request: mr.FetchOrderRequest) -> mr.FetchOrderResponse:
        response = mr.FetchOrderResponse()
        res, _, msg_header = await self.send_request(
            'fetch_order',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
            symbol=request.symbol,
            order_id=request.order_id,
            origin_client_order_id=request.client_order_id,
            receive_window=None
        )
        logger.debug(f"{msg_header}: {res}")

        if res and request.filled_update_call and Decimal(res['executedQty']):
            request.order_id = res['orderId']
            await self.create_trade_stream_event(request, res)
        response.from_pydict(res)
        return response

    async def create_trade_stream_event(self, request, order):
        trades, client, msg_header = await self.send_request(
            'fetch_order_trade_list',
            request,
            trade_id=request.trade_id,
            symbol=request.symbol,
            order_id=request.order_id
        )

        _queue = client.on_order_update_queues.get(request.trade_id)

        for trade in trades:
            trade['updateTime'] = trade.pop('time')
            trade |= {
                'clientOrderId': order['clientOrderId'],
                'orderPrice': order['price'],
                'origQty': order['origQty'],
                'executedQty': order['executedQty'],
                'cummulativeQuoteQty': order['cummulativeQuoteQty'],
                'status': order['status'],
                "time": order['time']
            }
            event = OrderTradesEvent(trade)
            await _queue.put(weakref.ref(event)())
        logger.debug(f"{msg_header}: {trades}")

    async def cancel_all_orders(self, request: mr.MarketRequest) -> mr.SimpleResponse():
        response = mr.SimpleResponse()

        res, _, _ = await self.send_request(
            'cancel_all_orders',
            request,
            trade_id=request.trade_id,
            symbol=request.symbol
        )

        response.success = True
        response.result = json.dumps(str(res))
        return response

    async def fetch_exchange_info_symbol(self, request: mr.MarketRequest) -> mr.FetchExchangeInfoSymbolResponse:
        response = mr.FetchExchangeInfoSymbolResponse()
        exchange_info, _, _ = await self.send_request(
            'fetch_exchange_info',
            request,
            rate_limit=True,
            symbol=request.symbol
        )

        if exchange_info_symbol := exchange_info.get('symbols'):
            exchange_info_symbol = exchange_info_symbol[0]
        else:
            raise UserWarning(f"Symbol {request.symbol} not exist")

        filters_res = exchange_info_symbol.pop('filters', [])
        response.from_pydict(exchange_info_symbol)
        response.filters = self.process_filters(filters_res)
        return response

    def process_filters(self, filters_res):
        filters = mr.FetchExchangeInfoSymbolResponseFilters()
        for _filter in filters_res:
            filter_type = _filter.get('filterType')
            if filter_type == 'PERCENT_PRICE_BY_SIDE':
                filter_type = _filter['filterType'] = 'PERCENT_PRICE'
                _filter['multiplierUp'] = _filter['askMultiplierUp']
                _filter['multiplierDown'] = _filter['bidMultiplierDown']
                del _filter['bidMultiplierUp']
                del _filter['bidMultiplierDown']
                del _filter['askMultiplierUp']
                del _filter['askMultiplierDown']
            if filter_class := FILTER_TYPE_MAP.get(filter_type):
                filter_instance = filter_class()
                filter_instance.from_pydict(_filter)
                setattr(filters, filter_type.lower(), filter_instance)
        return filters

    async def fetch_account_information(self, request: mr.OpenClientConnectionId) -> mr.JsonResponse:
        response = mr.JsonResponse()
        account_information, _, _ = await self.send_request(
            'fetch_account_information',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
        )
        # Send only balances
        res = account_information.get('balances', [])
        # Create consolidated list of asset balances from SPOT and Funding wallets
        balances = [
            {'asset': i['asset'], 'free': i['free'], 'locked': i['locked']}
            for i in res if float(i['free']) or float(i['locked'])
        ]
        response.items = list(map(json.dumps, balances))
        return response

    async def fetch_funding_wallet(self, request: mr.FetchFundingWalletRequest) -> mr.JsonResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = mr.JsonResponse()
        res = []
        if client.exchange in ('bitfinex', 'okx', 'bybit') \
                or (open_client.real_market and client.exchange == 'binance'):

            res, _, _ = await self.send_request(
                'fetch_funding_wallet',
                request,
                rate_limit=True,
                asset=request.asset,
                need_btc_valuation=request.need_btc_valuation,
                receive_window=request.receive_window
            )

        response.items = list(map(json.dumps, res))
        return response

    async def fetch_order_book(self, request: mr.MarketRequest) -> mr.FetchOrderBookResponse:
        response = mr.FetchOrderBookResponse()
        res, _, _ = await self.send_request(
            'fetch_order_book',
            request,
            rate_limit=True,
            symbol=request.symbol
        )

        res['bids'] = [json.dumps(v) for v in res.get('bids', [])]
        res['asks'] = [json.dumps(v) for v in res.get('asks', [])]
        return response.from_pydict(res)

    async def fetch_symbol_price_ticker(self, request: mr.MarketRequest) -> mr.FetchSymbolPriceTickerResponse:
        response = mr.FetchSymbolPriceTickerResponse()
        res, _, _ = await self.send_request(
            'fetch_symbol_price_ticker',
            request,
            rate_limit=True,
            symbol=request.symbol
        )
        return response.from_pydict(res)

    async def fetch_ticker_price_change_statistics(
            self,
            request: mr.MarketRequest
    ) -> mr.FetchTickerPriceChangeStatisticsResponse:
        response = mr.FetchTickerPriceChangeStatisticsResponse()
        res, _, _ = await self.send_request(
            'fetch_ticker_price_change_statistics',
            request,
            rate_limit=True,
            symbol=request.symbol
        )
        return response.from_pydict(res)

    async def fetch_klines(self, request: mr.FetchKlinesRequest) -> mr.JsonResponse:
        response = mr.JsonResponse()

        res, _, _ = await self.send_request(
            'fetch_klines',
            request,
            rate_limit=True,
            symbol=request.symbol,
            interval=request.interval,
            start_time=None,
            end_time=None,
            limit=request.limit
        )

        response.items = list(map(json.dumps, res))
        return response

    async def on_klines_update(self, request: mr.FetchKlinesRequest) -> mr.OnKlinesUpdateResponse:
        response = mr.OnKlinesUpdateResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        _intervals = json.loads(request.interval)
        event_types = []
        # Register streams for intervals
        if client.exchange == 'bitfinex':
            exchange = 'bitfinex'
            _symbol = client.symbol_to_bfx(request.symbol)
        elif client.exchange == 'okx':
            exchange = 'okx'
            _symbol = client.symbol_to_okx(request.symbol)
        elif client.exchange == 'bybit':
            exchange = 'bybit'
            _symbol = request.symbol
        else:
            exchange = 'huobi' if client.exchange == 'huobi' else 'binance'
            _symbol = request.symbol.lower()
        for i in _intervals:
            _event_type = f"{_symbol}@kline_{i}"
            event_types.append(_event_type)
            client.events.register_event(functools.partial(
                event_handler, _queue, client, request.trade_id, _event_type),
                _event_type, exchange, request.trade_id)
        while True:
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnKlinesUpdate: Stop loop for {open_client.name}:{request.symbol}:{_intervals}")
                return
            else:
                # logger.info(f"OnKlinesUpdate.event: {exchange}:{_event.symbol}:{_event.kline_interval}")
                response.symbol = _event.symbol
                response.interval = _event.kline_interval
                response.candle = json.dumps(
                    [_event.kline_start_time,
                     _event.kline_open_price,
                     _event.kline_high_price,
                     _event.kline_low_price,
                     _event.kline_close_price,
                     _event.kline_base_asset_volume,
                     _event.kline_close_time,
                     _event.kline_quote_asset_volume,
                     _event.kline_trades_number,
                     _event.kline_taker_buy_base_asset_volume,
                     _event.kline_taker_buy_quote_asset_volume,
                     _event.kline_ignore
                     ]
                )
                yield response
                _queue.task_done()

    async def fetch_account_trade_list(self, request: mr.AccountTradeListRequest) -> mr.JsonResponse:
        response = mr.JsonResponse()

        res, _, _ = await self.send_request(
            'fetch_account_trade_list',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
            symbol=request.symbol,
            start_time=request.start_time,
            end_time=None,
            from_id=None,
            limit=request.limit,
            receive_window=None
        )

        response.items = list(map(json.dumps, res))
        return response

    async def on_ticker_update(self, request: mr.MarketRequest) -> mr.OnTickerUpdateResponse:
        response = mr.OnTickerUpdateResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        if client.exchange == 'okx':
            _symbol = client.symbol_to_okx(request.symbol)
        elif client.exchange == 'bitfinex':
            _symbol = client.symbol_to_bfx(request.symbol)
        elif client.exchange == 'bybit':
            _symbol = request.symbol
        else:
            _symbol = request.symbol.lower()
        _event_type = f"{_symbol}@miniTicker"
        client.events.register_event(functools.partial(event_handler, _queue, client, request.trade_id, _event_type),
                                     _event_type, client.exchange, request.trade_id)
        while True:
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnTickerUpdate: Stop loop for {open_client.name}: {request.symbol}")
                return
            else:
                response.from_pydict(
                    {
                        'openPrice': _event.open_price,
                        'lastPrice': _event.close_price,
                        'closeTime': _event.event_time
                    }
                )
                yield response
                _queue.task_done()

    async def on_order_book_update(self, request: mr.MarketRequest) -> mr.FetchOrderBookResponse:
        response = mr.FetchOrderBookResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.LifoQueue(MAX_QUEUE_SIZE * 5)
        client.stream_queue[request.trade_id] |= {_queue}
        if client.exchange == 'okx':
            _symbol = client.symbol_to_okx(request.symbol)
        elif client.exchange == 'bitfinex':
            _symbol = client.symbol_to_bfx(request.symbol)
        elif client.exchange == 'bybit':
            _symbol = request.symbol
        else:
            _symbol = request.symbol.lower()
        _event_type = f"{_symbol}@depth5"
        client.events.register_event(functools.partial(event_handler, _queue, client, request.trade_id, _event_type),
                                     _event_type, client.exchange, request.trade_id)
        while True:
            _event = await _queue.get()
            while not _queue.empty():
                _queue.get_nowait()
                _queue.task_done()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnOrderBookUpdate: Stop loop for {open_client.name}: {request.symbol}")
                return
            else:
                if _event.bids and _event.asks:
                    response.last_update_id = _event.last_update_id
                    response.bids = list(map(json.dumps, _event.bids))
                    response.asks = list(map(json.dumps, _event.asks))
                    yield response
                _queue.task_done()

    async def on_funds_update(self, request: mr.OnFundsUpdateRequest) -> mr.StreamResponse:
        response = mr.StreamResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        client.events.register_user_event(functools.partial(
            event_handler, _queue, client, request.trade_id, 'outboundAccountPosition'),
            'outboundAccountPosition')
        while True:
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnFundsUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            else:
                response.event = json.dumps(_event.balances)
                yield response
                _queue.task_done()

    async def on_balance_update(self, request: mr.MarketRequest) -> mr.StreamResponse:
        response = mr.StreamResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        if client.exchange in ('binance', 'okx'):
            client.events.register_user_event(functools.partial(
                event_handler, _queue, client, request.trade_id, 'balanceUpdate'), 'balanceUpdate')
        _events = []
        while True:
            _events.clear()
            try:
                _event = await asyncio.wait_for(_queue.get(), timeout=HEARTBEAT * 30)
                if isinstance(_event, str) and _event == request.trade_id:
                    client.stream_queue.get(request.trade_id, set()).discard(_queue)
                    logger.info(f"OnBalanceUpdate: Stop user stream for {open_client.name}:{request.symbol}")
                    return
                _events.append(_event)
                _get_event_from_queue = True
            except asyncio.exceptions.TimeoutError:
                _get_event_from_queue = False

                if client.exchange in ('bitfinex', 'huobi', 'bybit'):
                    balances, _, _ = await self.send_request(
                        'fetch_ledgers',
                        request,
                        rate_limit=True,
                        symbol=request.symbol
                    )
                    [_events.append(client.events.wrap_event(balance)) for balance in balances]

            for _event in _events:
                if _event.asset in request.symbol:
                    balance = {
                        "event_time": _event.event_time,
                        "asset": _event.asset,
                        "balance_delta": _event.balance_delta,
                        "clear_time": _event.clear_time
                    }
                    response.event = json.dumps(balance)
                    yield response

                if _get_event_from_queue:
                    _queue.task_done()

    async def on_order_update(self, request: mr.MarketRequest) -> mr.SimpleResponse:
        response = mr.SimpleResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.on_order_update_queues.update({request.trade_id: _queue})
        client.stream_queue[request.trade_id] |= {_queue}
        client.events.register_user_event(functools.partial(
            event_handler, _queue, client, request.trade_id, 'executionReport'),
            'executionReport')
        while True:
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnOrderUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            else:
                event = vars(_event)
                event.pop('handlers', None)
                # logger.info(f"OnOrderUpdate: {open_client.name}: {event}")
                response.success = True
                response.result = json.dumps(event)
                yield response
                _queue.task_done()

    async def create_limit_order(self, request: mr.CreateLimitOrderRequest) -> mr.CreateLimitOrderResponse:
        response = mr.CreateLimitOrderResponse()

        res, _, _ = await self.send_request(
            'create_order',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
            symbol=request.symbol,
            side=Side.BUY if request.buy_side else Side.SELL,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            quantity=request.quantity,
            price=request.price,
            new_client_order_id=request.new_client_order_id,
            response_type=ResponseType.RESULT.value,
            receive_window=None,
            test=False
        )

        response.from_pydict(res)
        return response

    async def cancel_order(self, request: mr.CancelOrderRequest) -> mr.CancelOrderResponse:
        response = mr.CancelOrderResponse()

        res, _, _ = await self.send_request(
            'cancel_order',
            request,
            rate_limit=True,
            trade_id=request.trade_id,
            symbol=request.symbol,
            order_id=request.order_id,
            origin_client_order_id=None,
            new_client_order_id=None,
            receive_window=None
        )

        response.from_pydict(res)
        return response

    async def transfer_to_sub(self, request: mr.MarketRequest) -> mr.SimpleResponse:
        response = mr.SimpleResponse()
        response.success = False

        res, _, _ = await self.send_request(
            'transfer_to_sub',
            request,
            rate_limit=True,
            email=request.data,
            symbol=request.symbol,
            quantity=request.amount
        )

        if res and res.get("txnId"):
            response.success = True
        response.result = json.dumps(res)
        return response

    async def transfer_to_master(self, request: mr.MarketRequest) -> mr.SimpleResponse:
        response = mr.SimpleResponse()
        response.success = False

        res, _, _ = await self.send_request(
            'transfer_to_master',
            request,
            rate_limit=True,
            symbol=request.symbol,
            quantity=request.amount
        )

        if res and res.get("txnId"):
            response.success = True
        response.result = json.dumps(res)
        return response

    async def start_stream(self, request: mr.StartStreamRequest) -> mr.SimpleResponse:
        if request.update_max_queue_size:
            global MAX_QUEUE_SIZE
            MAX_QUEUE_SIZE += int(MAX_QUEUE_SIZE / 10)
            logger.info(f"MAX_QUEUE_SIZE was updated: new value is {MAX_QUEUE_SIZE}")
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = mr.SimpleResponse()
        _market_stream_count = 0
        while _market_stream_count < request.market_stream_count:
            await asyncio.sleep(HEARTBEAT)
            _market_stream_count = sum(
                len(v[request.trade_id]) for v in client.events.registered_streams.values() if request.trade_id in v
            )
        logger.info(f"Start WS streams for {open_client.name}")
        await client.start_market_events_listener(request.trade_id)
        await client.start_user_events_listener(request.trade_id, request.symbol)
        response.success = True
        return response

    async def stop_stream(self, request: mr.MarketRequest) -> mr.SimpleResponse:
        response = mr.SimpleResponse()
        if open_client := OpenClient.get_client(request.client_id):
            client = open_client.client
            logger.info(f"StopStream request for {request.symbol} on {client.exchange}")
            await stop_stream(client, request.trade_id)
            response.success = True
        else:
            response.success = False
        return response

    async def check_stream(self, request: mr.MarketRequest) -> mr.SimpleResponse:
        response = mr.SimpleResponse()
        response.success = False
        if open_client := OpenClient.get_client(request.client_id):
            client = open_client.client
            response.success = bool(client.data_streams.get(request.trade_id))
        else:
            logger.warning(f"CheckStream request failed for {request.symbol}")
        return response


async def stop_stream(client, trade_id):
    await client.stop_events_listener(trade_id)
    client.events.unregister(client.exchange, trade_id)
    [await _queue.put(trade_id) for _queue in client.stream_queue.get(trade_id, [])]
    await asyncio.sleep(0)
    client.on_order_update_queues.pop(trade_id, None)
    client.stream_queue.pop(trade_id, None)
    gc.collect(generation=2)


async def event_handler(_queue, client, trade_id, _event_type, event):
    try:
        _queue.put_nowait(weakref.ref(event)())
    except asyncio.QueueFull:
        logger.warning(f"For {_event_type} asyncio queue full and wold be closed")
        client.stream_queue.get(trade_id, set()).discard(_queue)
        await stop_stream(client, trade_id)


def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


async def amain(host: str = '127.0.0.1', port: int = 50051):
    if is_port_in_use(port):
        raise SystemExit(f"gRPC server port {port} already used")

    server = Server([Martin()])
    with graceful_exit([server]):
        await server.start(host, port)
        logger.info(f"Starting server v:{VER_CW}:{VER_EW} on {host}:{port}")
        await server.wait_closed()

        for oc in OpenClient.open_clients:
            await oc.client.session.close()

        [task.cancel() for task in asyncio.all_tasks() if not task.done() and task is not asyncio.current_task()]


def main():
    try:
        asyncio.run(amain())
    except (asyncio.exceptions.CancelledError, grpclib.exceptions.StreamTerminatedError):
        pass  # # Task cancellation should not be logged as an error
    except Exception as ex:
        print(f"Exception: {ex}")
        print(traceback.format_exc())


if __name__ == '__main__':
    main()
