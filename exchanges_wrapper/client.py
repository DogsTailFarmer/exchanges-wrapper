import aiohttp
from enum import Enum
from typing import Union
import decimal
import math
import asyncio
import logging
import time
from collections import defaultdict
import pyotp
from expiringdict import ExpiringDict
import uuid
from decimal import Decimal, ROUND_HALF_DOWN

from exchanges_wrapper.http_client import ClientBinance, ClientBFX, ClientHBP, ClientOKX, ClientBybit
from exchanges_wrapper.errors import ExchangePyError
from exchanges_wrapper.web_sockets import UserEventsDataStream, \
    MarketEventsDataStream, \
    BfxPrivateEventsDataStream, \
    HbpPrivateEventsDataStream, \
    OkxPrivateEventsDataStream, \
    BBTPrivateEventsDataStream
from exchanges_wrapper.events import Events
import exchanges_wrapper.parsers.bitfinex as bfx
import exchanges_wrapper.parsers.huobi as hbp
import exchanges_wrapper.parsers.okx as okx
import exchanges_wrapper.parsers.bybit as bbt
from crypto_ws_api.ws_session import UserWSSession

logger = logging.getLogger(__name__)

STATUS_TIMEOUT = 5  # sec, also use for lifetime limit for inactive order (Bitfinex) as 60 * STATUS_TIMEOUT
USER_DATA_STREAM = "/api/v3/userDataStream"
FALLBACK_WARNING = 'Fallback to HTTP API call due to None response from user WSS session'

def truncate(f, n):
    return math.floor(f * 10 ** n) / 10 ** n


def any2str(_x) -> str:
    return f"{_x:.10f}".rstrip('0').rstrip('.')


class Client:
    def __init__(self, acc: dict):
        self.exchange = acc['exchange']
        self.sub_account = acc['sub_account']
        self.test_net = acc['test_net']
        self.api_key = acc['api_key']
        self.api_secret = acc['api_secret']
        self.passphrase = acc['passphrase']
        self.endpoint_api_public = acc['api_public']
        self.endpoint_ws_public = acc['ws_public']
        self.endpoint_api_auth = acc['api_auth']
        self.endpoint_ws_auth = acc['ws_auth']
        self.endpoint_ws_api = acc['ws_api']
        self.ws_add_on = acc['ws_add_on']
        self.master_email = acc['master_email']
        self.master_name = acc['master_name']
        self.two_fa = acc['two_fa']
        #
        self.session = aiohttp.ClientSession()
        client_init_params = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'passphrase': self.passphrase,
            'endpoint': self.endpoint_api_auth,
            'session': self.session,
            'exchange': self.exchange,
            'sub_account': self.sub_account,
            'test_net': self.test_net
        }
        if self.exchange == 'binance':
            self.http = ClientBinance(client_init_params)
        elif self.exchange == 'bitfinex':
            self.http = ClientBFX(client_init_params)
        elif self.exchange == 'huobi':
            self.http = ClientHBP(client_init_params)
        elif self.exchange == 'okx':
            self.http = ClientOKX(client_init_params)
        elif self.exchange == 'bybit':
            self.http = ClientBybit(client_init_params)
        else:
            raise UserWarning(f"Exchange {self.exchange} not yet connected")

        if self.exchange in ('binance', 'okx', 'bitfinex', 'huobi'):
            self.user_session = UserWSSession(
                self.exchange,
                self.endpoint_ws_api,
                self.api_key,
                self.api_secret,
                self.passphrase,
            )
        else:
            self.user_session = None
        #
        self.loaded = False
        self.symbols = {}
        self.highest_precision = None
        self.rate_limits = None
        self.data_streams = defaultdict(set)
        self.active_orders = {}
        self.wss_buffer = ExpiringDict(max_len=50, max_age_seconds=STATUS_TIMEOUT*20)
        self.stream_queue = defaultdict(set)
        self.on_order_update_queues = {}
        self.account_id = None
        self.account_uid = None
        self.main_account_id = None
        self.main_account_uid = None
        self.ledgers_id = []
        self.ts_start = {}
        self.tasks = set()
        self.request_event = asyncio.Event()
        self.request_event.set()

    def tasks_manage(self, coro):
        _t = asyncio.create_task(coro)
        self.tasks.add(_t)
        _t.add_done_callback(self.tasks.discard)

    async def fetch_object(self, key):
        res = None
        while res is None:
            await asyncio.sleep(0.05)
            res = self.wss_buffer.pop(key, None)
        return res

    async def load(self, symbol):
        logger.info(f"Try load {self.exchange}:{symbol} info...")
        infos = await self.fetch_exchange_info(symbol)
        if not infos.get('serverTime'):
            raise UserWarning("Can't get exchange info, check availability and operational status of the exchange")
        self.ts_start[symbol] = int(time.time() * 1000)
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
        decimal.getcontext().prec = (self.highest_precision + 4)  # for operations and rounding
        if self.exchange == 'bybit':
            # ByBit get main- and subaccount UID
            self.account_uid, self.main_account_uid = await self.fetch_api_info()
            if self.main_account_uid == '0':
                logger.info(f"It is main ByBit account, UID: {self.account_uid}")
            else:
                logger.info(f"Main ByBit account UID: {self.main_account_uid}, sub-UID: {self.account_uid}")
        # load rate limits
        self.rate_limits = infos["rateLimits"]
        self.loaded = True
        logger.info(f"Info for {self.exchange}:{symbol} loaded successfully")

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
            user_data_stream = await UserEventsDataStream(self, self.endpoint_ws_auth, self.exchange, _trade_id)
        elif self.exchange == 'bitfinex':
            user_data_stream = BfxPrivateEventsDataStream(self, self.endpoint_ws_auth, self.exchange, _trade_id)
        elif self.exchange == 'huobi':
            user_data_stream = HbpPrivateEventsDataStream(self, self.endpoint_ws_auth, self.exchange, _trade_id, symbol)
        elif self.exchange == 'okx':
            user_data_stream = OkxPrivateEventsDataStream(
                self,
                self.endpoint_ws_auth,
                self.exchange,
                _trade_id,
                self.symbol_to_okx(symbol)
            )
        elif self.exchange == 'bybit':
            user_data_stream = BBTPrivateEventsDataStream(self, self.endpoint_ws_auth, self.exchange, _trade_id)
        if user_data_stream:
            self.data_streams[_trade_id] |= {user_data_stream}
            self.tasks_manage(user_data_stream.start())
            timeout = STATUS_TIMEOUT / 0.1
            while not user_data_stream.wss_started:
                timeout -= 1
                if not timeout:
                    logger.warning(f"{self.exchange} user WSS start timeout reached for {_trade_id}")
                    break
                await asyncio.sleep(0.05)

    async def start_market_events_listener(self, _trade_id):
        _events = self.events.registered_streams.get(self.exchange, {}).get(_trade_id, set())
        if self.exchange == 'binance':
            market_data_stream = MarketEventsDataStream(self, self.endpoint_ws_public, self.exchange, _trade_id)
            self.data_streams[_trade_id] |= {market_data_stream}
            self.tasks_manage(market_data_stream.start())
        else:
            for channel in _events:
                # https://www.okx.com/help-center/changes-to-v5-api-websocket-subscription-parameter-and-url
                if self.exchange == 'okx' and 'kline' in channel:
                    _endpoint = self.ws_add_on
                else:
                    _endpoint = self.endpoint_ws_public
                #
                market_data_stream = MarketEventsDataStream(self, _endpoint, self.exchange, _trade_id, channel)
                self.data_streams[_trade_id] |= {market_data_stream}
                self.tasks_manage(market_data_stream.start())

    async def stop_events_listener(self, _trade_id):
        logger.info(f"Stop events listener data streams for {_trade_id}")
        stopped_data_stream = self.data_streams.pop(_trade_id, set())
        for data_stream in stopped_data_stream:
            await data_stream.stop()
        if self.user_session:
            await self.user_session.stop()

    def assert_symbol_exists(self, symbol):
        if self.loaded and symbol not in self.symbols:
            raise ExchangePyError(f"Symbol {symbol} is not valid according to the loaded exchange infos")

    def symbol_to_bfx(self, symbol) -> str:
        symbol_info = self.symbols.get(symbol)
        base_asset = symbol_info.get('baseAsset')
        quote_asset = symbol_info.get('quoteAsset')
        return (
            f"t{base_asset}:{quote_asset}"
            if len(base_asset) > 3 or len(quote_asset) > 3
            else f"t{base_asset}{quote_asset}"
        )

    def symbol_to_okx(self, symbol) -> str:
        symbol_info = self.symbols.get(symbol)
        return f"{symbol_info.get('baseAsset')}-{symbol_info.get('quoteAsset')}"

    def active_order(self, order_id: int, quantity="0", executed_qty="0", last_event=None):
        quantity_decimal = Decimal(quantity)
        executed_qty_decimal = Decimal(executed_qty)

        if order_id not in self.active_orders:
            self.active_orders[order_id] = {
                'origQty': quantity_decimal,
                'executedQty': executed_qty_decimal,
                'lastEvent': last_event,
                'eventIds': [],
                'cancelled': False
            }
        else:
            if last_event is not None:
                self.active_orders[order_id]['lastEvent'] = last_event

            if quantity_decimal and not self.active_orders[order_id]["origQty"]:
                self.active_orders[order_id]["origQty"] = quantity_decimal

            if executed_qty_decimal and self.active_orders[order_id]["executedQty"] < executed_qty_decimal:
                self.active_orders[order_id]["executedQty"] = executed_qty_decimal

        self.active_orders[order_id]['lifeTime'] = int(time.time()) + 60 * STATUS_TIMEOUT

    def active_orders_clear(self):
        current_time = int(time.time())
        keys_to_delete = [key for key, val in self.active_orders.items() if val['lifeTime'] <= current_time]
        for key in keys_to_delete:
            del self.active_orders[key]

    def refine_amount(self, symbol, amount: Union[str, Decimal], _quote=False):
        if type(amount) is str:  # to save time for developers
            amount = Decimal(amount)
        if self.loaded:
            precision = self.symbols[symbol]["baseAssetPrecision"]
            lot_size_filter = self.symbols[symbol]["filters"]["LOT_SIZE"]
            step_size = Decimal(lot_size_filter["stepSize"])
            # noinspection PyStringFormat
            amount = (
                (f"%.{precision}f" % truncate(amount if _quote else (amount - amount % step_size), precision))
                .rstrip("0")
                .rstrip(".")
            )
        return amount

    def refine_price(self, symbol, price: Union[str, Decimal]):
        if isinstance(price, str):  # to save time for developers
            price = Decimal(price)

        if self.loaded:
            precision = self.symbols[symbol]["baseAssetPrecision"]
            price_filter = self.symbols[symbol]["filters"]["PRICE_FILTER"]
            price = price - (price % Decimal(price_filter["tickSize"]))
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

    # region GENERAL ENDPOINTS

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
        elif self.exchange == 'bybit':
            res, _ = await self.http.send_api_call("/v5/market/time")
            binance_res = bbt.fetch_server_time(res)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#exchange-information
    async def fetch_exchange_info(self, symbol):
        binance_res = {}
        if self.exchange == 'binance':
            binance_res = await self.http.send_api_call(
                "/api/v3/exchangeInfo",
                params={"symbol": symbol},
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
                symbols=bfx.get_symbols(symbols_details, symbol)
            )
            if symbols_details and tickers:
                binance_res = bfx.exchange_info(symbols_details, tickers, symbol)
        elif self.exchange == 'huobi':
            server_time = await self.fetch_server_time()
            params = {'symbols': symbol.lower()}
            trading_symbol = await self.http.send_api_call("v1/settings/common/market-symbols", **params)
            await self.set_htx_ids()
            binance_res = hbp.exchange_info(server_time.get('serverTime'), trading_symbol[0])
        elif self.exchange == 'okx':
            params = {'instType': 'SPOT'}
            server_time = await self.fetch_server_time()
            instruments = await self.http.send_api_call("/api/v5/public/instruments", **params)
            tickers = await self.http.send_api_call("/api/v5/market/tickers", **params)
            binance_res = okx.exchange_info(server_time.get('serverTime'), instruments, tickers, symbol)
        elif self.exchange == 'bybit':
            params = {'category': 'spot', 'symbol': symbol}
            server_time = await self.fetch_server_time()
            instruments, _ = await self.http.send_api_call("/v5/market/instruments-info", **params)
            binance_res = bbt.exchange_info(server_time.get('serverTime'), instruments.get('list'))
        # logger.info(f"fetch_exchange_info: binance_res: {binance_res}")
        return binance_res

    async def set_htx_ids(self):
        if self.account_id is None:
            accounts = await self.http.send_api_call("v1/account/accounts", signed=True)
            for account in accounts:
                if account.get('type') == 'spot':
                    self.account_id = account.get('id')
                    break
            self.account_uid = await self.http.send_api_call("v2/user/uid", signed=True)

    # MARKET DATA ENDPOINTS

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#order-book
    async def fetch_order_book(self, symbol, precision='P0'):
        self.assert_symbol(symbol)
        limit = 1 if self.exchange in ('bitfinex', 'okx', 'bybit') else 5
        binance_res = {}
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
        elif self.exchange == 'bybit':
            params = {"category": "spot", "symbol": symbol, "limit": limit}
            res, _ = await self.http.send_api_call("/v5/market/orderbook", **params)
            binance_res = bbt.order_book(res)
        return binance_res

    async def fetch_ledgers(self, symbol, limit=25):
        self.assert_symbol(symbol)
        # From exchange get ledger records about deposit/withdraw/transfer in last 60s time-frame
        balances = []
        if self.exchange == 'bitfinex':
            # https://docs.bitfinex.com/reference/rest-auth-ledgers
            category = [51, 101, 104]
            res = []
            # start = current time - 5min
            for i in category:
                params = {'limit': limit,
                          'category': i,
                          'start': max(self.ts_start[symbol], (int(time.time()) - 300) * 1000)}
                _res = await self.http.send_api_call(
                    "v2/auth/r/ledgers/hist",
                    method="POST",
                    signed=True,
                    **params
                )
                if _res:
                    res.extend(_res)
                await asyncio.sleep(1)
            for _res in res:
                if _res[1] in symbol and _res[0] not in self.ledgers_id:
                    self.ledgers_id.append(_res[0])
                    if len(self.ledgers_id) > limit * len(category):
                        self.ledgers_id.pop(0)
                    balances.append(bfx.on_balance_update(_res))
            return balances
        elif self.exchange == 'huobi':
            params = {'accountId': str(self.account_id),
                      'limit': limit}
            res = await self.http.send_api_call(
                "v2/account/ledger",
                signed=True,
                **params,
            )
            for _res in res:
                time_select = ((int(time.time() * 1000) - _res.get('transactTime', 0)) < 1000 * 300 and
                               self.ts_start[symbol] < _res.get('transactTime', 0))
                if (time_select and _res.get('currency').upper() in symbol and
                        _res.get('transactId') not in self.ledgers_id):
                    self.ledgers_id.append(_res.get('transactId'))
                    if len(self.ledgers_id) > limit:
                        self.ledgers_id.pop(0)
                    balances.append(hbp.on_balance_update(_res))
            return balances
        elif self.exchange == 'bybit':
            params = {
                'status': 'SUCCESS',
                'startTime': max(self.ts_start[symbol], (int(time.time()) - 300) * 1000)
            }
            # Internal transfer, ie from Funding to UTA account
            res, ts = await self.http.send_api_call(
                "/v5/asset/transfer/query-inter-transfer-list",
                signed=True,
                **params
            )
            _res = bbt.on_balance_update(res['list'], ts, symbol, 'internal')

            # Universal Transfer Records, ie from Sub account to Main account
            res, ts = await self.http.send_api_call(
                "/v5/asset/transfer/query-universal-transfer-list",
                signed=True,
                **params
            )
            _res += bbt.on_balance_update(
                res['list'],
                ts,
                symbol,
                'universal',
                uid=self.account_uid
            )

            if not _res:
                # Get Transaction Log
                params.pop('status')
                params['accountType'] = 'UNIFIED'
                params['category'] = 'spot'
                params['type'] = 'TRANSFER_IN'

                res, ts = await self.http.send_api_call(
                    "/v5/account/transaction-log",
                    signed=True,
                    **params
                )
                _res += bbt.on_balance_update(
                    res['list'],
                    ts,
                    symbol,
                    'log'
                )

            for i in _res:
                _id = next(iter(i))
                if _id not in self.ledgers_id:
                    self.ledgers_id.append(_id)
                    if len(self.ledgers_id) > limit * 4:
                        self.ledgers_id.pop(0)
                    balances.append(i[_id])
            return balances

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
        elif self.exchange == 'bybit':
            interval = bbt.interval(interval)
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
        elif self.exchange == 'bybit':
            params = {"category": "spot", "symbol": symbol, "interval": interval, "limit": limit}
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time
            res, _ = await self.http.send_api_call("/v5/market/kline", **params)
            res = res.get("list", [])
            res.sort(reverse=False)
            binance_res = bbt.klines(res, interval)
        # print(f"fetch_klines.binance_res: {binance_res}")
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
        elif self.exchange == 'bybit':
            params = {'category': 'spot', 'symbol': symbol}
            res, ts = await self.http.send_api_call("/v5/market/tickers", **params)
            binance_res = bbt.ticker_price_change_statistics(res["list"][0], ts)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#symbol-price-ticker
    async def fetch_symbol_price_ticker(self, symbol=None):
        if symbol:
            if not (self.exchange == 'binance' and symbol == 'BNBUSDT'):
                self.assert_symbol_exists(symbol)
            binance_res = {}
        elif self.exchange in ('bitfinex', 'huobi'):
            raise ValueError('For fetch_symbol_price_ticker() symbol parameter required')
        else:
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
        elif self.exchange == 'okx':
            params = {'instId': self.symbol_to_okx(symbol)}
            res = await self.http.send_api_call("/api/v5/market/ticker", **params)
            binance_res = okx.fetch_symbol_price_ticker(res[0], symbol)
        elif self.exchange == 'bybit':
            params = {'category': 'spot', 'symbol': symbol}
            res, _ = await self.http.send_api_call("/v5/market/tickers", **params)
            binance_res = {
                "symbol": symbol,
                "price": res["list"][0]["lastPrice"]
            }
        # print(f"fetch_symbol_price_ticker: binance_res: {binance_res}")
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
    # endregion

    # region ACCOUNT ENDPOINTS
    # binance-docs.github.io/apidocs/spot/en/#one-click-arrival-deposit-apply-for-expired-address-deposit-user_data
    async def one_click_arrival_deposit(self, tx_id):
        if self.exchange == 'binance':
            params = {"txId": tx_id}
            return await self.http.send_api_call(
                "/sapi/v1/capital/deposit/credit-apply",
                method="POST",
                params=params,
                signed=True,
            )

    async def fetch_api_info(self):
        res, _ = await self.http.send_api_call("/v5/user/query-api", signed=True)
        return int(res["userID"]), int(res["parentUid"])

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#new-order--trade
    async def create_order(
            self,
            trade_id,
            symbol,
            side,
            order_type,
            time_in_force=None,
            quantity=None,
            price=None,
            new_client_order_id=None,
            response_type=None,
            receive_window=None,
            test=False,
    ):
        self.assert_symbol(symbol)
        side = self.enum_to_value(side)
        order_type = self.enum_to_value(order_type)
        binance_res = {}
        if self.exchange == 'binance':
            params = {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": self.refine_amount(symbol, quantity),
                "price": self.refine_price(symbol, price),
                "timeInForce": self.enum_to_value(time_in_force)
            }
            if new_client_order_id:
                params["newClientOrderId"] = new_client_order_id
            if response_type:
                params["newOrderRespType"] = response_type
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.user_session.handle_request(
                trade_id,
                "order.place",
                _params=params,
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
                route = "/api/v3/order/test" if test else "/api/v3/order"
                binance_res = await self.http.send_api_call(route, "POST", data=params, signed=True)
        elif self.exchange == 'bitfinex':
            params = {
                "type": "EXCHANGE LIMIT",
                "symbol": self.symbol_to_bfx(symbol),
                "price": price,
                "amount": ('' if side == 'BUY' else '-') + quantity,
                "meta": {"aff_code": "v_4az2nCP"}
            }
            if new_client_order_id:
                params["cid"] = new_client_order_id
                self.active_order(new_client_order_id, quantity)

            res = await self.user_session.handle_request(trade_id, "on", _params=params)

            if not res or (res and isinstance(res, list) and res[6] != 'SUCCESS'):
                logger.warning(FALLBACK_WARNING)
                logger.debug(f"create_order.bitfinex {new_client_order_id}: {res}")
                res = await self.http.send_api_call(
                    "v2/auth/w/order/submit",
                    method="POST",
                    signed=True,
                    **params
                )
            if res and isinstance(res, list) and res[6] == 'SUCCESS':
                self.active_order(res[4][0][0], quantity)
                binance_res = bfx.order(res[4][0], response_type=False)
            else:
                logger.debug(f"create_order.bitfinex {new_client_order_id}: {res}")
        elif self.exchange == 'huobi':
            params = {
                'account-id': str(self.account_id),
                'symbol': symbol.lower(),
                'type': f"{side.lower()}-{order_type.lower()}",
                'amount': quantity,
                'price': price,
                'source': "spot-api"
            }
            if new_client_order_id:
                params["client-order-id"] = str(new_client_order_id)

            res = await self.user_session.handle_request(trade_id, "create-order", _params=params)

            if res is None:
                logger.warning(FALLBACK_WARNING)
                res = await self.http.send_api_call(
                    "v1/order/orders/place",
                    method="POST",
                    signed=True,
                    timeout=STATUS_TIMEOUT,
                    **params,
                )
            if res:
                timeout = STATUS_TIMEOUT / 0.1
                while not self.active_orders.get(int(res)) and timeout:
                    timeout -= 1
                    await asyncio.sleep(0.1)
                binance_res = await self.fetch_order(trade_id, symbol, order_id=res, response_type=False)
                self.active_order(int(res), quantity, binance_res['executedQty'])
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
            res = await self.user_session.handle_request(trade_id, "order", _params=params)
            if res is None:
                logger.warning(FALLBACK_WARNING)
                res = await self.http.send_api_call(
                    "/api/v5/trade/order",
                    method="POST",
                    signed=True,
                    **params,
                )
            if res[0].get('sCode') == '0':
                binance_res = okx.place_order_response(res[0], params)
            else:
                raise UserWarning(f"Code: {res[0].get('sCode')}: {res[0].get('sMsg')}")
        elif self.exchange == 'bybit':
            params = {
                'category': 'spot',
                'symbol': symbol,
                'side': side.title(),
                'orderType': order_type.title(),
                'qty': quantity,
                'price': price,
                'orderLinkId': str(new_client_order_id),
            }
            res, ts = await self.http.send_api_call("/v5/order/create", method="POST", signed=True, **params)
            if res:
                res["ts"] = ts
                binance_res = bbt.place_order_response(res, params)
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-order-user_data
    async def fetch_order(  # lgtm [py/similar-function]
            self,
            trade_id,
            symbol,
            order_id=None,
            origin_client_order_id=None,
            receive_window=None,
            response_type=None,
    ):
        self.assert_symbol(symbol)
        if not order_id and not origin_client_order_id:
            raise ValueError("This query requires an order_id or an origin_client_order_id")

        b_res = {}
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            else:
                params["origClientOrderId"] = origin_client_order_id
            if receive_window:
                params["recvWindow"] = receive_window
            b_res = await self.user_session.handle_request(
                        trade_id,
                        "order.status",
                        _params=params,
                        send_api_key=True,
                        _signed=True,
                    )
            if b_res is None:
                logger.warning(FALLBACK_WARNING)
                b_res =  await self.http.send_api_call(
                    "/api/v3/order",
                    params=params,
                    signed=True,
                )
        elif self.exchange == 'bitfinex':
            params = {}
            if order_id:
                params['id'] = [order_id]
            _res = await self.http.send_api_call(
                f"v2/auth/r/orders/{self.symbol_to_bfx(symbol)}",
                method="POST",
                signed=True,
                **params
            )
            res = bfx.find_order(_res, order_id, origin_client_order_id)
            if not res:
                if not order_id:
                    params['start'] = int(time.time() * 1000) - 600000  # 10 mins
                _res = await self.http.send_api_call(
                    f"v2/auth/r/orders/{self.symbol_to_bfx(symbol)}/hist",
                    method="POST",
                    signed=True,
                    **params
                )
                res = bfx.find_order(_res, order_id, origin_client_order_id)
            if res:
                b_res = bfx.order(res, response_type=response_type)
                self.active_order(b_res['orderId'], b_res['origQty'], b_res['executedQty'])
        elif self.exchange == 'huobi':
            if origin_client_order_id:
                params = {'clientOrderId': str(origin_client_order_id)}
                res = await self.http.send_api_call("/v1/order/orders/getClientOrder", signed=True, **params)
            else:
                res = await self.http.send_api_call(f"v1/order/orders/{order_id}", signed=True)
            if res:
                b_res = hbp.order(res, response_type=response_type)
                self.active_order(b_res['orderId'], b_res['origQty'], b_res['executedQty'])
        elif self.exchange == 'okx':
            params = {'instId': self.symbol_to_okx(symbol),
                      'ordId': str(order_id),
                      'clOrdId': str(origin_client_order_id)}
            res = await self.http.send_api_call("/api/v5/trade/order", signed=True, **params)
            if res:
                b_res = okx.order(res[0], response_type=response_type)
        elif self.exchange == 'bybit':
            params = {
                'category': 'spot',
                'symbol': symbol,
                'orderId': str(order_id),
                'orderLinkId': str(origin_client_order_id),
            }
            res, _ = await self.http.send_api_call("/v5/order/history", signed=True, **params)
            if res["list"]:
                b_res = bbt.order(res["list"][0], response_type=response_type)
        return b_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-order-trade
    async def cancel_order(  # lgtm [py/similar-function]
            self,
            trade_id,
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
            binance_res = await self.user_session.handle_request(
                trade_id,
                "order.cancel",
                _params=params,
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
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
            res = await self.user_session.handle_request(trade_id, "oc", _params=params)
            if res is None or (res and isinstance(res, list) and res[6] == 'ERROR'):
                logger.warning(FALLBACK_WARNING)
                logger.debug(f"cancel_order.bitfinex {order_id}: res1: {res}")
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
                        binance_res = bfx.order(res[4], response_type=True, cancelled=True)
                        break
                    await asyncio.sleep(0.1)
            else:
                logger.debug(f"cancel_order.bitfinex {order_id}: res2: {res}")
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(
                f"v1/order/orders/{order_id}/submitcancel",
                method="POST",
                signed=True
            )
            if res:
                timeout = STATUS_TIMEOUT / 0.1
                while not self.active_orders.get(order_id, {}).get('cancelled', False) and timeout:
                    timeout -= 1
                    await asyncio.sleep(0.1)
                binance_res = await self.fetch_order(trade_id, symbol, order_id=res, response_type=True)
        elif self.exchange == 'okx':
            _symbol = self.symbol_to_okx(symbol)
            _queue = asyncio.Queue()
            self.on_order_update_queues.update({f"{_symbol}{order_id}": _queue})
            params = {
                "instId": _symbol,
                "ordId": str(order_id),
                "clOrdId": str(origin_client_order_id),
            }
            _res = (
                    await self.user_session.handle_request(trade_id, "cancel-order", _params=params)
                    or await self.http.send_api_call(
                        "/api/v5/trade/cancel-order",
                        method="POST",
                        signed=True,
                        **params,
                    )
            )
            if _res[0].get('sCode') != '0':
                raise UserWarning(_res[0].get('sMsg'))
            try:
                binance_res = await asyncio.wait_for(_queue.get(), timeout=STATUS_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"WSS CancelOrder for OKX:{symbol} timeout exception")
            self.on_order_update_queues.pop(f"{_symbol}{order_id}", None)
        elif self.exchange == 'bybit':
            params = {
                'category': 'spot',
                'symbol': symbol,
                'orderId': str(order_id),
                'orderLinkId': str(origin_client_order_id)
            }
            res, _ = await self.http.send_api_call("/v5/order/cancel", method="POST", signed=True, **params)
            if order_id := res.get("orderId"):
                try:
                    binance_res = await asyncio.wait_for(self.fetch_object(f"oc-{order_id}"), timeout=STATUS_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"WSS CancelOrder for ByBit:{symbol}:{order_id} timeout exception")

        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-all-open-orders-on-a-symbol-trade
    async def cancel_all_orders(self, trade_id, symbol, receive_window=None):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.user_session.handle_request(
                trade_id,
                "openOrders.cancelAll",
                _params=params,
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
                binance_res = await self.http.send_api_call(
                    "/api/v3/openOrders",
                    "DELETE",
                    params=params,
                    signed=True,
                    )
        elif self.exchange == 'bitfinex':
            orders = await self.fetch_open_orders(trade_id, symbol, receive_window=receive_window, response_type=True)
            orders_id = [order.get('orderId') for order in orders]
            params = {'id': orders_id}
            res = await self.user_session.handle_request(trade_id, "oc_multi", _params=params)
            if not res or (res and isinstance(res, list) and res[6] != 'SUCCESS'):
                logger.warning(FALLBACK_WARNING)
                logger.debug(f"cancel_all_orders.bitfinex {orders_id}: res1: {res}")
                res = await self.http.send_api_call(
                        "v2/auth/w/order/cancel/multi",
                        method="POST",
                        signed=True,
                        **params
                )
            if res and isinstance(res, list) and res[6] == 'SUCCESS':
                binance_res = bfx.orders(res[4], response_type=True, cancelled=True)
            else:
                logger.debug(f"bitfinex: cancel_all_orders.res: {res}")
        elif self.exchange == 'huobi':
            orders = await self.fetch_open_orders(trade_id, symbol, receive_window=receive_window, response_type=True)
            orders_id = [str(order.get('orderId')) for order in orders]
            params = {'order-ids': orders_id}

            res = await self.user_session.handle_request(trade_id, "cancel", _params=params)

            if res is None:
                logger.warning(FALLBACK_WARNING)
                res = await self.http.send_api_call(
                    "v1/order/orders/batchcancel",
                    method="POST",
                    signed=True,
                    **params,
                )
            orders_id = res.get('success', [])
            for order in orders:
                if str(order.get('orderId')) in orders_id:
                    order['status'] = 'CANCELED'
                    binance_res.append(order)
        elif self.exchange == 'okx':
            orders = await self.fetch_open_orders(
                trade_id,
                symbol,
                receive_window=receive_window,
                response_type=True
            )
            _symbol = self.symbol_to_okx(symbol)
            while orders:
                orders_canceled = []
                params = []
                i = 0
                # 20 is OKX limit fo bulk orders cancel
                for order in orders:
                    order['status'] = 'CANCELED'
                    orders_canceled.append(order)
                    params.append({'instId': _symbol, 'ordId': order.get('orderId')})
                    if i >= 19:
                        break
                    i += 1
                del orders[:20]
                res = await self.user_session.handle_request(
                    trade_id,
                    "batch-cancel-orders",
                    _params=params
                )
                if res is None:
                    res = await self.http.send_api_call(
                        "/api/v5/trade/cancel-batch-orders",
                        method="POST",
                        signed=True,
                        data=params,
                    )
                ids_canceled = [int(ordr['ordId']) for ordr in res if ordr['sCode'] == '0']
                orders_canceled[:] = [i for i in orders_canceled if i['orderId'] in ids_canceled]
                binance_res.extend(orders_canceled)
        elif self.exchange == 'bybit':
            params = {'category': 'spot', 'symbol': symbol}
            res, _ = await self.http.send_api_call("/v5/order/cancel-all", method="POST", signed=True, **params)

            tasks = set()
            for order in res.get('list', []):
                _id = order.get('orderId')
                task = asyncio.create_task(self.fetch_object(f"oc-{_id}"))
                task.set_name(f"{_id}")
                tasks.add(task)

            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=STATUS_TIMEOUT)
                binance_res = [task.result() for task in done]
                if pending:
                    [task.cancel() for task in pending]
                    if res.get("success"):
                        for task in pending:
                            _id = task.get_name()
                            _res = await self.fetch_order(trade_id, symbol, order_id=_id, response_type=True)
                            binance_res.append(_res)
                    pending.clear()
                tasks.clear()

        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#current-open-orders-user_data
    async def fetch_open_orders(self, trade_id, symbol, receive_window=None, response_type=None):
        self.assert_symbol(symbol)
        binance_res = []
        if self.exchange == 'binance':
            params = {"symbol": symbol}
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.user_session.handle_request(
                trade_id,
                "openOrders.status",
                _params=params,
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
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
            if res:
                binance_res = bfx.orders(res)
        elif self.exchange == 'huobi':
            params = {
                'account-id': str(self.account_id),
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
            params = {'instType': 'SPOT', 'instId': self.symbol_to_okx(symbol)}
            res = await self.http.send_api_call(
                "/api/v5/trade/orders-pending",
                signed=True,
                **params,
            )
            # print(f"fetch_open_orders.res: {res}")
            binance_res = okx.orders(res, response_type=response_type)
        elif self.exchange == 'bybit':
            params = {'category': 'spot', 'symbol': symbol}
            res, _ = await self.http.send_api_call("/v5/order/realtime", signed=True, **params)
            binance_res = bbt.orders(res['list'], response_type=response_type)
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
    async def fetch_account_information(self, trade_id, receive_window=None):
        params = {}
        binance_res = {}
        if self.exchange == 'binance':
            if receive_window:
                params["recvWindow"] = receive_window
            binance_res = await self.user_session.handle_request(
                trade_id,
                "account.status",
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
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
            if res:
                binance_res = bfx.account_information(res)
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(f"v1/account/accounts/{self.account_id}/balance", signed=True)
            binance_res = hbp.account_information(res.get('list'))
        elif self.exchange == 'okx':
            res = await self.http.send_api_call("/api/v5/account/balance", signed=True)
            binance_res = okx.account_information(res[0].get('details'), res[0].get('uTime'))
        elif self.exchange == 'bybit':
            params = {'accountType': 'UNIFIED'}
            res, ts = await self.http.send_api_call("/v5/account/wallet-balance", signed=True, **params)
            binance_res = bbt.account_information(res["list"][0]["coin"], ts)
        # print(f"fetch_account_information.binance_res: {binance_res}")
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
            params = {'ccy': self.symbol_to_okx(asset)} if asset else {}
            res = await self.http.send_api_call("/api/v5/asset/balances", signed=True, **params)
            binance_res = okx.funding_wallet(res)
        elif self.exchange == 'bybit':
            params = {'accountType': 'FUND'}
            res, _ = await self.http.send_api_call(
                "/v5/asset/transfer/query-account-coins-balance",
                signed=True,
                **params
            )
            binance_res = bbt.funding_wallet(res["balance"])
        return binance_res

    # https://developers.binance.com/docs/sub_account/asset-management/Transfer-to-Sub-account-of-Same-Master
    async def transfer_to_sub(self, email, symbol, quantity, receive_window=None):
        if self.exchange == 'binance':
            quantity = any2str(Decimal(quantity).quantize(Decimal('0.01234567'), rounding=ROUND_HALF_DOWN))
            params = {"toEmail": email, "asset": symbol, "amount": quantity}
            if receive_window:
                params["recvWindow"] = receive_window
            return await self.http.send_api_call(
                "/sapi/v1/sub-account/transfer/subToSub",
                "POST",
                signed=True,
                params=params
            )
        else:
            raise ValueError(f"Can't implemented for {self.exchange}")

    # https://binance-docs.github.io/apidocs/spot/en/#transfer-to-master-for-sub-account
    async def transfer_to_master(self, symbol, quantity, receive_window=None):
        _quantity = any2str(Decimal(quantity).quantize(Decimal('0.01234567'), rounding=ROUND_HALF_DOWN))
        binance_res = {}
        if self.exchange == 'binance':
            if self.master_email:
                logger.info(f"Collect {_quantity}{symbol} to {self.master_email} sub-account")
                binance_res = await self.transfer_to_sub(self.master_email, symbol, quantity, receive_window)
            else:
                params = {"asset": symbol, "amount": _quantity}
                if receive_window:
                    params["recvWindow"] = receive_window
                binance_res = await self.http.send_api_call(
                    "/sapi/v1/sub-account/transfer/subToMaster",
                    "POST",
                    signed=True,
                    params=params
                )
        elif self.exchange == 'bitfinex':
            if self.master_email is None or self.two_fa is None:
                raise ValueError("This query requires master_email and 2FA")
            totp = pyotp.TOTP(self.two_fa)
            params = {
                "from": "exchange",
                "to": "exchange",
                "currency": symbol,
                "amount": _quantity,
                "email_dst": self.master_email,
                "tfaToken": {"method": "otp", "token": totp.now()}
            }
            res = await self.http.send_api_call(
                "v2/auth/w/transfer",
                method="POST",
                signed=True,
                **params,
            )
            logger.debug(f"transfer_to_master.res: {res}")
            if res and isinstance(res, list) and res[6] == 'SUCCESS':
                binance_res = {"txnId": res[0]}
        elif self.exchange == 'huobi':
            params = {
                'from-user': self.account_uid,
                'from-account-type': "spot",
                'from-account': self.account_id,
                'to-user': self.main_account_uid,
                'to-account-type': "spot",
                'to-account': self.main_account_id,
                'currency': symbol.lower(),
                'amount': _quantity
            }
            res = await self.http.send_api_call(
                "v1/account/transfer",
                method="POST",
                signed=True,
                **params,
            )
            binance_res = {"txnId": res.get("transact-id")}
        elif self.exchange == 'okx':
            params = {
                "ccy": symbol,
                "amt": _quantity,
                "from": '18',
                "to": '18',
                "type": '3'
            }
            res = await self.http.send_api_call(
                "/api/v5/asset/transfer",
                method="POST",
                signed=True,
                **params,
            )
            binance_res = {"txnId": res[0].get("transId")}
        elif self.exchange == 'bybit':
            if not self.main_account_uid:
                raise UserWarning("This request can only be made from the subaccount")

            params = {'coin': symbol}
            res, _ = await self.http.send_api_call("/v5/asset/coin/query-info", signed=True, **params)
            n = int(res["rows"][0]["chains"][0]["minAccuracy"])
            params = {
                'transferId': str(uuid.uuid4()),
                'coin': symbol,
                'amount':  str(math.floor(float(_quantity) * 10 ** n) / 10 ** n),
                'fromMemberId': self.account_uid,
                'toMemberId': self.main_account_uid,
                'fromAccountType': 'UNIFIED',
                'toAccountType': 'UNIFIED',
            }
            res, _ = await self.http.send_api_call(
                "/v5/asset/transfer/universal-transfer",
                "POST",
                signed=True,
                **params
            )
            binance_res = {"txnId": res.get("transferId")}
        return binance_res

    # https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-trade-list-user_data
    async def fetch_account_trade_list(
            self,
            trade_id,
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
            binance_res = await self.user_session.handle_request(
                trade_id,
                "myTrades",
                _params=params,
                send_api_key=True,
                _signed=True
            )
            if binance_res is None:
                logger.warning(FALLBACK_WARNING)
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
                binance_res = bfx.account_trade_list(res, order_id)
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
        return binance_res

    async def fetch_order_trade_list(self, trade_id, symbol, order_id):
        if not order_id:
            raise ValueError("This query (fetch_order_trade_list) requires an order_id")
        self.assert_symbol(symbol)
        b_res = []
        if self.exchange == 'binance':
            b_res = await self.fetch_account_trade_list(trade_id, symbol, order_id=order_id)
        elif self.exchange == 'bitfinex':
            res = await self.http.send_api_call(
                f"v2/auth/r/order/{self.symbol_to_bfx(symbol)}:{order_id}/trades",
                method='POST',
                signed=True,
            )
            if res:
                b_res = bfx.account_trade_list(res)
            else:
                b_res = await self.fetch_account_trade_list(trade_id, symbol, order_id)
        elif self.exchange == 'huobi':
            res = await self.http.send_api_call(f"v1/order/orders/{order_id}/matchresults", signed=True)
            b_res = hbp.account_trade_list(res)
        elif self.exchange == 'okx':
            params = {'instType': "SPOT",
                      'instId': self.symbol_to_okx(symbol),
                      'ordId': str(order_id),
                      }
            res = await self.http.send_api_call("/api/v5/trade/fills", signed=True, **params)
            b_res = okx.order_trade_list(res)
        elif self.exchange == 'bybit':
            res_list = []
            params = {
                'category': "spot",
                'execType': 'Trade',
                'orderId': str(order_id)
            }
            next_page_cursor = 1
            while next_page_cursor:
                res, _ = await self.http.send_api_call("/v5/execution/list", signed=True, **params)
                next_page_cursor = params['cursor'] = res['nextPageCursor']
                res_list.extend(res['list'])
            b_res = bbt.order_trade_list(res_list)
        return b_res

    # endregion

    # USER DATA STREAM ENDPOINTS

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#create-a-listenkey
    async def create_listen_key(self):
        return await self.http.send_api_call(USER_DATA_STREAM, "POST")

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
    async def keep_alive_listen_key(self, listen_key):
        if not listen_key:
            raise ValueError("This query requires a listen_key.")
        return await self.http.send_api_call(
            USER_DATA_STREAM, "PUT", params={"listenKey": listen_key}
        )

    # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#close-a-listenkey
    async def close_listen_key(self, listen_key):
        if not listen_key:
            raise ValueError("This query requires a listen_key.")
        return await self.http.send_api_call(
            USER_DATA_STREAM, "DELETE", params={"listenKey": listen_key}
        )
