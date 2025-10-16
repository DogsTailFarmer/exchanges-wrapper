import sys
import asyncio
import gc
import logging

# noinspection PyPackageRequirements
import ujson as json
from pathlib import Path
import time
from decimal import Decimal
import gzip
from datetime import datetime, timezone

# noinspection PyPackageRequirements
from websockets.asyncio.client import connect
# noinspection PyPackageRequirements
from websockets import ConnectionClosed

import exchanges_wrapper.parsers.bitfinex as bfx
import exchanges_wrapper.parsers.huobi as hbp
import exchanges_wrapper.parsers.okx as okx
import exchanges_wrapper.parsers.bybit as bbt
from crypto_ws_api.ws_session import (
    set_logger,
    generate_signature,
    compose_htx_ws_auth,
    compose_binance_ws_auth,
    tasks_manage,
    tasks_cancel
)
from exchanges_wrapper import LOG_PATH, DEBUG_LOG

logger = set_logger(__name__, Path(LOG_PATH, 'websockets.log'))
sys.tracebacklimit = 0


class EventsDataStream:
    __slots__ = (
        'client',
        'endpoint',
        'exchange',
        'trade_id',
        'websocket',
        'try_count',
        'wss_event_buffer',
        '_order_book',
        '_price',
        'tasks',
        'ping',
        'logger'
    )

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
        self.ping = 0
        self.logger = logger

        if exchange == DEBUG_LOG:
            log_key = f"web_s_{trade_id}"
            if log_key in logging.root.manager.loggerDict:
                self.logger = logging.root.manager.loggerDict[log_key]
            else:
                self.logger = set_logger(log_key, Path(LOG_PATH, f"{log_key}.log"), logging.DEBUG)

    async def start(self):
        async for self.websocket in connect(
                self.endpoint,
                logger=self.logger,
                ping_interval=None if self.exchange in ('binance', 'huobi') else 20
        ):
            await self.cycle_init()
            start_time = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                await self.start_wss()
            except ConnectionClosed as ex:
                self.websocket = None
                ct = str(datetime.now(timezone.utc).replace(tzinfo=None) - start_time).rsplit('.')[0]
                self.logger.info(f"WSS life time for {self.exchange} is {ct}")
                if ex.rcvd and ex.rcvd.code == 4000:
                    self.logger.info(f"WSS closed for {self.exchange}:{self.trade_id}")
                    break
                else:
                    self.logger.warning(f"Restart WSS for {self.exchange}: {ex}")
                    continue
            except Exception as ex:
                self.logger.error(f"WSS start() other exception: {ex}")

    async def start_wss(self):
        pass  # meant to be overridden in a subclass

    async def cycle_init(self):
        await tasks_cancel(self.tasks, _logger=logger)
        self.wss_event_buffer.clear()
        gc.collect()

    async def stop(self):
        """
        Stop data stream
        """
        if self.websocket:
            await self.websocket.close(code=4000)
        await self.cycle_init()

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, msg, symbol=None, ch_type=str()):
        msg_data = json.loads(msg if isinstance(msg, str) else gzip.decompress(msg))
        if self.exchange == 'binance':
            if "stream" in msg_data:
                await self._handle_event(msg_data)
            elif event := msg_data.get("event"):
                await self._handle_event(event)
            elif msg_data.get("status") == 200:
                result = msg_data.get("result")
                if isinstance(result, dict) and 'authorizedSince' in result:
                    self.logger.info(f"Binance User Data Stream started for {self.trade_id}")
            else:
                self.logger.warning(f"Reconnecting Binance User Data Stream for {self.trade_id}, msg_data: {msg_data}")
                raise ConnectionClosed(None, None)
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
                tasks_manage(
                    self.tasks, self.bybit_heartbeat(ch_type or "private"), f"bybit_heartbeat-{symbol}-{ch_type}"
                )
                if msg_data["op"] == "subscribe" and msg_data["success"] and not msg_data["ret_msg"]:
                    self.logger.info(f"ByBit User Data Stream started for {self.trade_id}")
            elif ((msg_data.get("ret_msg") == "subscribe" or msg_data.get("op") in ("auth", "subscribe"))
                  and not msg_data.get("success")):
                self.logger.warning(f"Reconnecting ByBit WSS: {symbol}: {ch_type}, msg_data: {msg_data}")
                raise ConnectionClosed(None, None)
            else:
                self.logger.info(f"ByBit undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
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
                self.logger.info(f"OKX User Data Stream started for {self.trade_id}")
            elif msg_data.get("event") in ("login", "error") and msg_data.get("code") != "0":
                self.logger.warning(f"Reconnecting OKX WSS: {symbol}: {ch_type}, msg_data: {msg_data}")
                raise ConnectionClosed(None, None)
            else:
                self.logger.debug(f"OKX undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
        elif self.exchange == 'bitfinex':
            # info and error handling
            if isinstance(msg_data, dict):
                if msg_data.get('version') and msg_data.get('version') != 2:
                    self.logger.critical('Change WSS version detected')
                if msg_data.get('platform') and msg_data.get('platform').get('status') != 1:
                    self.logger.warning(f"Exchange in maintenance mode, trying reconnect. Exchange info: {msg}")
                    await asyncio.sleep(60)
                    raise ConnectionClosed(None, None)
                elif 'code' in msg_data:
                    code = msg_data.get('code')
                    if code == 10300:
                        self.logger.warning('WSS Subscription failed (generic)')
                        raise ConnectionClosed(None, None)
                    elif code == 10301:
                        self.logger.error('WSS Already subscribed')
                    elif code == 10302:
                        raise UserWarning(f"WSS Unknown channel {ch_type}")
                    elif code == 10305:
                        raise UserWarning('WSS Reached limit of open channels')
                    elif code == 20051:
                        self.logger.warning('WSS reconnection request received from exchange')
                        raise ConnectionClosed(None, None)
                    elif code == 20060:
                        self.logger.info('WSS entering in maintenance mode, trying reconnect after 120s')
                        await asyncio.sleep(120)
                        raise ConnectionClosed(None, None)
                elif msg_data.get('event') == 'subscribed':
                    chan_id = msg_data.get('chanId')
                    self.logger.info(f"bitfinex, ch_type: {ch_type}, chan_id: {chan_id}")
                elif msg_data.get('event') == 'auth' and msg_data.get('status') == 'OK':
                    chan_id = msg_data.get('chanId')
                    self.logger.info(f"Bitfinex, user stream chan_id: {chan_id}")

            # data handling
            elif isinstance(msg_data, list) and len(msg_data) == 2 and msg_data[1] == 'hb':
                pass  # heartbeat message
            elif isinstance(msg_data, list):
                if ch_type == 'book' and isinstance(msg_data[1][-1], list):
                    self._order_book = bfx.OrderBook(msg_data[1], symbol)
                else:
                    await self._handle_event(msg_data, symbol, ch_type)
            else:
                self.logger.debug(f"Bitfinex undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
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
                    self.logger.info(f"HTX User Data Stream started for {self.trade_id}")
            elif 'subbed' in msg_data and msg_data.get('status') == 'ok':
                self.logger.info(f"Huobi WSS started: {msg_data['subbed']}")
            elif (msg_data.get('action') == 'sub' and
                  msg_data.get('code') == 500 and
                  msg_data.get('message') == '系统异常:'):
                self.logger.warning(f"Reconnecting Huobi user {ch_type} channel")
                raise ConnectionClosed(None, None)
            else:
                self.logger.debug(f"Huobi undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")

    async def ws_listener(self, request=None, symbol=None, ch_type=str()):
        if request:
            await self.websocket.send(json.dumps(request))
            await asyncio.sleep(0)
        async for msg_data in self.websocket:
            await self._handle_messages(msg_data, symbol, ch_type)

    async def bybit_heartbeat(self, req_id, interval=20):
        while True:
            await asyncio.sleep(interval)
            try:
                await self.websocket.send(json.dumps({"req_id": req_id, "op": "ping"}))
            except (ConnectionClosed, asyncio.exceptions.TimeoutError):
                break

    async def htx_keepalive(self, interval=60):
        await asyncio.sleep(interval)
        while True:
            await asyncio.sleep(interval)
            if self.ping:
                break
            else:
                self.ping = 1
        self.logger.warning("From HTX server PING timeout exceeded")
        await self.websocket.close()


class MarketEventsDataStream(EventsDataStream):
    __slots__ = ('channel', 'candles_max_time', 'endpoint')

    def __init__(self, client, endpoint, exchange, trade_id, channel=None):
        super().__init__(client, endpoint, exchange, trade_id)
        self.channel = channel
        self.candles_max_time = None
        if self.exchange == 'binance':
            registered_streams = self.client.events.registered_streams.get(self.exchange, {}).get(self.trade_id, set())
            combined_streams = "/".join(registered_streams)
            self.endpoint = f"{endpoint}/stream?streams={combined_streams}"

    async def start_wss(self):
        self.logger.info(f"Start market WSS {self.channel or ''} for {self.exchange}")
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

                tasks_manage(self.tasks, self.htx_keepalive(interval=30), f"htx_keepalive-{symbol}-{ch_type}")

        await self.ws_listener(request, symbol, ch_type)

    async def _handle_event(self, content, symbol=None, ch_type=str()):
        # self.logger.info(f"MARKET_handle_event.content: symbol: {symbol}, ch_type: {ch_type}, content: {content}")
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
        if isinstance(content, dict):
            stream_name = content["stream"]
            content = content["data"]
            content["stream"] = stream_name
            await self.client.events.wrap_event(content).fire(self.trade_id)
        elif isinstance(content, list):
            for event_content in content:
                event_content["stream"] = stream_name
                await self.client.events.wrap_event(event_content).fire(self.trade_id)


class HbpPrivateEventsDataStream(EventsDataStream):
    __slots__ = ('symbol',)

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
        tasks_manage(self.tasks, self.htx_keepalive(), f"htx_keepalive-user-{self.symbol}")
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
            self.logger.debug(f"HTXPrivateEvents.content: {content}")
            await self.client.events.wrap_event(content).fire(self.trade_id)


class BfxPrivateEventsDataStream(EventsDataStream):
    __slots__ = ()

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
    __slots__ = ('symbol',)

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
    __slots__ = ()

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
            # self.logger.info(f"_handle_event: ch_type: {ch_type}, msg_data: {msg_data}")
            event = msg_data[0]
            if event.get('orderStatus') in ("Cancelled", "PartiallyFilledCanceled"):
                self.client.wss_buffer[f"oc-{event.get('orderId')}"] = bbt.order(event, response_type=True)
        elif ch_type == 'wallet':
            event = msg_data[0]
            content = bbt.on_funds_update(event)
        if content:
            await self.client.events.wrap_event(content).fire(self.trade_id)


class UserEventsDataStream(EventsDataStream):
    __slots__ = ()

    async def start_wss(self):
        await self.websocket.send(
            json.dumps(
                compose_binance_ws_auth(self.trade_id, self.client.api_key, self.client.api_secret)
            )
        )
        await asyncio.sleep(0)
        await self._handle_messages(await self.websocket.recv())
        #
        request = {
            "id": self.trade_id,
            "method": "userDataStream.subscribe"
        }
        await self.ws_listener(request)

    async def _handle_event(self, content):
        # self.logger.debug(f"UserEventsDataStream._handle_event.content: {content}")
        await self.client.events.wrap_event(content).fire(self.trade_id)
