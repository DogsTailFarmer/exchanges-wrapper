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
from exchanges_wrapper import events, errors, api_pb2, api_pb2_grpc
from exchanges_wrapper.client import Client
from exchanges_wrapper.definitions import Side, OrderType, TimeInForce, ResponseType
from exchanges_wrapper.c_structures import OrderUpdateEvent, OrderTradesEvent
from exchanges_wrapper import WORK_PATH, CONFIG_FILE, LOG_FILE
#
HEARTBEAT = 1  # Sec
MAX_QUEUE_SIZE = 50
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
    res = ()
    for account in accounts:
        if account.get('name') == _account_name:
            exchange = account['exchange']
            sub_account = account.get('sub_account_name')
            test_net = account['test_net']
            master_email = account.get('master_email')
            master_name = account.get('master_name')
            #
            api_key = account['api_key']
            api_secret = account['api_secret']
            passphrase = account.get('passphrase')
            two_fa = account.get('two_fa')
            #
            endpoint = config['endpoint'][exchange]
            #
            api_public = endpoint['api_public']
            ws_public = endpoint['ws_public']
            api_auth = endpoint['api_test'] if test_net else endpoint['api_auth']
            ws_auth = endpoint['ws_test'] if test_net else endpoint['ws_auth']
            ws_public_mbr = endpoint.get('ws_public_mbr')
            ws_api = endpoint.get('ws_api_test') if test_net else endpoint.get('ws_api')
            #
            exchange = 'binance' if exchange == 'binance_us' else exchange
            #
            res = (exchange,        # 0
                   sub_account,     # 1
                   test_net,        # 2
                   api_key,         # 3
                   api_secret,      # 4
                   api_public,      # 5
                   ws_public,       # 6
                   api_auth,        # 7
                   ws_auth,         # 8
                   ws_public_mbr,   # 9
                   passphrase,      # 10
                   master_email,    # 11
                   master_name,     # 12
                   two_fa,          # 13
                   ws_api,          # 14
                   )
            break
    return res


class OpenClient:
    open_clients = []

    def __init__(self, _account_name: str):
        account = get_account(_account_name)
        if account:
            self.name = _account_name
            self.real_market = not account[2]
            self.client = Client(*account)
            OpenClient.open_clients.append(self)
        else:
            raise UserWarning

    @classmethod
    def get_id(cls, _account_name):
        _id = 0
        for client in cls.open_clients:
            if client.name == _account_name:
                _id = id(client)
                break
        return _id

    @classmethod
    def get_client(cls, _id):
        _client = None
        for client in cls.open_clients:
            if id(client) == _id:
                _client = client
                break
        return _client

    @classmethod
    def remove_client(cls, _account_name):
        cls.open_clients[:] = [i for i in cls.open_clients if i.name != _account_name]


# noinspection PyPep8Naming,PyMethodMayBeStatic
class Martin(api_pb2_grpc.MartinServicer):
    rate_limit_reached_time = None
    rate_limiter = None

    async def OpenClientConnection(self, request: api_pb2.OpenClientConnectionRequest,
                                   _context: grpc.aio.ServicerContext) -> api_pb2.OpenClientConnectionId:
        logger.info(f"OpenClientConnection start trade: {request.account_name}:{request.trade_id}")
        client_id = OpenClient.get_id(request.account_name)
        if not client_id:
            try:
                open_client = OpenClient(request.account_name)
                client_id = id(open_client)
                if open_client.client.master_name == 'Huobi':
                    # For HuobiPro get master account uid and account_id
                    main_account = get_account(open_client.client.master_name)
                    main_client = Client(*main_account)
                    await main_client.fetch_exchange_info()
                    if main_client.hbp_uid and main_client.hbp_account_id:
                        open_client.client.hbp_main_uid = main_client.hbp_uid
                        open_client.client.hbp_main_account_id = main_client.hbp_account_id
                        logger.info(f"The values for main Huobi account were received and set:"
                                    f" UID: {main_client.hbp_uid} and account ID: {main_client.hbp_account_id}")
                    else:
                        logger.warning("No account IDs were received for the Huobi master account")
                    await main_client.close()
            except UserWarning:
                _context.set_details(f"Account {request.account_name} not registered into"
                                     f" {WORK_PATH}/config/exch_srv_cfg.toml")
                _context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            else:
                try:
                    await open_client.client.load()
                except asyncio.CancelledError:
                    pass  # Task cancellation should not be logged as an error
                except Exception as ex:
                    logger.warning(f"OpenClientConnection for '{open_client.name}' exception: {ex}")
                    logger.debug(f"Exception traceback: {traceback.format_exc()}")
                    _context.set_details(f"{ex}")
                    _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                    await OpenClient.get_client(client_id).client.session.close()
                    OpenClient.remove_client(request.account_name)
                    client_id = None
        else:
            OpenClient.get_client(client_id).client.http.rate_limit_reached = False
        if client_id:
            exchange = OpenClient.get_client(client_id).client.exchange
            # Set rate_limiter
            Martin.rate_limiter = max(Martin.rate_limiter if Martin.rate_limiter else 0, request.rate_limiter)
            return api_pb2.OpenClientConnectionId(client_id=client_id, srv_version=__version__, exchange=exchange)

    async def FetchServerTime(self, request: api_pb2.OpenClientConnectionId,
                              _context: grpc.aio.ServicerContext) -> api_pb2.FetchServerTimeResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        try:
            res = await client.fetch_server_time()
        except Exception as ex:
            logger.error(f"FetchServerTime for {open_client.name} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            server_time = res.get('serverTime')
            return api_pb2.FetchServerTimeResponse(server_time=server_time)

    async def ResetRateLimit(self, request: api_pb2.OpenClientConnectionId,
                             _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        Martin.rate_limiter = max(Martin.rate_limiter if Martin.rate_limiter else 0, request.rate_limiter)
        _success = False
        client = OpenClient.get_client(request.client_id).client
        if Martin.rate_limit_reached_time:
            if time.time() - Martin.rate_limit_reached_time > 30:
                client.http.rate_limit_reached = False
                Martin.rate_limit_reached_time = None
                logger.info("RateLimit error clear, trying one else time")
                _success = True
        else:
            if client.http.rate_limit_reached:
                Martin.rate_limit_reached_time = time.time()
        return api_pb2.SimpleResponse(success=_success)

    async def FetchOpenOrders(self, request: api_pb2.MarketRequest,
                              _context: grpc.aio.ServicerContext) -> api_pb2.FetchOpenOrdersResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        # message list
        response = api_pb2.FetchOpenOrdersResponse()
        # Nested dict
        response_order = api_pb2.FetchOpenOrdersResponse.Order()
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                }
                res = await client.user_wss_session.handle_request(
                    "openOrders.status",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.fetch_open_orders(symbol=request.symbol, receive_window=None)
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
            active_orders = []
            for order in res:
                active_orders.append(order['orderId'])
                new_order = json_format.ParseDict(order, response_order)
                # logger.debug(f"FetchOpenOrders.new_order: {new_order}")
                response.items.append(new_order)
                if client.exchange == 'bitfinex':
                    client.active_orders.update(
                        {order['orderId']:
                            {'filledTime': int(),
                             'origQty': order['origQty'],
                             'executedQty': order['executedQty'],
                             'lastEvent': (),
                             'cancelled': False
                             }
                         }
                    )
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
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                    "orderId": request.order_id,
                }
                res = await client.user_wss_session.handle_request(
                    "order.status",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.fetch_order(symbol=request.symbol,
                                               order_id=request.order_id,
                                               origin_client_order_id=None,
                                               receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.error(f"FetchOrders for {open_client.name}: {request.symbol} exception: {_ex}")
        else:
            if _queue and request.filled_update_call:
                if res.get('status') == 'FILLED':
                    event = OrderUpdateEvent(res)
                    logger.info(f"FetchOrder.event: {open_client.name}:{event.symbol}:{event.order_id}:"
                                f"{event.order_status}")
                    _event = weakref.ref(event)
                    await _queue.put(_event())
                elif res.get('status') == 'PARTIALLY_FILLED':
                    try:
                        trades = await client.fetch_order_trade_list(symbol=request.symbol, order_id=request.order_id)
                    except asyncio.CancelledError:
                        pass  # Task cancellation should not be logged as an error
                    except Exception as _ex:
                        logger.error(f"Fetch order trades for {open_client.name}: {request.symbol} exception: {_ex}")
                    else:
                        logger.debug(f"FetchOrder.trades: {trades}")
                        for trade in trades:
                            event = OrderTradesEvent(trade)
                            _event = weakref.ref(event)
                            await _queue.put(_event())
            json_format.ParseDict(res, response)
        return response

    async def CancelAllOrders(self, request: api_pb2.MarketRequest,
                              _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse():
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.SimpleResponse()
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                }
                res = await client.user_wss_session.handle_request(
                    "openOrders.cancelAll",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.cancel_all_orders(symbol=request.symbol, receive_window=None)
            # logger.info(f"CancelAllOrders: {res}")
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as ex:
            logger.error(f"CancelAllOrder for {open_client.name}:{request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
            response.success = True
            response.result = json.dumps(str(res))
        return response

    async def FetchExchangeInfoSymbol(self, request: api_pb2.MarketRequest,
                                      _context: grpc.aio.ServicerContext
                                      ) -> api_pb2.FetchExchangeInfoSymbolResponse:
        client = OpenClient.get_client(request.client_id).client
        response = api_pb2.FetchExchangeInfoSymbolResponse()
        exchange_info = await client.fetch_exchange_info()
        exchange_info_symbol = {}
        try:
            exchange_info_symbol = next(item for item in exchange_info.get('symbols')
                                        if item["symbol"] == request.symbol)
        except StopIteration:
            logger.info("FetchExchangeInfoSymbol.exchange_info_symbol: None")
        # logger.info(f"exchange_info_symbol: {exchange_info_symbol}")
        filters_res = exchange_info_symbol.pop('filters', [])
        json_format.ParseDict(exchange_info_symbol, response)
        # logger.info(f"filters: {filters_res}")
        filters = response.filters
        for _filter in filters_res:
            if _filter.get('filterType') == 'PRICE_FILTER':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.PriceFilter()
                filters.price_filter.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif 'PERCENT_PRICE' in _filter.get('filterType'):
                if _filter.get('filterType') == 'PERCENT_PRICE_BY_SIDE':
                    _filter['multiplierUp'] = _filter['bidMultiplierUp']
                    _filter['multiplierDown'] = _filter['bidMultiplierDown']
                    _filter.pop('bidMultiplierUp')
                    _filter.pop('bidMultiplierDown')
                    _filter.pop('askMultiplierUp')
                    _filter.pop('askMultiplierDown')
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.PercentPrice()
                filters.percent_price.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'LOT_SIZE':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.LotSize()
                filters.lot_size.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'MIN_NOTIONAL':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MinNotional()
                filters.min_notional.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'NOTIONAL':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.Notional()
                filters.notional.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'ICEBERG_PARTS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.IcebergParts()
                filters.iceberg_parts.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'MARKET_LOT_SIZE':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MarketLotSize()
                filters.market_lot_size.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'MAX_NUM_ORDERS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumOrders()
                filters.max_num_orders.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'MAX_NUM_ICEBERG_ORDERS':
                new_filter_template = api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumIcebergOrders()
                filters.max_num_iceberg_orders.CopyFrom(json_format.ParseDict(_filter, new_filter_template))
            elif _filter.get('filterType') == 'MAX_POSITION':
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
        account_information = None
        if client.exchange == 'binance':
            account_information = await client.user_wss_session.handle_request(
                "account.status",
                api_key=True,
                signed=True
            )
        if account_information is None:
            account_information = await client.fetch_account_information(receive_window=None)
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
        res = []
        if client.exchange in ('bitfinex', 'okx') or (open_client.real_market and client.exchange == 'binance'):
            try:
                res = await client.fetch_funding_wallet(asset=request.asset,
                                                        need_btc_valuation=request.need_btc_valuation,
                                                        receive_window=request.receive_window)
            except AttributeError:
                logger.error("Can't get Funding Wallet balances")
        logger.debug(f"funding_wallet: {res}")
        for balance in res:
            new_balance = json_format.ParseDict(balance, response_balance)
            response.balances.extend([new_balance])
        return response

    async def FetchOrderBook(self, request: api_pb2.MarketRequest,
                             _context: grpc.aio.ServicerContext) -> api_pb2.FetchOrderBookResponse:
        client = OpenClient.get_client(request.client_id).client
        response = api_pb2.FetchOrderBookResponse()
        limit = 1 if client.exchange in ('bitfinex', 'okx') else 5
        res = await client.fetch_order_book(symbol=request.symbol, limit=limit)
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
        client = OpenClient.get_client(request.client_id).client
        response = api_pb2.FetchSymbolPriceTickerResponse()
        res = await client.fetch_symbol_price_ticker(symbol=request.symbol)
        json_format.ParseDict(res, response)
        return response

    async def FetchTickerPriceChangeStatistics(
            self, request: api_pb2.MarketRequest,
            _context: grpc.aio.ServicerContext) -> api_pb2.FetchTickerPriceChangeStatisticsResponse:
        client = OpenClient.get_client(request.client_id).client
        response = api_pb2.FetchTickerPriceChangeStatisticsResponse()
        res = await client.fetch_ticker_price_change_statistics(symbol=request.symbol)
        json_format.ParseDict(res, response)
        return response

    async def FetchKlines(self, request: api_pb2.FetchKlinesRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.FetchKlinesResponse:
        client = OpenClient.get_client(request.client_id).client
        response = api_pb2.FetchKlinesResponse()
        try:
            res = await client.fetch_klines(symbol=request.symbol, interval=request.interval,
                                            start_time=None, end_time=None, limit=request.limit)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.error(f"FetchKlines for {request.symbol} interval: {request.interval}, exception: {_ex}")
        else:
            # logger.info(f"FetchKlines.res: {res}")
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

    async def FetchAccountTradeList(self, request: api_pb2.AccountTradeListRequest,
                                    _context: grpc.aio.ServicerContext) -> api_pb2.AccountTradeListResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = api_pb2.AccountTradeListResponse()
        response_trade = api_pb2.AccountTradeListResponse.Trade()
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                    "startTime": request.start_time,
                    "limit": request.limit,
                }
                res = await client.user_wss_session.handle_request(
                    "myTrades",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.fetch_account_trade_list(
                    symbol=request.symbol,
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
                # logger.info(f"OnTickerUpdate.event: {_event.symbol}, _event.close_price: {_event.close_price}")
                ticker_24h = {'symbol': _event.symbol,
                              'open_price': _event.open_price,
                              'close_price': _event.close_price,
                              'event_time': _event.event_time}
                json_format.ParseDict(ticker_24h, response)
                yield response

    async def OnOrderBookUpdate(self, request: api_pb2.MarketRequest,
                                _context: grpc.aio.ServicerContext) -> api_pb2.FetchOrderBookResponse:
        response = api_pb2.FetchOrderBookResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = asyncio.Queue(MAX_QUEUE_SIZE * 2)
        client.stream_queue[request.trade_id] |= {_queue}
        if client.exchange == 'okx':
            _symbol = client.symbol_to_okx(request.symbol)
        elif client.exchange == 'bitfinex':
            _symbol = client.symbol_to_bfx(request.symbol)
        else:
            _symbol = request.symbol.lower()
        _event_type = f"{_symbol}@depth5"
        client.events.register_event(functools.partial(event_handler, _queue, client, request.trade_id, _event_type),
                                     _event_type, client.exchange, request.trade_id)
        while True:
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnOrderBookUpdate: Stop loop for {open_client.name}: {request.symbol}")
                return
            else:
                response.Clear()
                response.lastUpdateId = _event.last_update_id
                for bid in _event.bids:
                    response.bids.append(json.dumps(bid))
                for ask in _event.asks:
                    response.asks.append(json.dumps(ask))
                yield response

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
            _event = await _queue.get()
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnFundsUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            else:
                # logger.debug(f"OnFundsUpdate: {client.exchange}:{_event.balances.items()}")
                response.funds = json.dumps(_event.balances)
                yield response

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
        while True:
            try:
                _event = await asyncio.wait_for(_queue.get(), timeout=HEARTBEAT * 10)
            except asyncio.TimeoutError:
                _event = None
            if isinstance(_event, str) and _event == request.trade_id:
                client.stream_queue.get(request.trade_id, set()).discard(_queue)
                logger.info(f"OnBalanceUpdate: Stop user stream for {open_client.name}:{request.symbol}")
                return
            if client.exchange in ('bitfinex', 'huobi'):
                try:
                    balance = await client.fetch_ledgers(request.symbol)
                except Exception as _ex:
                    logger.warning(f"OnBalanceUpdate: for {open_client.name}:{request.symbol}: {_ex}")
                else:
                    if balance:
                        _event = client.events.wrap_event(balance)
            if isinstance(_event, events.BalanceUpdateWrapper):
                logger.debug(f"OnBalanceUpdate: {open_client.name}:{_event.event_time}:"
                             f"{_event.asset}:{_event.balance_delta}")
                if _event.asset in request.symbol:
                    balance = {
                        "event_time": _event.event_time,
                        "asset": _event.asset,
                        "balance_delta": _event.balance_delta,
                        "clear_time": _event.clear_time
                    }
                    response.balance = json.dumps(balance)
                    yield response

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

    async def CreateLimitOrder(self, request: api_pb2.CreateLimitOrderRequest,
                               _context: grpc.aio.ServicerContext) -> api_pb2.CreateLimitOrderResponse:
        response = api_pb2.CreateLimitOrderResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        # logger.info(f"CreateLimitOrder: quantity: {request.quantity}, price: {request.price}")
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                    "side": 'BUY' if request.buy_side else 'SELL',
                    "type": 'LIMIT',
                    "timeInForce": 'GTC',
                    "price": request.price,
                    "quantity": request.quantity,
                    "newClientOrderId": request.new_client_order_id,
                    "newOrderRespType": 'RESULT',
                }
                res = await client.user_wss_session.handle_request(
                    "order.place",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.create_order(
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
            logger.debug(f"CreateLimitOrder: created: {res.get('orderId')}")
        return response

    async def CancelOrder(self, request: api_pb2.CancelOrderRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.CancelOrderResponse:
        response = api_pb2.CancelOrderResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        try:
            res = None
            if client.exchange == 'binance':
                params = {
                    "symbol": request.symbol,
                    "orderId": request.order_id,
                }
                res = await client.user_wss_session.handle_request(
                    "order.cancel",
                    params,
                    api_key=True,
                    signed=True
                )
            if res is None:
                res = await client.cancel_order(
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
        try:
            res = await client.transfer_to_master(symbol=request.symbol, quantity=request.amount)
        except errors.HTTPError as ex:
            logger.error(f"TransferToMaster for {open_client.name}: {request.symbol} exception: {ex}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
        except Exception as ex:
            logger.error(f"TransferToMaster for {open_client.name}: {request.symbol} exception: {ex}")
            logger.debug(f"TransferToMaster for {open_client.name}: {request.symbol} error: {traceback.format_exc()}")
            _context.set_details(f"{ex}")
            _context.set_code(grpc.StatusCode.UNKNOWN)
        else:
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
        asyncio.create_task(client.start_market_events_listener(request.trade_id))
        asyncio.create_task(client.start_user_events_listener(request.trade_id, request.symbol))
        response.success = True
        return response

    async def StopStream(self, request: api_pb2.MarketRequest,
                         _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        logger.info(f"StopStream request for {request.symbol} on {client.exchange}")
        response = api_pb2.SimpleResponse()
        await stop_stream(client, request.trade_id)
        response.success = True
        return response

    async def CheckStream(self, request: api_pb2.MarketRequest,
                          _context: grpc.aio.ServicerContext) -> api_pb2.SimpleResponse:
        response = api_pb2.SimpleResponse()
        open_client = OpenClient.get_client(request.client_id)
        if open_client:
            client = open_client.client
            response.success = bool(client.data_streams.get(request.trade_id))
        else:
            response.success = False
        if not response.success:
            logger.warning(f"CheckStream request filed for {request.symbol}")
        return response


async def stop_stream(client, trade_id):
    await client.stop_events_listener(trade_id)
    client.events.unregister(client.exchange, trade_id)
    [await _queue.put(trade_id) for _queue in client.stream_queue.get(trade_id, [])]
    client.on_order_update_queues.pop(trade_id, None)
    client.stream_queue.pop(trade_id, None)
    gc.collect(generation=2)


async def event_handler(_queue, client, trade_id, _event_type, event):
    _event = weakref.ref(event)
    try:
        _queue.put_nowait(_event())
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
    logger.info(f"Starting server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()


def main():
    loop = asyncio.new_event_loop()
    loop.create_task(serve())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(asyncio.sleep(0.250))
        loop.close()


if __name__ == '__main__':
    main()
