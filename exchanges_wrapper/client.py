import aiohttp
from enum import Enum
from typing import Union
import decimal
import math
import asyncio
import logging
import time
from collections import defaultdict

from exchanges_wrapper.http_client import ClientBinance, ClientBFX, ClientHBP, ClientOKX
from exchanges_wrapper.errors import ExchangePyError
from exchanges_wrapper.web_sockets import UserEventsDataStream,\
                                            MarketEventsDataStream,\
                                            BfxPrivateEventsDataStream,\
                                            HbpPrivateEventsDataStream,\
                                            OkxPrivateEventsDataStream
from exchanges_wrapper.definitions import OrderType
from exchanges_wrapper.events import Events
import exchanges_wrapper.bitfinex_parser as bfx
import exchanges_wrapper.huobi_parser as hbp
import exchanges_wrapper.okx_parser as okx

logger = logging.getLogger('exch_srv_logger')

STATUS_TIMEOUT = 5  # sec


def truncate(f, n):
    return math.floor(f * 10 ** n) / 10 ** n


class Client:
    def __init__(
        self,
        exchange,
        sub_account,
        test_net,
        api_key,
        api_secret,
        endpoint_api_public,
        endpoint_ws_public,
        endpoint_api_auth,
        endpoint_ws_auth,
        ws_public_mbr=None,
        passphrase=None,
        user_agent=None,
        proxy=str()
    ):
        self.exchange = exchange
        self.sub_account = sub_account
        self.test_net = test_net
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.endpoint_api_public = endpoint_api_public
        self.endpoint_ws_public = endpoint_ws_public
        self.endpoint_api_auth = endpoint_api_auth
        self.endpoint_ws_auth = endpoint_ws_auth
        self.ws_public_mbr = ws_public_mbr
        #
        self.session = aiohttp.ClientSession()
        client_init_params = {
            'api_key': api_key,
            'api_secret': api_secret,
            'passphrase': passphrase,
            'endpoint': endpoint_api_auth,
            'user_agent': user_agent,
            'proxy': proxy,
            'session': self.session,
            'exchange': exchange,
            'sub_account': sub_account,
            'test_net': test_net
        }

        if exchange == 'binance':
            self.http = ClientBinance(**client_init_params)
        elif exchange == 'bitfinex':
            self.http = ClientBFX(**client_init_params)
        elif exchange == 'huobi':
            self.http = ClientHBP(**client_init_params)
        elif exchange == 'okx':
            self.http = ClientOKX(**client_init_params)
        else:
            raise UserWarning(f"Exchange {exchange} not yet connected")

        self.user_agent = user_agent
        self.proxy = proxy
        self.loaded = False
        self.symbols = {}
        self.highest_precision = None
        self.rate_limits = None
        self.data_streams = defaultdict(set)
        self.active_orders = {}
        self.wss_buffer = {}
        self.stream_queue = defaultdict(set)
        self.hbp_account_id = None
        self.ledgers_id = []

    async def load(self):
        infos = await self.fetch_exchange_info()
        if infos.get('serverTime'):
            # load available symbols
            self.highest_precision = 8
            original_symbol_infos = infos["symbols"]
            for symbol_infos in original_symbol_infos:
                symbol = symbol_infos.pop("symbol")
                precision = symbol_infos["baseAssetPrecision"]
                if precision > self.highest_precision:
                    self.highest_precision = precision
                symbol_infos["filters"] = dict(
                    map(lambda x: (x.pop("filterType"), x), symbol_infos["filters"])
                )
                self.symbols[symbol] = symbol_infos
            decimal.getcontext().prec = (
                self.highest_precision + 4
            )  # for operations and rounding
            # load rate limits
            self.rate_limits = infos["rateLimits"]
            self.loaded = True
        else:
            raise UserWarning("Can't get exchange info, check availability and operational status of the exchange")

    async def close(self):
        await self.session.close()

    @property
    def events(self):
        if not hasattr(self, "_events"):
            # noinspection PyAttributeOutsideInit
            self._events = Events()  # skipcq: PYL-W0201
        return self._events

    async def start_user_events_listener(self, _trade_id, symbol):
        logger.info(f"Start '{self.exchange}' user events listener for {_trade_id}")

        user_data_stream = None
        if self.exchange == 'binance':
            user_data_stream = UserEventsDataStream(self,
                                                    self.endpoint_ws_auth,
                                                    self.user_agent,
                                                    self.exchange,
                                                    _trade_id)
        elif self.exchange == 'bitfinex':
            user_data_stream = BfxPrivateEventsDataStream(self,
                                                          self.endpoint_ws_auth,
                                                          self.user_agent,
                                                          self.exchange,
                                                          _trade_id)
        elif self.exchange == 'huobi':
            user_data_stream = HbpPrivateEventsDataStream(self,
                                                          self.endpoint_ws_auth,
                                                          self.user_agent,
                                                          self.exchange,
                                                          _trade_id,
                                                          symbol)
        elif self.exchange == 'okx':
            user_data_stream = OkxPrivateEventsDataStream(self,
                                                          self.endpoint_ws_auth,
                                                          self.user_agent,
                                                          self.exchange,
                                                          _trade_id,
                                                          self.symbol_to_okx(symbol))
        if user_data_stream:
            self.data_streams[_trade_id] |= {user_data_stream}
            await user_data_stream.start()

    async def start_market_events_listener(self, _trade_id):
        _events = self.events.registered_streams.get(self.exchange, {}).get(_trade_id, set())
        start_list = []
        if self.exchange == 'binance':
            market_data_stream = MarketEventsDataStream(self,
                                                        self.endpoint_ws_public,
                                                        self.user_agent,
                                                        self.exchange,
                                                        _trade_id)
            self.data_streams[_trade_id] |= {market_data_stream}
            start_list.append(market_data_stream.start())
        else:
            for channel in _events:
                market_data_stream = MarketEventsDataStream(self,
                                                            self.endpoint_ws_public,
                                                            self.user_agent,
                                                            self.exchange,
                                                            _trade_id,
                                                            channel)
                self.data_streams[_trade_id] |= {market_data_stream}
                start_list.append(market_data_stream.start())
        await asyncio.gather(*start_list, return_exceptions=True)

    async def stop_events_listener(self, _trade_id):
        logger.info(f"Stop events listener data streams for {_trade_id}")
        stopped_data_stream = self.data_streams.pop(_trade_id, set())
        for data_stream in stopped_data_stream:
            await data_stream.stop()

    def assert_symbol_exists(self, symbol):
        if self.loaded and symbol not in self.symbols:
            raise ExchangePyError(f"Symbol {symbol} is not valid according to the loaded exchange infos")

    def symbol_to_bfx(self, symbol) -> str:
        symbol_info = self.symbols.get(symbol)
        base_asset = symbol_info.get('baseAsset')
        quote_asset = symbol_info.get('quoteAsset')
        if len(base_asset) > 3 or len(quote_asset) > 3:
            res = f"t{base_asset}:{quote_asset}"
        else:
            res = f"t{base_asset}{quote_asset}"
        return res

    def symbol_to_okx(self, symbol) -> str:
        symbol_info = self.symbols.get(symbol)
        return f"{symbol_info.get('baseAsset')}-{symbol_info.get('quoteAsset')}"

    def active_orders_clear(self, active_orders: list = None):
        limit_time = int(time.time())
        self.active_orders = {key: val for key, val in self.active_orders.items()
                              if not val['filledTime'] or val['filledTime'] > limit_time}
        for order_id in set(self.active_orders.keys()).difference(set(active_orders)):
            self.active_orders[order_id]['filledTime'] = limit_time + 60 * 30

    def refine_amount(self, symbol, amount: Union[str, decimal.Decimal], quote=False):
        if type(amount) is str:  # to save time for developers
            amount = decimal.Decimal(amount)
        if self.loaded:
            precision = self.symbols[symbol]["baseAssetPrecision"]
            lot_size_filter = self.symbols[symbol]["filters"]["LOT_SIZE"]
            step_size = decimal.Decimal(lot_size_filter["stepSize"])
            # noinspection PyStringFormat
            amount = (
                (f"%.{precision}f" % truncate(amount if quote else (amount - amount % step_size), precision))
                .rstrip("0")
                .rstrip(".")
            )
        return amount

    def refine_price(self, symbol, price: Union[str, decimal.Decimal]) -> decimal.Decimal:
        if isinstance(price, str):  # to save time for developers
            price = decimal.Decimal(price)

        if self.loaded:
            precision = self.symbols[symbol]["baseAssetPrecision"]
            price_filter = self.symbols[symbol]["filters"]["PRICE_FILTER"]
            price = price - (price % decimal.Decimal(price_filter["tickSize"]))
            # noinspection PyStringFormat
            price = (
                (f"%.{precision}f" % truncate(price, precision))
                .rstrip("0")
                .rstrip(".")
            )
        return price

    def assert_symbol(self, symbol):
        if not symbol:
            raise ValueError("This query requires a symbol.")
        self.assert_symbol_exists(symbol)

    # keep support for hardcoded string but allow enums usage
    @staticmethod
    def enum_to_value(enum):
        if isinstance(enum, Enum):
            enum = enum.value
        return enum

    # GENERAL ENDPOINTS

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#test-connectivity
    async def ping(self):
        return await self.http.send_api_call("/api/v3/ping", send_api_key=False)

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#check-server-time
    async def fetch_server_time(self):
        binance_res = {}
        if self.exchange == 'binance':
            binance_res = await self.http.send_api_call("/api/v3/time", send_api_key=False)
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call("v1/common/timestamp")
            binance_res = hbp.fetch_server_time(res)
        elif self.exchange == 'okx':
            res = await self.http.send_api_call("/api/v5/public/time")
            binance_res = okx.fetch_server_time(res)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#exchange-information
    async def fetch_exchange_info(self):
        binance_res = {}
        if self.exchange == 'binance':
            binance_res = await self.http.send_api_call(
                "/api/v3/exchangeInfo",
                send_api_key=False
            )
        elif self.exchange == 'bitfinex':
            symbols_details = await self.http.send_api_call(
                "v1/symbols_details",
                send_api_key=False
            )
            tickers = await self.http.send_api_call(
                "v2/tickers",
                send_api_key=False,
                endpoint=self.endpoint_api_public,
                symbols=bfx.get_symbols(symbols_details)
            )
            if symbols_details and tickers:
                binance_res = bfx.exchange_info(symbols_details, tickers)
        elif self.exchange == 'huobi':
            server_time = await self.fetch_server_time()
            trading_symbols = await self.http.send_api_call("v1/common/symbols")
            if self.hbp_account_id is None:
                accounts = await self.http.send_api_call("v1/account/accounts", signed=True)
                for account in accounts:
                    if account.get('type') == 'spot':
                        self.hbp_account_id = account.get('id')
                        break
            binance_res = hbp.exchange_info(server_time.get('serverTime'), trading_symbols)
        elif self.exchange == 'okx':
            params = {'instType': 'SPOT'}
            server_time = await self.fetch_server_time()
            instruments = await self.http.send_api_call("/api/v5/public/instruments", **params)
            tickers = await self.http.send_api_call("/api/v5/market/tickers", **params)
            binance_res = okx.exchange_info(server_time.get('serverTime'), instruments, tickers)
        return binance_res

    # MARKET DATA ENDPOINTS

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#order-book
    async def fetch_order_book(self, symbol, precision='P0', limit=100):
        self.assert_symbol(symbol)
        valid_limits = []
        if self.exchange == 'binance':
            valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        elif self.exchange == 'bitfinex':
            valid_limits = [1, 25, 100]
        elif self.exchange == 'huobi':
            valid_limits = [5, 10, 20]
        elif self.exchange == 'okx':
            valid_limits = [1, 5, 10, 20, 50, 100, 400]
        binance_res = {}
        if limit in valid_limits:
            if self.exchange == 'binance':
                binance_res = await self.http.send_api_call(
                    "/api/v3/depth",
                    params={"symbol": symbol, "limit": limit},
                    send_api_key=False,
                )
            elif self.exchange == 'bitfinex':
                params = {'len': limit}
                res = await self.http.send_api_call(
                    f"v2/book/{self.symbol_to_bfx(symbol)}/{precision}",
                    endpoint=self.endpoint_api_public,
                    **params
                )
                # print(f"fetch_order_book.res: {res}")
                if res:
                    binance_res = bfx.order_book(res)
            elif self.exchange == 'huobi':
                params = {'symbol': symbol.lower(),
                          'depth': limit,
                          'type': 'step0'}
                res = await self.http.send_api_call(
                    "market/depth",
                    **params
                )
                binance_res = hbp.order_book(res)
            elif self.exchange == 'okx':
                params = {'instId': self.symbol_to_okx(symbol),
                          'sz': str(limit)}
                res = await self.http.send_api_call("/api/v5/market/books", **params)
                binance_res = okx.order_book(res[0])
        else:
            raise ValueError(
                f"{limit} is not a valid limit. Valid limits: {valid_limits}"
            )
        return binance_res

    async def fetch_ledgers(self, symbol, limit=10):
        self.assert_symbol(symbol)
        # From exchange get ledger records about deposit/withdraw/transfer in last 60s time-frame
        if self.exchange == 'bitfinex':
            # https://docs.bitfinex.com/reference/rest-auth-ledgers
            category = [51, 101, 104]
            res = []
            # start = current time - 5min
            for i in category:
                params = {'limit': limit,
                          'category': i,
                          'start': (int(time.time()) - 60) * 1000}
                _res = await self.http.send_api_call(
                    "v2/auth/r/ledgers/hist",
                    method="POST",
                    signed=True,
                    **params
                )
                if _res:
                    res.extend(_res)
                await asyncio.sleep(2)
            for _res in res:
                if _res[1] in symbol and _res[0] not in self.ledgers_id:
                    self.ledgers_id.append(_res[0])
                    if len(self.ledgers_id) > limit*len(category):
                        del self.ledgers_id[0]
                    if _res:
                        binance_res = bfx.on_balance_update(_res)
                        return binance_res
        elif self.exchange == 'huobi':
            params = {'accountId': str(self.hbp_account_id),
                      'limit': limit}
            res = await self.http.send_api_call(
                "v2/account/ledger",
                signed=True,
                **params,
            )
            for res_i in res:
                time_select = (int(time.time() * 1000) - res_i.get('transactTime')) < 1000 * 60
                if (time_select and res_i.get('currency').upper() in symbol and
                        res_i.get('transactId') not in self.ledgers_id):
                    self.ledgers_id.append(res_i.get('transactId'))
                    if len(self.ledgers_id) > limit:
                        del self.ledgers_id[0]
                    binance_res = hbp.on_balance_update(res_i)
                    return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#recent-trades-list
    async def fetch_recent_trades_list(self, symbol, limit=500):
        self.assert_symbol(symbol)
        if limit == 500:
            params = {"symbol": symbol}
        elif 0 < limit <= 1000:
            params = {"symbol": symbol, "limit": limit}
        else:
            raise ValueError(
                f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
            )
        return await self.http.send_api_call(
            "/api/v3/trades", params=params, signed=False
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#old-trade-lookup-market_data
    async def fetch_old_trades_list(self, symbol, from_id=None, limit=500):
        self.assert_symbol(symbol)
        if limit == 500:
            params = {"symbol": symbol}
        elif 0 < limit <= 1000:
            params = {"symbol": symbol, "limit": limit}
        else:
            raise ValueError(
                f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
            )
        if from_id:
            params["fromId"] = from_id
        return await self.http.send_api_call(
            "/api/v3/historicalTrades", params=params, signed=False
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#compressedaggregate-trades-list
    async def fetch_aggregate_trades_list(
        self, symbol, from_id=None, start_time=None, end_time=None, limit=500
    ):
        self.assert_symbol(symbol)
        if limit == 500:
            params = {"symbol": symbol}
        elif 0 < limit <= 1000:
            params = {"symbol": symbol, "limit": limit}
        else:
            raise ValueError(
                f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
            )
        if from_id:
            params["fromId"] = from_id
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self.http.send_api_call(
            "/api/v3/aggTrades", params=params, signed=False
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
    async def fetch_klines(self, symbol, interval, start_time=None, end_time=None, limit=500):
        self.assert_symbol(symbol)
        interval = str(self.enum_to_value(interval))
        if self.exchange == 'huobi':
            interval = hbp.interval(interval)
        elif self.exchange == 'okx':
            interval = okx.interval(interval)
        if not interval:
            raise ValueError("This query requires correct interval value")

        binance_res = []
        if self.exchange == 'binance':
            if limit == 500:
                params = {"symbol": symbol, "interval": interval}
            elif 0 < limit <= 1000:
                params = {"symbol": symbol, "interval": interval, "limit": limit}
            else:
                raise ValueError(
                    f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
                )
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
            binance_res = await self.http.send_api_call(
                "/api/v3/klines", params=params, signed=False
            )
        elif self.exchange == 'bitfinex':
            params = {'limit': limit, 'sort': -1}
            if start_time:
                params["start"] = str(start_time)
            if end_time:
                params["end"] = str(end_time)
            res = await self.http.send_api_call(
                f"v2/candles/trade:{interval}:{self.symbol_to_bfx(symbol)}/hist",
                endpoint=self.endpoint_api_public,
                **params
            )
            if res and isinstance(res, list):
                res.sort(reverse=False)
            if res:
                binance_res = bfx.klines(res, interval)
        elif self.exchange == 'huobi':
            params = {'symbol': symbol.lower(),
                      'period': interval,
                      'size': limit}
            res = await self.http.send_api_call(
                "market/history/kline",
                **params,
            )
            # print(f"fetch_klines.res: {res[::-1]}")
            binance_res = hbp.klines(res[::-1], interval)
        elif self.exchange == 'okx':
            params = {'instId': self.symbol_to_okx(symbol),
                      'bar': interval,
                      'limit': str(min(limit, 300))}
            res = await self.http.send_api_call("/api/v5/market/candles", **params)
            res.sort(reverse=False)
            binance_res = okx.klines(res, interval)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#current-average-price
    async def fetch_average_price(self, symbol):
        self.assert_symbol(symbol)
        return await self.http.send_api_call(
            "/api/v3/avgPrice",
            params={"symbol": symbol},
            signed=False,
            send_api_key=False,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#24hr-ticker-price-change-statistics
    async def fetch_ticker_price_change_statistics(self, symbol=None):
        if symbol:
            self.assert_symbol_exists(symbol)
            binance_res = {}
        else:
            binance_res = []
        if self.exchange == 'binance':
            binance_res = await self.http.send_api_call(
                "/api/v3/ticker/24hr",
                params={"symbol": symbol} if symbol else {},
                signed=False,
                send_api_key=False,
            )
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                f"v2/ticker/{self.symbol_to_bfx(symbol)}",
                endpoint=self.endpoint_api_public
            )
            if res:
                binance_res = bfx.ticker_price_change_statistics(res, symbol)
        elif self.exchange == 'huobi':
            params = {'symbol': symbol.lower()}
            res = await self.http.send_api_call(
                "market/detail/",
                **params
            )
            binance_res = hbp.ticker_price_change_statistics(res, symbol)
        elif self.exchange == 'okx':
            params = {'instId': self.symbol_to_okx(symbol)}
            res = await self.http.send_api_call("/api/v5/market/ticker", **params)
            # print(f"fetch_ticker_price_change_statistics: res: {res}")
            binance_res = okx.ticker_price_change_statistics(res[0])
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#symbol-price-ticker
    async def fetch_symbol_price_ticker(self, symbol=None):
        if symbol:
            self.assert_symbol_exists(symbol)
            binance_res = {}
        else:
            if self.exchange in ('bitfinex', 'huobi'):
                raise ValueError('For fetch_symbol_price_ticker() symbol parameter required')
            binance_res = []
        if self.exchange == 'binance':
            binance_res = await self.http.send_api_call(
                "/api/v3/ticker/price",
                params={"symbol": symbol} if symbol else {},
                signed=False,
                send_api_key=False,
            )
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                f"v2/ticker/{self.symbol_to_bfx(symbol)}",
                endpoint=self.endpoint_api_public
            )
            if res:
                binance_res = bfx.fetch_symbol_price_ticker(res, symbol)
        elif self.exchange == 'huobi':
            params = {'symbol': symbol.lower()}
            res = await self.http.send_api_call(
                "market/trade",
                **params
            )
            binance_res = hbp.fetch_symbol_price_ticker(res, symbol)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#symbol-order-book-ticker
    async def fetch_symbol_order_book_ticker(self, symbol=None):
        if symbol:
            self.assert_symbol_exists(symbol)
        return await self.http.send_api_call(
            "/api/v3/ticker/bookTicker",
            params={"symbol": symbol} if symbol else {},
            signed=False,
            send_api_key=False,
        )

    # ACCOUNT ENDPOINTS

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#new-order--trade
    async def create_order(
        self,
        symbol,
        side,
        order_type,
        time_in_force=None,
        quantity=None,
        quote_order_quantity=None,
        price=None,
        new_client_order_id=None,
        stop_price=None,
        iceberg_quantity=None,
        response_type=None,
        receive_window=None,
        test=False,
    ):
        self.assert_symbol(symbol)
        side = self.enum_to_value(side)
        order_type = self.enum_to_value(order_type)
        if not side:
            raise ValueError("This query requires a side.")
        if not order_type:
            raise ValueError("This query requires an order_type.")
        binance_res = {}
        if self.exchange == 'binance':
            params = {"symbol": symbol, "side": side, "type": order_type}
            if time_in_force:
                params["timeInForce"] = self.enum_to_value(time_in_force)
            elif order_type in [
                OrderType.LIMIT.value,
                OrderType.STOP_LOSS_LIMIT.value,
                OrderType.TAKE_PROFIT_LIMIT.value,
            ]:
                raise ValueError("This order type requires a time_in_force.")
            if quote_order_quantity:
                params["quoteOrderQty"] = self.refine_amount(
                    symbol, quote_order_quantity, True
                )
            if quantity:
                params["quantity"] = self.refine_amount(symbol, quantity)
            elif not quote_order_quantity:
                raise ValueError(
                    "This order type requires a quantity or a quote_order_quantity."
                    if order_type == OrderType.MARKET
                    else "This order type requires a quantity."
                )
            if price:
                params["price"] = self.refine_price(symbol, price)
            elif order_type in [
                OrderType.LIMIT.value,
                OrderType.STOP_LOSS_LIMIT.value,
                OrderType.TAKE_PROFIT_LIMIT.value,
                OrderType.LIMIT_MAKER.value,
            ]:
                raise ValueError("This order type requires a price.")
            if new_client_order_id:
                params["newClientOrderId"] = new_client_order_id
            if stop_price:
                params["stopPrice"] = self.refine_price(symbol, stop_price)
            elif order_type in [
                OrderType.STOP_LOSS.value,
                OrderType.STOP_LOSS_LIMIT.value,
                OrderType.TAKE_PROFIT.value,
                OrderType.TAKE_PROFIT_LIMIT.value,
            ]:
                raise ValueError("This order type requires a stop_price.")
            if iceberg_quantity:
                params["icebergQty"] = self.refine_amount(symbol, iceberg_quantity)
            if response_type:
                params["newOrderRespType"] = response_type
            if receive_window:
                params["recvWindow"] = receive_window
            route = "/api/v3/order/test" if test else "/api/v3/order"
            binance_res = await self.http.send_api_call(route, "POST", data=params, signed=True)
        elif self.exchange == 'bitfinex':
            params = {
                "type": "EXCHANGE LIMIT",
                "symbol": self.symbol_to_bfx(symbol),
                "price": price,
                "amount": str((float(quantity) * (1 if side == 'BUY' else -1))),
                "meta": {"aff_code": "v_4az2nCP"}
            }
            if new_client_order_id:
                params["cid"] = new_client_order_id
            res = await self.http.send_api_call(
                "v2/auth/w/order/submit",
                method="POST",
                signed=True,
                **params,
            )
            logger.debug(f"create_order.res: {res}")
            if res and isinstance(res, list) and res[6] == 'SUCCESS':
                order_id = res[4][0][0]
                ahead_ws = self.wss_buffer.pop(order_id, [])
                logger.debug(f"create_order.ahead_ws: {ahead_ws}")
                binance_res = bfx.order(res[4][0], response_type=False, wss_te=ahead_ws)
                self.active_orders.update(
                    {order_id:
                        {'filledTime': int(),
                         'origQty': quantity,
                         'executedQty': "0",
                         'lastEvent': (),
                         'cancelled': False
                         }
                     }
                )
        elif self.exchange == 'huobi':
            params = {
                'account-id': str(self.hbp_account_id),
                'symbol': symbol.lower(),
                'type': f"{side.lower()}-{order_type.lower()}",
                'amount': quantity,
                'price': price,
                'source': "spot-api"
            }
            if new_client_order_id:
                params["client-order-id"] = str(new_client_order_id)
            count = 0
            res = None
            while count < STATUS_TIMEOUT:
                res = await self.http.send_api_call(
                    "v1/order/orders/place",
                    method="POST",
                    signed=True,
                    timeout=STATUS_TIMEOUT,
                    **params,
                )
                if res:
                    break
                else:
                    count += 1
                    logger.debug(f"RateLimitReached for {symbol}, count {count}, try one else")
            if res:
                binance_res = await self.fetch_order(symbol, order_id=res, response_type=False)
        elif self.exchange == 'okx':
            params = {
                "instId": self.symbol_to_okx(symbol),
                "tdMode": "cash",
                "clOrdId": new_client_order_id,
                "side": side.lower(),
                "ordType": order_type.lower(),
                "sz": quantity,
                "px": price,
            }
            res = await self.http.send_api_call(
                "/api/v5/trade/order",
                method="POST",
                signed=True,
                **params,
            )
            if res[0].get('sCode') == '0':
                binance_res = await self.fetch_order(symbol, order_id=res[0].get('ordId'), response_type=False)
            else:
                raise UserWarning(res[0].get('sMsg'))
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-order-user_data
    async def fetch_order(  # lgtm [py/similar-function]
        self,
        symbol,
        order_id=None,
        origin_client_order_id=None,
        receive_window=None,
        response_type=None,
    ):
        self.assert_symbol(symbol)
        if self.exchange in ('binance', 'huobi', 'okx'):
            if not order_id and not origin_client_order_id:
                raise ValueError(
                    "This query requires an order_id or an origin_client_order_id"
                )
        else:
            if not order_id:
                raise ValueError(
                    "This query requires an order_id"
                )
        binance_res = {}
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            else:
                params["origClientOrderId"] = origin_client_order_id
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/order",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            params = {'id': [order_id]}
            res = await self.http.send_api_call(
                f"v2/auth/r/orders/{self.symbol_to_bfx(symbol)}",
                method="POST",
                signed=True,
                **params
            )
            if not res:
                res = await self.http.send_api_call(
                    f"v2/auth/r/orders/{self.symbol_to_bfx(symbol)}/hist",
                    method="POST",
                    signed=True,
                    **params
                )
            if res:
                binance_res = bfx.order(res[0], response_type=response_type)
        elif self.exchange == 'huobi':
            if origin_client_order_id:
                params = {'clientOrderId': str(origin_client_order_id)}
                res = await self.http.send_api_call("/v1/order/orders/getClientOrder", signed=True, **params)
            else:
                res = await self.http.send_api_call(f"v1/order/orders/{order_id}", signed=True)
            binance_res = hbp.order(res, response_type=response_type)
        elif self.exchange == 'okx':
            params = {'instId': self.symbol_to_okx(symbol),
                      'ordId': str(order_id),
                      'clOrdId': str(origin_client_order_id)}
            res = await self.http.send_api_call("/api/v5/trade/order", signed=True, **params)
            logger.debug(f"fetch_order.res: {res}")
            binance_res = okx.order(res[0], response_type=response_type)
        logger.debug(f"fetch_order.binance_res: {binance_res}")
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-order-trade
    async def cancel_order(  # lgtm [py/similar-function]
        self,
        symbol,
        order_id=None,
        origin_client_order_id=None,
        new_client_order_id=None,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        binance_res = {}
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if not order_id and not origin_client_order_id:
                raise ValueError(
                    "This query requires an order_id or an origin_client_order_id."
                )
            if order_id:
                params["orderId"] = order_id
            if origin_client_order_id:
                params["originClientOrderId"] = origin_client_order_id
            if new_client_order_id:
                params["newClientOrderId"] = origin_client_order_id
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/order",
                "DELETE",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            if not order_id:
                raise ValueError(
                    "This query requires an order_id on Bitfinex. Deletion by user number is not implemented."
                )
            params = {'id': order_id}
            res = await self.http.send_api_call(
                "v2/auth/w/order/cancel",
                method="POST",
                signed=True,
                **params
            )
            if res and isinstance(res, list) and res[6] == 'SUCCESS':
                timeout = STATUS_TIMEOUT / 0.1
                while timeout:
                    timeout -= 1
                    if self.active_orders.get(order_id, {}).get('cancelled', False):
                        binance_res = bfx.order(res[4], response_type=True)
                        binance_res.update({"status": 'CANCELED'})
                        break
                    await asyncio.sleep(0.1)
                logger.debug(f"cancel_order.bitfinex {order_id}: timeout: {timeout}")
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(
                f"v1/order/orders/{order_id}/submitcancel",
                method="POST",
                signed=True
            )
            order_cancelled = False
            timeout = STATUS_TIMEOUT
            while res and not order_cancelled and timeout:
                timeout -= 1
                binance_res = await self.fetch_order(symbol, order_id=res, response_type=True)
                order_cancelled = bool(binance_res.get('status') == 'CANCELED')
                await asyncio.sleep(1)
        elif self.exchange == 'okx':
            params = {
                "instId": self.symbol_to_okx(symbol),
                "ordId": str(order_id),
                "clOrdId": str(origin_client_order_id),
            }
            res = await self.http.send_api_call(
                "/api/v5/trade/cancel-order",
                method="POST",
                signed=True,
                **params,
            )
            if res[0].get('sCode') == '0':
                _canceled_order_id = res[0].get('ordId')
                order_cancelled = False
                timeout = STATUS_TIMEOUT
                while _canceled_order_id and not order_cancelled and timeout:
                    timeout -= 1
                    binance_res = await self.fetch_order(symbol, order_id=_canceled_order_id, response_type=True)
                    order_cancelled = bool(binance_res.get('status') == 'CANCELED')
                    await asyncio.sleep(1)
            else:
                raise UserWarning(res[0].get('sMsg'))
        logger.debug(f"cancel_order.binance_res: {binance_res}")
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-all-open-orders-on-a-symbol-trade
    async def cancel_all_orders(self, symbol, receive_window=None):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/openOrders",
                "DELETE",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            orders = await self.fetch_open_orders(symbol=symbol, receive_window=receive_window)
            orders_id = []
            for order in orders:
                orders_id.append(order.get('orderId'))
            params = {'id': orders_id}
            res = await self.http.send_api_call(
                "v2/auth/w/order/cancel/multi",
                method="POST",
                signed=True,
                **params,
            )
            if res and res[6] == 'SUCCESS':
                binance_res = bfx.orders(res[4], response_type=True)
        elif self.exchange == 'huobi':
            orders_canceled = []
            orders = await self.fetch_open_orders(symbol=symbol, receive_window=receive_window, response_type=True)
            orders_id = []
            for order in orders:
                orders_id.append(str(order.get('orderId')))
            params = {'order-ids': orders_id}
            res = await self.http.send_api_call(
                "v1/order/orders/batchcancel",
                method="POST",
                signed=True,
                **params,
            )
            ids_canceled = res.get('success')
            for order in orders:
                if str(order.get('orderId')) in ids_canceled:
                    orders_canceled.append(order)
            binance_res = orders_canceled
        elif self.exchange == 'okx':
            orders = await self.fetch_open_orders(symbol=symbol, receive_window=receive_window, response_type=True)
            _symbol = self.symbol_to_okx(symbol)
            while orders:
                orders_canceled = []
                params = []
                i = 1
                # 20 is OKX limit fo bulk orders cancel
                for order in orders:
                    orders_canceled.append(order)
                    params.append({'instId': _symbol, 'ordId': order.get('orderId')})
                    if i >= 20:
                        break
                    i += 1
                del orders[:20]
                res = await self.http.send_api_call(
                    "/api/v5/trade/cancel-batch-orders",
                    method="POST",
                    signed=True,
                    data=params,
                )
                ids_canceled = [int(ordr['ordId']) for ordr in res if ordr['sCode'] == '0']
                orders_canceled[:] = [i for i in orders_canceled if i['orderId'] in ids_canceled]
                binance_res.extend(orders_canceled)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#current-open-orders-user_data
    async def fetch_open_orders(self, symbol, receive_window=None, response_type=None):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/openOrders",
                params=params,
                signed=True
            )
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                f"v2/auth/r/orders/{self.symbol_to_bfx(symbol)}",
                method="POST",
                signed=True
            )
            # logger.debug(f"fetch_open_orders.res: {res}")
            if res:
                binance_res = bfx.orders(res)
        elif self.exchange == 'huobi':
            params = {
                'account-id': str(self.hbp_account_id),
                'symbol': symbol.lower()
            }
            res = await self.http.send_api_call(
                "v1/order/openOrders",
                signed=True,
                **params,
            )
            # print(f"fetch_open_orders.res: {res}")
            binance_res = hbp.orders(res, response_type=response_type)
        elif self.exchange == 'okx':
            params = {'instType': 'SPOT'}
            res = await self.http.send_api_call(
                "/api/v5/trade/orders-pending",
                signed=True,
                **params,
            )
            # print(f"fetch_open_orders.res: {res}")
            binance_res = okx.orders(res, response_type=response_type)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#all-orders-user_data
    async def fetch_all_orders(
        self,
        symbol,
        order_id=None,
        start_time=None,
        end_time=None,
        limit=500,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        if limit == 500:
            params = {"symbol": symbol}
        elif 0 < limit <= 1000:
            params = {"symbol": symbol, "limit": limit}
        else:
            raise ValueError(
                f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
            )
        if order_id:
            params["orderId"] = order_id
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if receive_window:
            params["recvWindow"] = receive_window
        return await self.http.send_api_call(
            "/api/v3/allOrders",
            params=params,
            signed=True,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#new-oco-trade
    async def create_oco(
        self,
        symbol,
        side,
        quantity,
        price,
        stop_price,
        list_client_order_id=None,
        limit_iceberg_quantity=None,
        stop_client_order_id=None,
        stop_limit_price=None,
        stop_iceberg_quantity=None,
        stop_limit_time_in_force=None,
        response_type=None,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        side = self.enum_to_value(side)
        if not side:
            raise ValueError("This query requires a side.")
        if not quantity:
            raise ValueError("This query requires a quantity.")
        if not price:
            raise ValueError("This query requires a price.")
        if not stop_price:
            raise ValueError("This query requires a stop_price.")

        params = {
            "symbol": symbol,
            "side": side,
            "quantity": self.refine_amount(symbol, quantity),
            "price": self.refine_price(symbol, price),
            "stopPrice": self.refine_price(symbol, stop_price),
            "stopLimitPrice": self.refine_price(symbol, stop_limit_price),
        }

        if list_client_order_id:
            params["listClientOrderId"] = list_client_order_id
        if limit_iceberg_quantity:
            params["limitIcebergQty"] = self.refine_amount(
                symbol, limit_iceberg_quantity
            )
        if stop_client_order_id:
            params["stopLimitPrice"] = self.refine_price(symbol, stop_client_order_id)
        if stop_iceberg_quantity:
            params["stopIcebergQty"] = self.refine_amount(symbol, stop_iceberg_quantity)
        if stop_limit_time_in_force:
            params["stopLimitTimeInForce"] = stop_limit_time_in_force
        if response_type:
            params["newOrderRespType"] = response_type
        if receive_window:
            params["recvWindow"] = receive_window

        return await self.http.send_api_call(
            "/api/v3/order/oco", "POST", data=params, signed=True
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-oco-user_data
    async def fetch_oco(  # lgtm [py/similar-function]
        self,
        symbol,
        order_list_id=None,
        origin_client_order_id=None,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        params = {"symbol": symbol}
        if not order_list_id and not origin_client_order_id:
            raise ValueError(
                "This query requires an order_id or an origin_client_order_id."
            )
        if order_list_id:
            params["orderListId"] = order_list_id
        if origin_client_order_id:
            params["originClientOrderId"] = origin_client_order_id
        if receive_window:
            params["recvWindow"] = receive_window

        return await self.http.send_api_call(
            "/api/v3/orderList",
            params=params,
            signed=True,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-oco-trade
    async def cancel_oco(  # lgtm [py/similar-function]
        self,
        symbol,
        order_list_id=None,
        list_client_order_id=None,
        new_client_order_id=None,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        params = {"symbol": symbol}
        if not order_list_id and not list_client_order_id:
            raise ValueError(
                "This query requires a order_list_id or a list_client_order_id."
            )
        if order_list_id:
            params["orderListId"] = order_list_id
        if list_client_order_id:
            params["listClientOrderId"] = list_client_order_id
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        if receive_window:
            params["recvWindow"] = receive_window

        return await self.http.send_api_call(
            "/api/v3/order/oco",
            "DELETE",
            params=params,
            signed=True,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-open-oco-user_data
    async def fetch_open_oco(self, receive_window=None):
        params = {}

        if receive_window:
            params["recvWindow"] = receive_window

        return await self.http.send_api_call(
            "/api/v3/openOrderList",
            params=params,
            signed=True,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-all-oco-user_data
    async def fetch_all_oco(
        self,
        from_id=None,
        start_time=None,
        end_time=None,
        limit=None,
        receive_window=None,
    ):
        params = {}

        if from_id:
            params["fromId"] = from_id
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if limit:
            params["limit"] = limit
        if receive_window:
            params["recvWindow"] = receive_window

        return await self.http.send_api_call(
            "/api/v3/allOrderList",
            params=params,
            signed=True,
        )

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-information-user_data
    async def fetch_account_information(self, receive_window=None):
        params = {}
        binance_res = {}
        if self.exchange == 'binance':
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/account",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                "v2/auth/r/wallets",
                method="POST",
                signed=True
            )
            # print(f"fetch_account_information.res: {res}")
            if res:
                binance_res = bfx.account_information(res)
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(f"v1/account/accounts/{self.hbp_account_id}/balance", signed=True)
            binance_res = hbp.account_information(res.get('list'))
        elif self.exchange == 'okx':
            res = await self.http.send_api_call("/api/v5/account/balance", signed=True)
            binance_res = okx.account_information(res[0].get('details'), res[0].get('uTime'))
        return binance_res

    # https://binance-docs.github.io/apidocs/spot/en/#funding-wallet-user_data
    # Not can be used for Spot Test Network, for real SPOT market only
    async def fetch_funding_wallet(self, asset=None, need_btc_valuation=None, receive_window=None):
        binance_res = []
        if self.exchange == 'binance':
            params = {}
            if asset:
                params["asset"] = asset
            if need_btc_valuation:
                params["needBtcValuation"] = "true"
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/sapi/v1/asset/get-funding-asset",
                method="POST",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                "v2/auth/r/wallets",
                method="POST",
                signed=True
            )
            # print(f"fetch_funding_wallet.res: {res}")
            if res:
                binance_res = bfx.funding_wallet(res)
        elif self.exchange == 'okx':
            params = {}
            if asset:
                params = {'ccy': self.symbol_to_okx(asset)}
            res = await self.http.send_api_call("/api/v5/asset/balances", signed=True, **params)
            binance_res = okx.funding_wallet(res)
        return binance_res

    # https://binance-docs.github.io/apidocs/spot/en/#transfer-to-master-for-sub-account
    async def transfer_to_master(self, symbol, quantity, receive_window=None):
        binance_res = {}
        if self.exchange == 'binance':
            params = {"symbol": symbol, "amount": quantity}
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/sapi/v1/sub-account/transfer/subToMaster",
                "POST",
                data=params,
                signed=True
            )
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-trade-list-user_data
    async def fetch_account_trade_list(
        self,
        symbol,
        order_id=None,
        start_time=None,
        end_time=None,
        from_id=None,
        limit=500,
        receive_window=None,
    ):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            if limit == 500:
                params = {"symbol": symbol}
            elif 0 < limit <= 1000:
                params = {"symbol": symbol, "limit": limit}
            else:
                raise ValueError(
                    f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 1000."
                )
            if order_id:
                params["orderId"] = order_id
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
            if from_id:
                params["fromId"] = from_id
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.http.send_api_call(
                "/api/v3/myTrades",
                params=params,
                signed=True,
            )
        elif self.exchange == 'bitfinex':
            params = {'limit': limit, 'sort': -1}
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time
            res = await self.http.send_api_call(
                f"v2/auth/r/trades/{self.symbol_to_bfx(symbol)}/hist",
                method='POST',
                signed=True,
                **params
            )
            # print(f"fetch_account_trade_list.res: {res}")
            if res:
                binance_res = bfx.account_trade_list(res)
            # print(f"fetch_account_trade_list.res: {binance_res}")
        elif self.exchange == 'huobi':
            if limit == 100:
                params = {'symbol': symbol.lower()}
            elif 0 < limit <= 500:
                params = {
                    'size': limit,
                    'symbol': symbol.lower()
                }
            else:
                raise ValueError(f"{limit} is not a valid limit. A valid limit should be > 0 and <= to 500")
            res = await self.http.send_api_call("v1/order/matchresults", signed=True, **params)
            binance_res = hbp.account_trade_list(res)
        elif self.exchange == 'okx':
            params = {'instType': "SPOT",
                      'instId': self.symbol_to_okx(symbol),
                      'limit': str(min(limit, 100))}
            if order_id:
                params["ordId"] = str(order_id)
            if start_time:
                params["begin"] = str(start_time)
            if end_time:
                params["end"] = str(end_time)
            res = await self.http.send_api_call("/api/v5/trade/fills-history", signed=True, **params)
            binance_res = okx.order_trade_list(res)
        logger.debug(f"fetch_account_trade_list.binance_res: {binance_res}")
        return binance_res

    async def fetch_order_trade_list(
        self,
        symbol,
        order_id,
    ):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            binance_res = await self.fetch_account_trade_list(symbol=symbol, order_id=order_id)
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                f"v2/auth/r/order/{self.symbol_to_bfx(symbol)}:{order_id}/trades",
                method='POST',
                signed=True,
            )
            binance_res = bfx.account_trade_list(res)
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(f"v1/order/orders/{order_id}/matchresults", signed=True)
            binance_res = hbp.account_trade_list(res)
        elif self.exchange == 'okx':
            params = {'instType': "SPOT",
                      'instId': self.symbol_to_okx(symbol),
                      'ordId': str(order_id),
                      }
            res = await self.http.send_api_call("/api/v5/trade/fills", signed=True, **params)
            binance_res = okx.order_trade_list(res)
        logger.debug(f"fetch_order_trade_list.binance_res: {binance_res}")
        return binance_res

    # USER DATA STREAM ENDPOINTS

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#create-a-listenkey
    async def create_listen_key(self):
        return await self.http.send_api_call("/api/v3/userDataStream", "POST")

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
    async def keep_alive_listen_key(self, listen_key):
        if not listen_key:
            raise ValueError("This query requires a listen_key.")
        return await self.http.send_api_call(
            "/api/v3/userDataStream", "PUT", params={"listenKey": listen_key}
        )

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
    async def close_listen_key(self, listen_key):
        if not listen_key:
            raise ValueError("This query requires a listen_key.")
        return await self.http.send_api_call(
            "/api/v3/userDataStream", "DELETE", params={"listenKey": listen_key}
        )
