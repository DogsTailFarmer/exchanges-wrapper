#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from exchanges_wrapper import __version__
import time
import weakref
import gc
import traceback
import asyncio
import functools
import json
import logging.handlers
import toml
# noinspection PyPackageRequirements
import grpc
# noinspection PyPackageRequirements
from google.protobuf import json_format
#
from exchanges_wrapper import errors, api_pb2, api_pb2_grpc
from exchanges_wrapper.client import Client, STATUS_TIMEOUT
from exchanges_wrapper.definitions import Side, OrderType, TimeInForce, ResponseType
from exchanges_wrapper.c_structures import OrderUpdateEvent, OrderTradesEvent, REST_RATE_LIMIT_INTERVAL
from exchanges_wrapper import WORK_PATH, CONFIG_FILE, LOG_FILE
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


def get_account(_account_name: str) -> ():
    config = toml.load(str(CONFIG_FILE))
    accounts = config.get('accounts')

    for account in accounts:
        if account.get('name') == _account_name:
            exchange = account['exchange']
            sub_account = account.get('sub_account_name')
            test_net = account['test_net']
            master_email = account.get('master_email')
            master_name = account.get('master_name')

            endpoint = config['endpoint'][exchange]
            ws_add_on = None

            if exchange == 'huobi':
                ws_add_on = endpoint.get('ws_public_mbr')
            elif exchange == 'okx':
                ws_add_on = endpoint.get('ws_business')

            if exchange == 'bitfinex':
                api_auth = endpoint['api_auth']
            else:
                api_auth = endpoint['api_test'] if test_net else endpoint['api_auth']
            api_public = endpoint['api_public']

            ws_public = endpoint['ws_test_public'] if exchange == 'bybit' and test_net else endpoint['ws_public']

            if exchange == 'bitfinex':
                ws_api = ws_auth = endpoint['ws_auth']
            else:
                ws_auth = endpoint['ws_test'] if test_net else endpoint['ws_auth']
                if exchange == 'okx':
                    ws_api = ws_auth
                else:
                    ws_api = endpoint.get('ws_api_test') if test_net else endpoint.get('ws_api')

            if exchange == 'binance_us':
                exchange = 'binance'

            res = (
                exchange,
                sub_account,
                test_net,
                account['api_key'],
                account['api_secret'],
                api_public,
                ws_public,
                api_auth,
                ws_auth,
                ws_add_on,
                account.get('passphrase'),
                master_email,
                master_name,
                account.get('two_fa'),
                ws_api
            )
            return res
    return ()


class OpenClient:
    open_clients = []

    def __init__(self, _account_name: str):
        if account := get_account(_account_name):
            self.name = _account_name
            self.real_market = not account[2]
            self.client = Client(*account)
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
        return next((client for client in cls.open_clients if id(client) == _id), None)

    @classmethod
    def remove_client(cls, _account_name):
        cls.open_clients[:] = [i for i in cls.open_clients if i.name != _account_name]


# noinspection PyPep8Naming,PyMethodMayBeStatic
class Martin(api_pb2_grpc.MartinServicer):
    rate_limit_reached_time = None
    rate_limiter = None

    async def rate_limit_control(self, client, _call_from='default'):
        if client.client.exchange == 'bitfinex':
            rate_limit_interval = REST_RATE_LIMIT_INTERVAL.get(client.client.exchange, {}).get(_call_from, 0)
            ts_diff = time.time() - client.ts_rlc
            if ts_diff < rate_limit_interval:
                sleep_duration = rate_limit_interval - ts_diff
                await asyncio.sleep(sleep_duration)

    async def OpenClientConnection(self, request: api_pb2.OpenClientConnectionRequest,
                                   _context: grpc.aio.ServicerContext) -> api_pb2.OpenClientConnectionId:
        logger.info(f"OpenClientConnection start trade: {request.account_name}:{request.trade_id}")
        client_id = OpenClient.get_id(request.account_name)
        if client_id:
            open_client = OpenClient.get_client(client_id)
            open_client.client.http.rate_limit_reached = False
        else:
            try:
                open_client = OpenClient(request.account_name)
                client_id = id(open_client)
                if open_client.client.master_name == 'Huobi':
                    # For HuobiPro get master account uid and account_id
                    main_account = get_account(open_client.client.master_name)
                    main_client = Client(*main_account)
                    await main_client.fetch_exchange_info(request.symbol)
                    if main_client.account_uid and main_client.account_id:
                        open_client.client.main_account_uid = main_client.account_uid
                        open_client.client.main_account_id = main_client.account_id
                        logger.info(f"The values for main Huobi account were received and set:"
                                    f" UID: {main_client.account_uid} and account ID: {main_client.account_id}")
                    else:
                        logger.warning("No account IDs were received for the Huobi master account")
                    await main_client.close()
            except UserWarning as ex:
                _context.set_details(f"{ex}")
                _context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                return api_pb2.OpenClientConnectionId(
                    client_id=client_id,
                    srv_version=__version__,
                    exchange=request.account_name
                )
        try:
            await open_client.client.load(request.symbol)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.warning(f"OpenClientConnection for '{open_client.name}' exception: {ex}")
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
            await OpenClient.get_client(client_id).client.session.close()
            OpenClient.remove_client(request.account_name)
            return api_pb2.OpenClientConnectionId(
                client_id=client_id,
                srv_version=__version__,
                exchange=request.account_name
            )

        # Set rate_limiter
        Martin.rate_limiter = max(Martin.rate_limiter or 0, request.rate_limiter)
        return api_pb2.OpenClientConnectionId(
            client_id=client_id,
            srv_version=__version__,
            exchange=open_client.client.exchange
        )

    async def FetchServerTime(self, request: api_pb2.OpenClientConnectionId,
                              _context: grpc.aio.ServicerContext) -> api_pb2.FetchServerTimeResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        await self.rate_limit_control(open_client)
        try:
            res = await client.fetch_server_time()
        except Exception as ex:
            logger.error(f"FetchServerTime for {open_client.name} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            open_client.ts_rlc = time.time()
            server_time = res.get('serverTime')
            return api_pb2.FetchServerTimeResponse(server_time=server_time)

    async def ResetRateLimit(self, request: api_pb2.OpenClientConnectionId,
                             _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
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
        return api_pb2.SimpleResponse(success=_success)

    async def FetchOpenOrders(self, request: api_pb2.MarketRequest,
                              _context: grpc.aio.ServicerContext) -> api_pb2.FetchOpenOrdersResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchOpenOrdersResponse()
        response_order = api_pb2.FetchOpenOrdersResponse.Order()
        await self.rate_limit_control(open_client)
        try:
            res = await client.fetch_open_orders(request.trade_id, request.symbol)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except (errors.RateLimitReached, errors.QueryCanceled) as ex:
            Martin.rate_limit_reached_time = time.time()
            logger.warning(f"FetchOpenOrders for {open_client.name}:{request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
        except errors.HTTPError as ex:
            logger.error(f"FetchOpenOrders for {open_client.name}:{request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        except Exception as ex:
            logger.error(f"FetchOpenOrders for {open_client.name}:{request.symbol} exception: {ex}")
            logger.debug(f"FetchOpenOrders for {open_client.name}:{request.symbol} exception: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            # logger.info(f"FetchOpenOrders.res: {res}")
            open_client.ts_rlc = time.time()
            active_orders = []
            for order in res:
                order_id = order['orderId']
                active_orders.append(order_id)
                new_order = json_format.ParseDict(order, response_order)
                # logger.debug(f"FetchOpenOrders.new_order: {new_order}")
                response.items.append(new_order)
                if client.exchange == 'bitfinex':
                    if order_id in client.active_orders:
                        client.active_orders[order_id]['executedQty'] = order['executedQty']
                    else:
                        client.active_orders[order_id] = {
                            'lifeTime': int(time.time()) + 60 * STATUS_TIMEOUT,
                            'origQty': order['origQty'],
                            'executedQty': order['executedQty'],
                            'lastEvent': (),
                            'cancelled': False
                        }
            if client.exchange == 'bitfinex':
                client.active_orders_clear(active_orders)
        response.rate_limiter = Martin.rate_limiter
        return response

    async def FetchOrder(self, request: api_pb2.FetchOrderRequest,
                         _context: grpc.aio.ServicerContext) -> api_pb2.FetchOrderResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = client.on_order_update_queues.get(request.trade_id)
        response = api_pb2.FetchOrderResponse()
        await self.rate_limit_control(open_client)
        try:
            res = await client.fetch_order(
                request.trade_id,
                symbol=request.symbol,
                order_id=request.order_id,
                origin_client_order_id=request.client_order_id,
                receive_window=None
            )
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.error(f"FetchOrder for {open_client.name}: {request.symbol}:"
                         f" {request.order_id}({request.client_order_id}) exception: {_ex}")
        else:
            open_client.ts_rlc = time.time()
            if _queue and request.filled_update_call:
                if res.get('status') == 'FILLED':
                    event = OrderUpdateEvent(res)
                    logger.info(f"FetchOrder.event: {open_client.name}:{event.symbol}:{event.order_id}:"
                                f"{event.order_status}")
                    await _queue.put(weakref.ref(event)())
                elif res.get('status') == 'PARTIALLY_FILLED':
                    try:
                        trades = await client.fetch_order_trade_list(request.trade_id, request.symbol, request.order_id)
                    except asyncio.CancelledError:
                        pass  # Task cancellation should not be logged as an error
                    except Exception as _ex:
                        logger.error(f"Fetch order trades for {open_client.name}: {request.symbol} exception: {_ex}")
                    else:
                        logger.debug(f"FetchOrder.trades: {trades}")
                        for trade in trades:
                            event = OrderTradesEvent(trade)
                            await _queue.put(weakref.ref(event)())
            json_format.ParseDict(res, response)
        return response

    async def CancelAllOrders(self, request: api_pb2.MarketRequest,
                              _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse():
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.SimpleResponse()
        try:
            res = await client.cancel_all_orders(request.trade_id, request.symbol)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.error(f"CancelAllOrder for {open_client.name}:{request.symbol} exception: {ex}")
            logger.debug(f"CancelAllOrder for {open_client.name}:{request.symbol} error: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            response.success = True
            response.result = json.dumps(str(res))
        return response

    async def FetchExchangeInfoSymbol(self, request: api_pb2.MarketRequest,
                                      _context: grpc.aio.ServicerContext) -> api_pb2.FetchExchangeInfoSymbolResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchExchangeInfoSymbolResponse()
        exchange_info = await client.fetch_exchange_info(request.symbol)
        if exchange_info_symbol := exchange_info.get('symbols'):
            exchange_info_symbol = exchange_info_symbol[0]
        else:
            raise UserWarning(f"Symbol {request.symbol} not exist")
        await self.rate_limit_control(open_client)
        # logger.info(f"exchange_info_symbol: {exchange_info_symbol}")
        open_client.ts_rlc = time.time()
        filters_res = exchange_info_symbol.pop('filters', [])
        json_format.ParseDict(exchange_info_symbol, response)
        # logger.info(f"filters: {filters_res}")
        filters = response.filters
        for _filter in filters_res:
            filter_type = _filter.get('filterType')
            if filter_type == 'PRICE_FILTER':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.PriceFilter()
                filters.price_filter.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif 'PERCENT_PRICE' in filter_type:
                if filter_type == 'PERCENT_PRICE_BY_SIDE':
                    _filter['multiplierUp'] = _filter['bidMultiplierUp']
                    _filter['multiplierDown'] = _filter['bidMultiplierDown']
                    del _filter['bidMultiplierUp']
                    del _filter['bidMultiplierDown']
                    del _filter['askMultiplierUp']
                    del _filter['askMultiplierDown']
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.PercentPrice()
                filters.percent_price.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'LOT_SIZE':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.LotSize()
                filters.lot_size.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'MIN_NOTIONAL':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MinNotional()
                filters.min_notional.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'NOTIONAL':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.Notional()
                filters.notional.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'ICEBERG_PARTS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.IcebergParts()
                filters.iceberg_parts.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'MARKET_LOT_SIZE':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MarketLotSize()
                filters.market_lot_size.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'MAX_NUM_ORDERS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumOrders()
                filters.max_num_orders.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'MAX_NUM_ICEBERG_ORDERS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumIcebergOrders()
                filters.max_num_iceberg_orders.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif filter_type == 'MAX_POSITION':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxPosition()
                filters.max_position.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
        return response

    async def FetchAccountInformation(self, request: api_pb2.OpenClientConnectionId,
                                      _context: grpc.aio.ServicerContext
                                      ) -> api_pb2.FetchAccountBalanceResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchAccountBalanceResponse()
        response_balance = api_pb2.FetchAccountBalanceResponse.Balances()
        await self.rate_limit_control(open_client)
        account_information = await client.fetch_account_information(request.trade_id, receive_window=None)
        open_client.ts_rlc = time.time()
        # Send only balances
        res = account_information.get('balances', [])
        # Create consolidated list of asset balances from SPOT and Funding wallets
        balances = []
        for i in res:
            _free = float(i.get('free'))
            _locked = float(i.get('locked'))
            if _free or _locked:
                balances.append({'asset': i.get('asset'), 'free': i.get('free'), 'locked': i.get('locked')})
        # logger.info(f"account_information.balances: {balances}")
        for balance in balances:
            new_balance = json_format.ParseDict(balance, response_balance)
            response.balances.extend([new_balance])
        return response

    async def FetchFundingWallet(self, request: api_pb2.FetchFundingWalletRequest,
                                 _context: grpc.aio.ServicerContext) -> api_pb2.FetchFundingWalletResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchFundingWalletResponse()
        response_balance = api_pb2.FetchFundingWalletResponse.Balances()
        await self.rate_limit_control(open_client)
        res = []
        if (client.exchange in ('bitfinex', 'okx', 'bybit') or
                (open_client.real_market and client.exchange == 'binance')):
            try:
                res = await client.fetch_funding_wallet(asset=request.asset,
                                                        need_btc_valuation=request.need_btc_valuation,
                                                        receive_window=request.receive_window)
            except AttributeError:
                logger.error("Can't get Funding Wallet balances")
        open_client.ts_rlc = time.time()
        logger.debug(f"funding_wallet: {res}")
        for balance in res:
            new_balance = json_format.ParseDict(balance, response_balance)
            response.balances.extend([new_balance])
        return response

    async def FetchOrderBook(self, request: api_pb2.MarketRequest,
                             _context: grpc.aio.ServicerContext) -> api_pb2.FetchOrderBookResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchOrderBookResponse()
        await self.rate_limit_control(open_client)
        limit = 1 if client.exchange in ('bitfinex', 'okx') else 5
        res = await client.fetch_order_book(symbol=request.symbol, limit=limit)
        open_client.ts_rlc = time.time()
        res_bids = res.get('bids', [])
        res_asks = res.get('asks', [])
        response.lastUpdateId = res.get('lastUpdateId')
        for bid in res_bids:
            response.bids.append(json.dumps(bid))
        for ask in res_asks:
            response.asks.append(json.dumps(ask))
        return response

    async def FetchSymbolPriceTicker(
            self, request: api_pb2.MarketRequest,
            _context: grpc.aio.ServicerContext) -> api_pb2.FetchSymbolPriceTickerResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchSymbolPriceTickerResponse()
        await self.rate_limit_control(open_client)
        res = await client.fetch_symbol_price_ticker(symbol=request.symbol)
        open_client.ts_rlc = time.time()
        json_format.ParseDict(res, response)
        return response

    async def FetchTickerPriceChangeStatistics(
            self, request: api_pb2.MarketRequest,
            _context: grpc.aio.ServicerContext) -> api_pb2.FetchTickerPriceChangeStatisticsResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchTickerPriceChangeStatisticsResponse()
        await self.rate_limit_control(open_client)
        res = await client.fetch_ticker_price_change_statistics(symbol=request.symbol)
        open_client.ts_rlc = time.time()
        json_format.ParseDict(res, response)
        return response

    async def FetchKlines(self, request: api_pb2.FetchKlinesRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.FetchKlinesResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.FetchKlinesResponse()
        await self.rate_limit_control(open_client)
        try:
            res = await client.fetch_klines(symbol=request.symbol, interval=request.interval,
                                            start_time=None, end_time=None, limit=request.limit)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.error(f"FetchKlines for {request.symbol} interval: {request.interval}, exception: {_ex}")
        else:
            # logger.info(f"FetchKlines.res: {res}")
            open_client.ts_rlc = time.time()
            for candle in res:
                response.klines.append(json.dumps(candle))
        return response

    async def OnKlinesUpdate(self, request: api_pb2.FetchKlinesRequest,
                             _context: grpc.aio.ServicerContext) -> api_pb2.OnKlinesUpdateResponse:
        response = api_pb2.OnKlinesUpdateResponse()
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
            response.Clear()
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnKlinesUpdate: Stop loop for {open_client.name}:{request.symbol}:{_intervals}")
                return
            else:
                # logger.info(f"OnKlinesUpdate.event: {exchange}:{_event.symbol}:{_event.kline_interval}")
                response.symbol = _event.symbol
                response.interval = _event.kline_interval
                candle = [_event.kline_start_time,
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
                response.candle = json.dumps(candle)
                yield response
                _queue.task_done()

    async def FetchAccountTradeList(self, request: api_pb2.AccountTradeListRequest,
                                    _context: grpc.aio.ServicerContext) -> api_pb2.AccountTradeListResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.AccountTradeListResponse()
        response_trade = api_pb2.AccountTradeListResponse.Trade()
        await self.rate_limit_control(open_client)
        try:
            res = await client.fetch_account_trade_list(
                request.trade_id,
                request.symbol,
                start_time=request.start_time,
                end_time=None,
                from_id=None,
                limit=request.limit,
                receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.error(f"FetchAccountTradeList for {open_client.name}: {request.symbol} exception: {_ex}")
        else:
            # logger.info(f"FetchAccountTradeList: {res}")
            open_client.ts_rlc = time.time()
            for trade in res:
                trade_order = json_format.ParseDict(trade, response_trade)
                response.items.append(trade_order)
        return response

    async def OnTickerUpdate(self, request: api_pb2.MarketRequest,
                             _context: grpc.aio.ServicerContext) -> api_pb2.OnTickerUpdateResponse:
        response = api_pb2.OnTickerUpdateResponse()
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
            response.Clear()
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnTickerUpdate: Stop loop for {open_client.name}: {request.symbol}")
                return
            else:
                ticker_24h = {'symbol': _event.symbol,
                              'open_price': _event.open_price,
                              'close_price': _event.close_price,
                              'event_time': _event.event_time}
                # logger.info(f"OnTickerUpdate.event: {_event.symbol}, ticker_24h: {ticker_24h}")
                json_format.ParseDict(ticker_24h, response)
                yield response
                _queue.task_done()

    async def OnOrderBookUpdate(self, request: api_pb2.MarketRequest,
                                _context: grpc.aio.ServicerContext) -> api_pb2.FetchOrderBookResponse:
        response = api_pb2.FetchOrderBookResponse()
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
            response.Clear()
            _event = await _queue.get()
            while not _queue.empty():
                _queue.get_nowait()
                _queue.task_done()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnOrderBookUpdate: Stop loop for {open_client.name}: {request.symbol}")
                return
            else:
                response.lastUpdateId = _event.last_update_id
                [response.bids.append(json.dumps(bid)) for bid in _event.bids]
                [response.asks.append(json.dumps(ask)) for ask in _event.asks]
                yield response
                _queue.task_done()

    async def OnFundsUpdate(self, request: api_pb2.OnFundsUpdateRequest,
                            _context: grpc.aio.ServicerContext) -> api_pb2.OnFundsUpdateResponse:
        response = api_pb2.OnFundsUpdateResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        client.events.register_user_event(functools.partial(
            event_handler, _queue, client, request.trade_id, 'outboundAccountPosition'),
            'outboundAccountPosition')
        while True:
            response.Clear()
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnFundsUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            else:
                # logger.debug(f"OnFundsUpdate: {client.exchange}:{_event.balances.items()}")
                response.funds = json.dumps(_event.balances)
                yield response
                _queue.task_done()

    async def OnBalanceUpdate(self, request: api_pb2.MarketRequest,
                              _context: grpc.aio.ServicerContext) -> api_pb2.OnBalanceUpdateResponse:
        response = api_pb2.OnBalanceUpdateResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.stream_queue[request.trade_id] |= {_queue}
        if client.exchange in ('binance', 'okx'):
            client.events.register_user_event(functools.partial(
                event_handler, _queue, client, request.trade_id, 'balanceUpdate'), 'balanceUpdate')
        _events = []
        while True:
            response.Clear()
            _events.clear()
            try:
                _event = await asyncio.wait_for(_queue.get(), timeout=HEARTBEAT * 30)
                if isinstance(_event, str) and _event == request.trade_id:
                    client.stream_queue.get(request.trade_id, set()).discard(_queue)
                    logger.info(f"OnBalanceUpdate: Stop user stream for {open_client.name}:{request.symbol}")
                    return
                _events.append(_event)
                _get_event_from_queue = True
            except asyncio.TimeoutError:
                _get_event_from_queue = False

                if client.exchange in ('bitfinex', 'huobi', 'bybit'):
                    await self.rate_limit_control(open_client)
                    try:
                        balances = await client.fetch_ledgers(request.symbol)
                    except Exception as _ex:
                        logger.warning(f"OnBalanceUpdate: for {open_client.name}:{request.symbol}:"
                                       f" {_ex}: {traceback.format_exc()}")
                    else:
                        open_client.ts_rlc = time.time()
                        [_events.append(client.events.wrap_event(balance)) for balance in balances]

            for _event in _events:
                if _event.asset in request.symbol:
                    balance = {
                        "event_time": _event.event_time,
                        "asset": _event.asset,
                        "balance_delta": _event.balance_delta,
                        "clear_time": _event.clear_time
                    }

                    logger.debug(f"OnBalanceUpdate: {open_client.name}:{request.symbol}: {balance}")

                    response.balance = json.dumps(balance)
                    yield response

                if _get_event_from_queue:
                    _queue.task_done()

    async def OnOrderUpdate(self, request: api_pb2.MarketRequest,
                            _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        response = api_pb2.SimpleResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE)
        client.on_order_update_queues.update({request.trade_id: _queue})
        client.stream_queue[request.trade_id] |= {_queue}
        client.events.register_user_event(functools.partial(
            event_handler, _queue, client, request.trade_id, 'executionReport'),
            'executionReport')
        while True:
            response.Clear()
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnOrderUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            else:
                event = vars(_event)
                # logger.info(f"OnOrderUpdate: {event}")
                event.pop('handlers', None)
                response.success = True
                response.result = json.dumps(str(event))
                yield response
                _queue.task_done()

    async def CreateLimitOrder(self, request: api_pb2.CreateLimitOrderRequest,
                               _context: grpc.aio.ServicerContext) -> api_pb2.CreateLimitOrderResponse:
        response = api_pb2.CreateLimitOrderResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        # logger.info(f"CreateLimitOrder: quantity: {request.quantity}, price: {request.price}")
        try:
            res = await client.create_order(
                request.trade_id,
                request.symbol,
                Side.BUY if request.buy_side else Side.SELL,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                quantity=request.quantity,
                quote_order_quantity=None,
                price=request.price,
                new_client_order_id=request.new_client_order_id,
                stop_price=None,
                iceberg_quantity=None,
                response_type=ResponseType.RESULT.value,
                receive_window=None,
                test=False)
        except errors.HTTPError as ex:
            logger.error(f"CreateLimitOrder for {open_client.name}:{request.symbol}:{request.new_client_order_id}"
                         f" exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        except Exception as ex:
            logger.error(f"CreateLimitOrder for {open_client.name}:{request.symbol} exception: {ex}")
            logger.debug(f"CreateLimitOrder for {open_client.name}:{request.symbol} error: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            if not res and client.exchange in ('binance', 'huobi', 'okx'):
                res = await client.fetch_order(symbol=request.symbol,
                                               order_id=None,
                                               origin_client_order_id=request.new_client_order_id,
                                               receive_window=None,
                                               response_type=False)
            json_format.ParseDict(res, response)
            logger.debug(f"CreateLimitOrder: for {open_client.name}:{request.symbol}: created: {res.get('orderId')}")
        return response

    async def CancelOrder(self, request: api_pb2.CancelOrderRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.CancelOrderResponse:
        response = api_pb2.CancelOrderResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        try:
            res = await client.cancel_order(
                request.trade_id,
                request.symbol,
                order_id=request.order_id,
                origin_client_order_id=None,
                new_client_order_id=None,
                receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except errors.RateLimitReached as ex:
            Martin.rate_limit_reached_time = time.time()
            logger.warning(f"CancelOrder for {open_client.name}:{request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
        except Exception as ex:
            logger.error(f"CancelOrder for {open_client.name}:{request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            json_format.ParseDict(res, response)
        return response

    async def TransferToMaster(self, request: api_pb2.MarketRequest,
                               _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        response = api_pb2.SimpleResponse()
        response.success = False
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        await self.rate_limit_control(open_client)
        try:
            res = await client.transfer_to_master(symbol=request.symbol, quantity=request.amount)
        except errors.HTTPError as ex:
            logger.error(f"TransferToMaster for {open_client.name}: {request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
        except Exception as ex:
            logger.error(f"TransferToMaster for {open_client.name}: {request.symbol} exception: {ex}")
            # logger.debug(f"TransferToMaster for {open_client.name}: {request.symbol} error: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            open_client.ts_rlc = time.time()
            if res and res.get("txnId"):
                response.success = True
            response.result = json.dumps(res)
        return response

    async def StartStream(self, request: api_pb2.StartStreamRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        if request.update_max_queue_size:
            global MAX_QUEUE_SIZE
            MAX_QUEUE_SIZE += int(MAX_QUEUE_SIZE / 10)
            logger.info(f"MAX_QUEUE_SIZE was updated: new value is {MAX_QUEUE_SIZE}")
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.SimpleResponse()
        _market_stream_count = 0
        while _market_stream_count < request.market_stream_count:
            await asyncio.sleep(HEARTBEAT)
            _market_stream_count = sum(len(k) for k in ([list(i.get(request.trade_id, []))
                                                         for i in list(client.events.registered_streams.values())]))
        logger.info(f"Start WS streams for {open_client.name}")
        await client.start_market_events_listener(request.trade_id)
        await client.start_user_events_listener(request.trade_id, request.symbol)
        response.success = True
        return response

    async def StopStream(self, request: api_pb2.MarketRequest,
                         _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        response = api_pb2.SimpleResponse()
        if open_client := OpenClient.get_client(request.client_id):
            client = open_client.client
            logger.info(f"StopStream request for {request.symbol} on {client.exchange}")
            await stop_stream(client, request.trade_id)
            response.success = True
        else:
            response.success = False
        return response

    async def CheckStream(self, request: api_pb2.MarketRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        response = api_pb2.SimpleResponse()
        if open_client := OpenClient.get_client(request.client_id):
            client = open_client.client
            response.success = bool(client.data_streams.get(request.trade_id))
        else:
            response.success = False
        if not response.success:
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
    # with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


async def serve() -> None:
    port = 50051
    listen_addr = f"localhost:{port}"
    if is_port_in_use(port):
        raise SystemExit(f"gRPC server port {port} already used")
    server = grpc.aio.server()
    api_pb2_grpc.add_MartinServicer_to_server(Martin(), server)
    server.add_insecure_port(listen_addr)
    logger.info(f"Starting server v:{__version__} on {listen_addr}")
    await server.start()
    await server.wait_for_termination()


async def stop_tasks(loop):
    for task in asyncio.all_tasks(loop):
        if all(item in task.get_name() for item in ['keepalive', 'heartbeat']) and not task.done():
            task.cancel()


def main():
    loop = asyncio.new_event_loop()
    loop.create_task(serve())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(stop_tasks(loop))
        loop.close()


if __name__ == '__main__':
    main()
