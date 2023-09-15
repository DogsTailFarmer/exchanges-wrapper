import sys
import asyncio
import json
import logging
import time
from decimal import Decimal
import traceback
import gzip
from datetime import datetime
from urllib.parse import urlencode, urlparse
import websockets.client

import exchanges_wrapper.bitfinex_parser as bfx
import exchanges_wrapper.huobi_parser as hbp
import exchanges_wrapper.okx_parser as okx
from crypto_ws_api.ws_session import generate_signature

logger_ws = logger = logging.getLogger('exch_srv_logger')
logger_ws.level = logging.INFO
sys.tracebacklimit = 0


class EventsDataStream:
    def __init__(self, client, endpoint, exchange, trade_id):
        self.client = client
        self.endpoint = endpoint
        self.exchange = exchange
        self.trade_id = trade_id
        self.websocket = None
        self.try_count = 0
        self.wss_event_buffer = {}
        self._order_book = None
        self._price = None

    async def start(self):
        async for ws in websockets.client.connect(self.endpoint, logger=logger_ws):
            self.websocket = ws
            try:
                await self.start_wss()
            except websockets.ConnectionClosed as ex:
                if ex.code == 4000:
                    logger.info(f"WSS closed for {self.exchange}:{self.trade_id}")
                    break
                else:
                    logger.warning(f"Restart WSS for {self.exchange}")
                    continue
            except Exception as ex:
                logger.error(f"WSS start() other exception: {ex}")
                # logger.debug(traceback.format_exc())

    async def start_wss(self):
        pass  # meant to be overridden in a subclass

    async def stop(self):
        """
        Stop data stream
        """
        if self.websocket:
            await self.websocket.close(code=4000)

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, msg, symbol=None, ch_type=str()):
        msg_data = json.loads(msg if isinstance(msg, str) else gzip.decompress(msg))
        if self.exchange == 'binance':
            await self._handle_event(msg_data)
        elif self.exchange == 'okx':
            if (not ch_type and
                    msg_data.get('arg', {}).get('channel') in ('account', 'orders', 'balance_and_position')
                    and msg_data.get('data')):
                await self._handle_event(msg_data)
            elif ch_type and msg_data.get('data'):
                await self._handle_event(msg_data.get('data')[0], symbol, ch_type)
            elif msg_data.get("event") == "login" and msg_data.get("code") == "0":
                return
            elif msg_data.get("event") in ("login", "error") and msg_data.get("code") != "0":
                logger.info(f"WSS handle messages: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
                raise websockets.ConnectionClosed(f"Reconnecting OKX user {ch_type} channel")
            else:
                logger.debug(f"OKX undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'bitfinex':
            # info and error handling
            if isinstance(msg_data, dict):
                if msg_data.get('event') == 'info':
                    if msg_data.get('version') != 2:
                        logger.critical('Change WSS version detected')
                    if msg_data.get('platform') and msg_data.get('platform').get('status') != 1:
                        logger.warning(f"Exchange in maintenance mode, trying reconnect. Exchange info: {msg}")
                        await asyncio.sleep(60)
                        raise websockets.ConnectionClosed
                elif msg_data.get('event') == 'subscribed':
                    chan_id = msg_data.get('chanId')
                    logger.info(f"bitfinex, ch_type: {ch_type}, chan_id: {chan_id}")
                elif msg_data.get('event') == 'auth' and msg_data.get('status') == 'OK':
                    chan_id = msg_data.get('chanId')
                    logger.info(f"bitfinex, user stream chan_id: {chan_id}")
                elif 'code' in msg_data:
                    code = msg_data.get('code')
                    if code == 10300:
                        raise websockets.ConnectionClosed('WSS Subscription failed (generic)')
                    elif code == 10301:
                        logger.error('WSS Already subscribed')
                    elif code == 10302:
                        raise UserWarning(f"WSS Unknown channel {ch_type}")
                    elif code == 10305:
                        raise UserWarning('WSS Reached limit of open channels')
                    elif code == 20051:
                        raise websockets.ConnectionClosed('WSS reconnection request received from exchange')
                    elif code == 20060:
                        logger.info('WSS entering in maintenance mode, trying reconnect after 120s')
                        await asyncio.sleep(120)
                        raise websockets.ConnectionClosed
            # data handling
            elif isinstance(msg_data, list) and len(msg_data) == 2 and msg_data[1] == 'hb':
                pass  # heartbeat message
            elif isinstance(msg_data, list):
                if ch_type == 'book' and isinstance(msg_data[1][-1], list):
                    self._order_book = bfx.OrderBook(msg_data[1], symbol)
                else:
                    await self._handle_event(msg_data, symbol, ch_type, self._order_book)
            else:
                logger.debug(f"Bitfinex undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'huobi':
            if msg_data.get('ping'):
                await self.websocket.send(json.dumps({"pong": msg_data.get('ping')}))
            elif msg_data.get('action') == 'ping':
                pong = {
                    "action": "pong",
                    "data": {
                          "ts": msg_data.get('data').get('ts')
                    }
                }
                await self.websocket.send(json.dumps(pong))
            elif msg_data.get('tick') or msg_data.get('data'):
                if ch_type == 'ticker':
                    _price = msg_data.get('tick', {}).get('lastPrice', None)
                    if self._price != _price:
                        self._price = _price
                        await self._handle_event(msg_data, symbol, ch_type)
                else:
                    await self._handle_event(msg_data, symbol, ch_type)
            elif msg_data.get('action') == 'req' and msg_data.get('code') == 200 and msg_data.get('ch') == 'auth':
                return
            elif (msg_data.get('action') == 'sub' and
                  msg_data.get('code') == 500 and
                  msg_data.get('message') == '系统异常:'):
                raise websockets.ConnectionClosed(f"Reconnecting Huobi user {ch_type} channel")
            else:
                logger.debug(f"Huobi undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")

    async def ws_listener(self, request=None, symbol=None, ch_type=str()):
        if request:
            await self.websocket.send(json.dumps(request))
        async for msg_data in self.websocket:
            await self._handle_messages(msg_data, symbol, ch_type)


class MarketEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, exchange, trade_id, channel=None):
        super().__init__(client, endpoint, exchange, trade_id)
        self.channel = channel
        self.candles_max_time = None
        if self.exchange == 'binance':
            registered_streams = self.client.events.registered_streams.get(self.exchange, {}).get(self.trade_id, set())
            combined_streams = "/".join(registered_streams)
            self.endpoint = f"{endpoint}/stream?streams={combined_streams}"

    async def start_wss(self):
        logger.info(f"Start market WSS {self.channel or ''} for {self.exchange}")
        symbol = None
        ch_type = str()
        request = {}

        if self.exchange != 'binance':
            symbol = self.channel.split('@')[0]
            ch_type = self.channel.split('@')[1]
            if self.exchange == 'okx':
                if ch_type == 'miniTicker':
                    _ch_type = 'tickers'
                elif 'kline_' in ch_type:
                    _ch_type = (f"{ch_type.split('_')[0].replace('kline', 'candle')}"
                                f"{okx.interval(ch_type.split('_')[1])}")
                elif ch_type == 'depth5':
                    _ch_type = 'books5'
                else:
                    _ch_type = None
                request = {"op": 'subscribe',
                           "args": [{"channel": _ch_type,
                                     "instType": 'SPOT',
                                     "instId": symbol}
                                    ]
                           }
            elif self.exchange == 'bitfinex':
                if ch_type == 'miniTicker':
                    ch_type = 'ticker'
                    request = {'event': 'subscribe', 'channel': ch_type, 'pair': symbol}
                elif 'kline_' in ch_type:
                    ch_type = ch_type.replace('kline_', 'candles_')
                    tf = ch_type.split('_')[1]
                    request = {'event': 'subscribe', 'channel': 'candles', 'key': f"trade:{tf}:{symbol}"}
                elif ch_type == 'depth5':
                    ch_type = 'book'
                    request = {'event': 'subscribe', 'channel': ch_type, 'symbol': symbol, 'prec': 'P0', "freq": "F0"}
            elif self.exchange == 'huobi':
                if ch_type == 'miniTicker':
                    ch_type = 'ticker'
                    request = {'sub': f"market.{symbol}.{ch_type}"}
                elif 'kline_' in ch_type:
                    tf = ch_type.split('_')[1]
                    request = {'sub': f"market.{symbol}.kline.{hbp.interval(tf)}"}
                elif ch_type == 'depth5':
                    request = {'sub': f"market.{symbol}.depth.step0"}

        await self.ws_listener(request, symbol, ch_type)

    async def _handle_event(self, content, symbol=None, ch_type=str(), order_book=None):
        # logger.info(f"MARKET_handle_event.content: symbol: {symbol}, ch_type: {ch_type}, content: {content}")
        self.try_count = 0
        if self.exchange == 'bitfinex':
            if 'candles' in ch_type:
                bfx_data = content[1][-1] if isinstance(content[1][-1], list) else content[1]
                if (
                    self.candles_max_time is not None
                    and bfx_data[0] < self.candles_max_time
                ):
                    return
                self.candles_max_time = bfx_data[0]
                content = bfx.candle(bfx_data, symbol, ch_type)
            elif ch_type == 'ticker':
                content = bfx.ticker(content[1], symbol)
            elif ch_type == 'book' and isinstance(order_book, bfx.OrderBook):
                order_book.update_book(content[1])
                content = order_book.get_book()
        elif self.exchange == 'huobi':
            if ch_type == 'ticker':
                content = hbp.ticker(content, symbol)
            elif 'kline_' in ch_type:
                content = hbp.candle(content, symbol, ch_type)
            elif ch_type == 'depth5':
                content = hbp.order_book_ws(content, symbol)
            else:
                return
        elif self.exchange == 'okx':
            if ch_type == 'miniTicker':
                content = okx.ticker(content)
            elif 'kline_' in ch_type:
                content = okx.candle(content, symbol, ch_type)
            if ch_type == 'depth5':
                content = okx.order_book_ws(content, symbol)
        #
        stream_name = None
        if isinstance(content, dict) and "stream" in content:
            stream_name = content["stream"]
            content = content["data"]
            content["stream"] = stream_name
            await self.client.events.wrap_event(content).fire(self.trade_id)
        elif isinstance(content, list):
            for event_content in content:
                event_content["stream"] = stream_name
                await self.client.events.wrap_event(event_content).fire(self.trade_id)


class HbpPrivateEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, exchange, trade_id, symbol):
        super().__init__(client, endpoint, exchange, trade_id)
        self.symbol = symbol

    async def start_wss(self):
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        _params = {
                "accessKey": self.client.api_key,
                "signatureMethod": "HmacSHA256",
                "signatureVersion": "2.1",
                "timestamp": str(ts)
        }
        signature_payload = (f"GET\n{urlparse(self.endpoint).hostname}\n{urlparse(self.endpoint).path}\n"
                             f"{urlencode(_params)}")
        signature = generate_signature(self.exchange, self.client.api_secret, signature_payload)
        _params["authType"] = "api"
        _params["signature"] = signature
        request = {
            "action": "req",
            "ch": "auth",
            "params": _params
        }
        await self.websocket.send(json.dumps(request))
        await self._handle_messages(await self.websocket.recv())
        request = {
            "action": "sub",
            "ch": "accounts.update#2"
        }
        await self.websocket.send(json.dumps(request))
        await self._handle_messages(await self.websocket.recv())
        request = {
            "action": "sub",
            "ch": f"trade.clearing#{self.symbol.lower()}#0"
        }
        await self.ws_listener(request)

    async def _handle_event(self, msg_data, *args):
        content = None
        if msg_data.get('data').get('accountId') == self.client.hbp_account_id:
            if msg_data.get('ch') == 'accounts.update#2':
                content = hbp.on_funds_update(msg_data)
            elif msg_data.get('ch') == f"trade.clearing#{self.symbol.lower()}#0":
                data = msg_data.get('data')
                content = hbp.on_order_update(data)
        if content:
            logger.debug(f"HbpPrivateEventsDataStream._handle_event.content: {content}")
            await self.client.events.wrap_event(content).fire(self.trade_id)


class BfxPrivateEventsDataStream(EventsDataStream):

    async def start_wss(self):
        ts = int(time.time() * 1000)
        data = f"AUTH{ts}"
        request = {
            'event': "auth",
            'apiKey': self.client.api_key,
            'authSig': generate_signature(self.exchange, self.client.api_secret, data),
            'authPayload': data,
            'authNonce': ts,
            'filter': ['trading', 'wallet']
        }
        await self.ws_listener(request)

    async def _handle_event(self, msg_data, *args):
        # logger.debug(f"BitfinexPrivate: msg_data: {msg_data}")
        content = None
        if msg_data[1] in ('wu', 'ws'):
            content = bfx.on_funds_update(msg_data[2])
        elif msg_data[1] == 'oc':
            order_id = msg_data[2][0]
            last_event = self.client.active_orders.get(order_id, {}).get('lastEvent', ())
            content = bfx.on_order_update(msg_data[2], last_event)
            if 'CANCELED' in msg_data[2][13]:
                self.client.active_orders.get(order_id, {}).update({'cancelled': True})
        elif msg_data[1] == 'te':
            order_id = msg_data[2][3]
            if self.client.active_orders.get(order_id, None) is None:
                self.client.wss_buffer.setdefault(order_id, [])
                self.client.wss_buffer[order_id].append(msg_data[2])
            else:
                orig_qty = Decimal(self.client.active_orders[order_id]['origQty'])
                last_qty = str(abs(msg_data[2][4]))
                executed_qty = self.client.active_orders[order_id]['executedQty']
                self.client.active_orders[order_id]['executedQty'] = executed_qty = str(Decimal(executed_qty) +
                                                                                        Decimal(last_qty))
                if Decimal(executed_qty) >= orig_qty:
                    self.client.active_orders[order_id]['lastEvent'] = (msg_data[2][0], last_qty, str(msg_data[2][5]))
                else:
                    executed_qty = self.client.active_orders.get(order_id, {}).get('executedQty', '0')
                    content = bfx.on_order_trade(msg_data[2], executed_qty)
        if content:
            await self.client.events.wrap_event(content).fire(self.trade_id)


class OkxPrivateEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, exchange, trade_id, symbol):
        super().__init__(client, endpoint, exchange, trade_id)
        self.symbol = symbol

    async def start_wss(self):
        ts = int(time.time())
        signature_payload = f"{ts}GET/users/self/verify"
        signature = generate_signature(self.exchange, self.client.api_secret, signature_payload)
        # Login on account
        request = {"op": 'login',
                   "args": [{"apiKey": self.client.api_key,
                             "passphrase": self.client.passphrase,
                             "timestamp": ts,
                             "sign": signature}
                            ]
                   }
        await self.websocket.send(json.dumps(request))
        await self._handle_messages(await self.websocket.recv())
        # Channel subscription
        request = {"op": 'subscribe',
                   "args": [{"channel": "account"},
                            {"channel": "orders",
                             "instType": "SPOT",
                             "instId": self.symbol},
                            {"channel": "balance_and_position"}
                            ]
                   }
        await self.ws_listener(request)

    async def _handle_event(self, msg_data, *args):
        content = None
        _data = msg_data.get('data')[0]
        if msg_data.get('arg', {}).get('channel') == 'account':
            content = okx.on_funds_update(_data)
        elif msg_data.get('arg', {}).get('channel') == 'orders':
            if _data.get('state') == "canceled":
                if _queue := self.client.on_order_update_queues.get(
                    f"{_data.get('instId')}{_data.get('ordId')}"
                ):
                    await _queue.put(okx.order(_data, response_type=True))
            content = okx.on_order_update(_data)
        elif msg_data.get('arg', {}).get('channel') == 'balance_and_position':
            content, self.wss_event_buffer = okx.on_balance_update(
                _data.get('balData', []),
                self.wss_event_buffer,
                _data.get('eventType') == 'transferred',
            )
            for i in content:
                await self.client.events.wrap_event(i).fire(self.trade_id)
            content = None
        if content:
            await self.client.events.wrap_event(content).fire(self.trade_id)


class UserEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, exchange, trade_id):
        super().__init__(client, endpoint, exchange, trade_id)
        self.listen_key = None

    async def async_init(self):
        self.listen_key = (await self.client.create_listen_key())["listenKey"]
        self.endpoint = f"{self.endpoint}/ws/{self.listen_key}"
        return self

    def __await__(self):
        return self.async_init().__await__()

    async def _heartbeat(self, listen_key, interval=60 * 30):
        # 30 minutes is recommended according to
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        while True:
            await asyncio.sleep(interval)
            await self.client.keep_alive_listen_key(listen_key)

    async def start_wss(self):
        logger.info(f"Start User WSS for {self.exchange}")
        _task = asyncio.ensure_future(self._heartbeat(self.listen_key))
        try:
            await self.ws_listener()
        finally:
            _task.cancel()

    async def _handle_event(self, content):
        # logger.debug(f"UserEventsDataStream._handle_event.content: {content}")
        await self.client.events.wrap_event(content).fire(self.trade_id)
