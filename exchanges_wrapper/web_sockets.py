import sys
import asyncio
import ujson as json
import logging.handlers
from pathlib import Path
import time
from decimal import Decimal
import gzip
from datetime import datetime, timezone

from websockets.asyncio.client import connect
from websockets import ConnectionClosed

import exchanges_wrapper.parsers.bitfinex as bfx
import exchanges_wrapper.parsers.huobi as hbp
import exchanges_wrapper.parsers.okx as okx
import exchanges_wrapper.parsers.bybit as bbt
from crypto_ws_api.ws_session import generate_signature, compose_htx_ws_auth
from exchanges_wrapper import LOG_PATH

logger = logging.getLogger(__name__)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
fh = logging.handlers.RotatingFileHandler(Path(LOG_PATH, 'websockets.log'), maxBytes=1000000, backupCount=10)
fh.setFormatter(formatter)
fh.setLevel(logging.INFO)
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
sh.setLevel(logging.INFO)

logger.addHandler(fh)
logger.addHandler(sh)
logger.propagate = False

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
        self.tasks = set()
        self.wss_started = False
        self.ping = 0

    async def start(self):
        async for self.websocket in connect(
                self.endpoint,
                logger=logger,
                ping_interval=None if self.exchange == 'huobi' else 20
        ):
            start_time = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                await self.start_wss()
            except ConnectionClosed as ex:
                ct = str(datetime.now(timezone.utc).replace(tzinfo=None) - start_time).rsplit('.')[0]
                logger.info(f"WSS life time for {self.exchange} is {ct}")
                self.tasks_cancel()
                if ex.rcvd and ex.rcvd.code == 4000:
                    logger.info(f"WSS closed for {self.exchange}:{self.trade_id}")
                    break
                else:
                    logger.warning(f"Restart WSS for {self.exchange}: {ex}")
                    continue
            except Exception as ex:
                self.tasks_cancel()
                logger.error(f"WSS start() other exception: {ex}")

    async def start_wss(self):
        pass  # meant to be overridden in a subclass

    async def stop(self):
        """
        Stop data stream
        """
        self.tasks_cancel()
        if self.websocket:
            await self.websocket.close(code=4000)

    def tasks_cancel(self):
        [task.cancel() for task in self.tasks if not task.done()]
        self.tasks.clear()

    def tasks_manage(self, coro):
        _t = asyncio.create_task(coro)
        self.tasks.add(_t)
        _t.add_done_callback(self.tasks.discard)

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, msg, symbol=None, ch_type=str()):
        msg_data = json.loads(msg if isinstance(msg, str) else gzip.decompress(msg))
        if self.exchange == 'binance':
            await self._handle_event(msg_data)
        elif self.exchange == 'bybit':
            if _data := msg_data.get('data'):
                if ch_type == 'depth5':
                    if msg_data["type"] == 'snapshot' or _data["u"] == 1:
                        self._order_book = bbt.OrderBook(_data)
                elif ch_type == 'miniTicker':
                    _data["ts"] = msg_data.get('ts')
                elif msg_data["topic"] in ("execution.spot", "order.spot", "wallet"):
                    ch_type = msg_data["topic"]
                    if msg_data["topic"] == "wallet":
                        _data[0]["creationTime"] = msg_data["creationTime"]
                await self._handle_event(_data, symbol, ch_type)
            elif msg_data.get("ret_msg") == "pong" or msg_data.get("op") == "pong":
                return
            elif ((msg_data.get("ret_msg") == "subscribe" or msg_data.get("op") in ("auth", "subscribe"))
                  and msg_data.get("success")):
                self.tasks_manage(self.bybit_heartbeat(ch_type or "private"))
                if msg_data["op"] == "subscribe" and msg_data["success"] and not msg_data["ret_msg"]:
                    self.wss_started = True
            elif ((msg_data.get("ret_msg") == "subscribe" or msg_data.get("op") in ("auth", "subscribe"))
                  and not msg_data.get("success")):
                logger.warning(f"Reconnecting ByBit WSS: {symbol}: {ch_type}, msg_data: {msg_data}")
                raise ConnectionClosed(None, None)
            else:
                logger.info(f"ByBit undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'okx':
            if (not ch_type and
                    msg_data.get('arg', {}).get('channel') in ('account', 'orders', 'balance_and_position')
                    and msg_data.get('data')):
                await self._handle_event(msg_data)
            elif ch_type and msg_data.get('data'):
                await self._handle_event(msg_data.get('data')[0], symbol, ch_type)
            elif msg_data.get("event") == "login" and msg_data.get("code") == "0":
                return
            elif msg_data.get("event") == "subscribe" and msg_data.get('arg', {}).get('channel') == 'orders':
                self.wss_started = True
            elif msg_data.get("event") in ("login", "error") and msg_data.get("code") != "0":
                logger.warning(f"Reconnecting OKX WSS: {symbol}: {ch_type}, msg_data: {msg_data}")
                raise ConnectionClosed(None, None)
            else:
                logger.debug(f"OKX undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'bitfinex':
            # info and error handling
            if isinstance(msg_data, dict):
                if msg_data.get('version') and msg_data.get('version') != 2:
                    logger.critical('Change WSS version detected')
                if msg_data.get('platform') and msg_data.get('platform').get('status') != 1:
                    logger.warning(f"Exchange in maintenance mode, trying reconnect. Exchange info: {msg}")
                    await asyncio.sleep(60)
                    raise ConnectionClosed(None, None)
                elif 'code' in msg_data:
                    code = msg_data.get('code')
                    if code == 10300:
                        logger.warning('WSS Subscription failed (generic)')
                        raise ConnectionClosed(None, None)
                    elif code == 10301:
                        logger.error('WSS Already subscribed')
                    elif code == 10302:
                        raise UserWarning(f"WSS Unknown channel {ch_type}")
                    elif code == 10305:
                        raise UserWarning('WSS Reached limit of open channels')
                    elif code == 20051:
                        logger.warning('WSS reconnection request received from exchange')
                        raise ConnectionClosed(None, None)
                    elif code == 20060:
                        logger.info('WSS entering in maintenance mode, trying reconnect after 120s')
                        await asyncio.sleep(120)
                        raise ConnectionClosed(None, None)
                elif msg_data.get('event') == 'subscribed':
                    chan_id = msg_data.get('chanId')
                    logger.info(f"bitfinex, ch_type: {ch_type}, chan_id: {chan_id}")
                elif msg_data.get('event') == 'auth' and msg_data.get('status') == 'OK':
                    chan_id = msg_data.get('chanId')
                    self.wss_started = True
                    logger.info(f"bitfinex, user stream chan_id: {chan_id}")

            # data handling
            elif isinstance(msg_data, list) and len(msg_data) == 2 and msg_data[1] == 'hb':
                pass  # heartbeat message
            elif isinstance(msg_data, list):
                if ch_type == 'book' and isinstance(msg_data[1][-1], list):
                    self._order_book = bfx.OrderBook(msg_data[1], symbol)
                else:
                    await self._handle_event(msg_data, symbol, ch_type)
            else:
                logger.debug(f"Bitfinex undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'huobi':
            if ping := msg_data.get('ping'):
                self.ping = 0
                await self.websocket.send(json.dumps({"pong": ping}))
                await asyncio.sleep(0)
            elif msg_data.get('action') == 'ping':
                self.ping = 0
                pong = {
                    "action": "pong",
                    "data": {
                          "ts": msg_data.get('data').get('ts')
                    }
                }
                await self.websocket.send(json.dumps(pong))
                await asyncio.sleep(0)
            elif msg_data.get('tick') or msg_data.get('data'):
                if ch_type == 'ticker':
                    _price = msg_data.get('tick', {}).get('lastPrice', None)
                    if self._price != _price:
                        self._price = _price
                        await self._handle_event(msg_data, symbol, ch_type)
                else:
                    await self._handle_event(msg_data, symbol, ch_type)
            elif msg_data.get('action') in ('req', 'sub') and msg_data.get('code') == 200:
                if msg_data.get('ch') == f"trade.clearing#{symbol.lower()}#0":
                    self.wss_started = True
            elif 'subbed' in msg_data and msg_data.get('status') == 'ok':
                logger.info(f"Huobi WSS started: {msg_data['subbed']}")
            elif (msg_data.get('action') == 'sub' and
                  msg_data.get('code') == 500 and
                  msg_data.get('message') == '系统异常:'):
                logger.warning(f"Reconnecting Huobi user {ch_type} channel")
                raise ConnectionClosed(None, None)
            else:
                logger.debug(f"Huobi undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")

    async def ws_listener(self, request=None, symbol=None, ch_type=str()):
        if request:
            await self.websocket.send(json.dumps(request))
            await asyncio.sleep(0)
        async for msg_data in self.websocket:
            await self._handle_messages(msg_data, symbol, ch_type)

    async def bybit_heartbeat(self, req_id, interval=20):
        while True:
            await asyncio.sleep(interval)
            await self.websocket.send(json.dumps({"req_id": req_id, "op": "ping"}))

    async def htx_keepalive(self, interval=60):
        await asyncio.sleep(interval * 10)
        while True:
            await asyncio.sleep(interval)
            if self.ping:
                break
            else:
                self.ping = 1
        logger.warning("From HTX server PING timeout exceeded")
        await self.websocket.close()


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
            _ch_type = None
            if self.exchange == 'bybit':
                if ch_type == 'miniTicker':
                    _ch_type = 'tickers'
                elif 'kline_' in ch_type:
                    _ch_type = f"{ch_type.split('_')[0]}.{bbt.interval(ch_type.split('_')[1])}"
                elif ch_type == 'depth5':
                    _ch_type = 'orderbook.1'
                request = {
                    "req_id": self.trade_id,
                    "op": 'subscribe',
                    "args": [
                        f"{_ch_type}.{symbol}"
                    ]
                }
            elif self.exchange == 'okx':
                if ch_type == 'miniTicker':
                    _ch_type = 'tickers'
                elif 'kline_' in ch_type:
                    _ch_type = (f"{ch_type.split('_')[0].replace('kline', 'candle')}"
                                f"{okx.interval(ch_type.split('_')[1])}")
                elif ch_type == 'depth5':
                    _ch_type = 'books5'

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

                self.tasks_manage(self.htx_keepalive(interval=30))

        await self.ws_listener(request, symbol, ch_type)

    async def _handle_event(self, content, symbol=None, ch_type=str()):
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
            elif ch_type == 'book':
                self._order_book.update_book(content[1])
                content = self._order_book.get_book()
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
        elif self.exchange == 'bybit':
            if ch_type == 'miniTicker':
                content = bbt.ticker(content)
            elif 'kline_' in ch_type:
                content = bbt.candle(content[0], symbol, ch_type)
            elif ch_type == 'depth5':
                self._order_book.update_book(content)
                content = self._order_book.get_book()
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
        await self.websocket.send(
            json.dumps(
                compose_htx_ws_auth(self.endpoint, self.exchange, self.client.api_key, self.client.api_secret)
            )
        )
        await asyncio.sleep(0)
        await self._handle_messages(await self.websocket.recv(), symbol=self.symbol)
        #
        request = {
            "action": "sub",
            "ch": "accounts.update#2"
        }
        await self.websocket.send(json.dumps(request))
        await asyncio.sleep(0)
        await self._handle_messages(await self.websocket.recv(), symbol=self.symbol)
        #
        request = {
            "action": "sub",
            "ch": f"orders#{self.symbol.lower()}"
        }
        await self.websocket.send(json.dumps(request))
        await asyncio.sleep(0)
        await self._handle_messages(await self.websocket.recv(), symbol=self.symbol)
        #
        request = {
            "action": "sub",
            "ch": f"trade.clearing#{self.symbol.lower()}#0"
        }
        self.tasks_manage(self.htx_keepalive())
        await self.ws_listener(request, symbol=self.symbol)

    async def _handle_event(self, msg_data, *args):
        content = None
        _ch = msg_data['ch']
        _data = msg_data.get('data')
        if _ch == 'accounts.update#2' and _data.get('currency') in self.symbol.lower():
            content = hbp.on_funds_update(_data)
        elif _ch == f"orders#{self.symbol.lower()}" and _data['eventType'] in ('creation', 'cancellation'):
            order_id = _data['orderId']
            self.client.active_order(order_id, quantity=_data['orderSize'])
            if _data.get('eventType') == 'cancellation':
                self.client.active_orders[order_id]['cancelled'] = True
        elif _ch == f"trade.clearing#{self.symbol.lower()}#0":
            order_id = _data['orderId']
            self.client.active_order(order_id, last_event=_data)
            if _data['tradeId'] not in self.client.active_orders[order_id]["eventIds"]:
                self.client.active_orders[order_id]["eventIds"].append(_data['tradeId'])
                self.client.active_orders[order_id]['executedQty'] += Decimal(_data['tradeVolume'])
                content = hbp.on_order_update(self.client.active_orders[order_id])

        if content:
            logger.debug(f"HTXPrivateEvents.content: {content}")
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
        event_type = msg_data[1]
        event = msg_data[2]

        content = None
        if event_type in ('wu', 'ws'):
            content = bfx.on_funds_update(event)
        elif event_type == 'on':
            order_id = event[0]
            self.client.active_order(order_id, quantity=str(abs(event[7])))
            content = bfx.on_order_update(event, self.client.active_orders[order_id])

        elif event_type in ('te', 'tu'):
            order_id = event[3]
            qty = self.client.active_orders.pop(event[11], {}).get('origQty', '0')
            self.client.active_order(order_id, quantity=qty, last_event=event)

            if event[0] not in self.client.active_orders[order_id]["eventIds"]:
                self.client.active_orders[order_id]["eventIds"].append(event[0])
                self.client.active_orders[order_id]['executedQty'] += Decimal(str(abs(event[4])))
                content = bfx.on_order_trade(self.client.active_orders[order_id])
            elif oc_event := self.wss_event_buffer.pop(order_id, None):
                content = bfx.on_order_update(oc_event, self.client.active_orders[order_id])

        elif event_type == 'oc':
            order_id = event[0]
            orig_qty = str(abs(event[7]))
            self.client.active_order(order_id, quantity=orig_qty)
            executed_qty = self.client.active_orders[order_id]['executedQty']
            if 'CANCELED' in event[13] or executed_qty >= Decimal(orig_qty):
                self.client.active_orders[order_id]['cancelled'] = True
                content = bfx.on_order_update(event, self.client.active_orders[order_id])
            else:
                self.wss_event_buffer[order_id] = event

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
        await asyncio.sleep(0)
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


class BBTPrivateEventsDataStream(EventsDataStream):

    async def start_wss(self):
        ts = int((time.time() + 1) * 1000)
        signature_payload = f"GET/realtime{ts}"
        signature = generate_signature(self.exchange, self.client.api_secret, signature_payload)
        # Login on account
        request = {
            "req_id": self.trade_id,
            "op": 'auth',
            "args": [self.client.api_key, ts, signature]
        }
        await self.websocket.send(json.dumps(request))
        await asyncio.sleep(0)
        await self._handle_messages(await self.websocket.recv())
        # Channel subscription
        request = {
            "op": 'subscribe',
            "args": ["execution.spot", "order.spot", "wallet"]
        }
        await self.ws_listener(request)

    async def _handle_event(self, msg_data, *args):
        ch_type = args[1]
        content = None
        if ch_type == 'execution.spot':
            for event in msg_data:
                content = bbt.on_trade_update(event)
                await self.client.events.wrap_event(content).fire(self.trade_id)
            content = None
        elif ch_type == 'order.spot':
            # logger.info(f"_handle_event: ch_type: {ch_type}, msg_data: {msg_data}")
            event = msg_data[0]
            if event.get('orderStatus') in ("Cancelled", "PartiallyFilledCanceled"):
                self.client.wss_buffer[f"oc-{event.get('orderId')}"] = bbt.order(event, response_type=True)
        elif ch_type == 'wallet':
            event = msg_data[0]
            content = bbt.on_funds_update(event)
        if content:
            await self.client.events.wrap_event(content).fire(self.trade_id)


class UserEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, exchange, trade_id):
        super().__init__(client, endpoint, exchange, trade_id)
        self.listen_key = None

    async def async_init(self):
        self.listen_key = (await self.client.create_listen_key())["listenKey"]
        self.endpoint = f"{self.endpoint}/ws/{self.listen_key}"
        self.wss_started = True
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
        self.tasks_manage(self._heartbeat(self.listen_key))
        try:
            await self.ws_listener()
        finally:
            self.tasks_cancel()

    async def _handle_event(self, content):
        # logger.debug(f"UserEventsDataStream._handle_event.content: {content}")
        await self.client.events.wrap_event(content).fire(self.trade_id)
