#!/usr/bin/python3
# -*- coding: utf-8 -*-
# __version__ = "1.2.6b4"

from exchanges_wrapper import __version__

import aiohttp
import asyncio
import json
import random
import logging
import time
from decimal import Decimal
import traceback
import gzip
from datetime import datetime
from urllib.parse import urlencode, urlparse

import exchanges_wrapper.ftx_parser as ftx
import exchanges_wrapper.bitfinex_parser as bfx
import exchanges_wrapper.huobi_parser as hbp
from exchanges_wrapper.c_structures import generate_signature

logger = logging.getLogger('exch_srv_logger')


class EventsDataStream:
    def __init__(self, client, endpoint, user_agent, exchange, trade_id):
        self.client = client
        self.session = client.session
        self.endpoint = endpoint
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = f"exchanges-wrapper, {__version__}"
        self.exchange = exchange
        self.trade_id = trade_id
        self.web_socket = None
        self.try_count = 0

    async def start(self):
        try:
            await self.start_wss()
        except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectionError, asyncio.TimeoutError) as ex:
            self.try_count += 1
            delay = random.randint(1, 10) * self.try_count
            logger.error(f"WSS start({self.exchange}): {ex}, restart try count: {self.try_count}, delay: {delay}s")
            await asyncio.sleep(delay)
            asyncio.ensure_future(self.start())
        except Exception as ex:
            logger.error(f"WSS start() other exception: {ex}")
            logger.debug(traceback.format_exc())

    async def start_wss(self):
        pass  # meant to be overridden in a subclass

    async def stop(self):
        pass  # meant to be overridden in a subclass

    async def upstream_bitfinex(self, request, symbol=None, ch_type=str()):
        await self.web_socket.send_json(request)
        msg = await self.web_socket.receive_json()
        if msg.get('event') == 'info':
            if msg.get('version') != 2:
                logger.warning('Change WSS version detected')
            if msg.get('platform') and msg.get('platform').get('status'):
                logger.debug(f"BfxPrivateEventsDataStream.msg: {msg}")
                await self._handle_messages(self.web_socket, symbol, ch_type)
            else:
                logger.warning(f"Exchange in maintenance mode, trying reconnect. Exchange info: {msg}")
                await asyncio.sleep(60)
                raise aiohttp.ClientOSError

    async def _heartbeat_ftx(self, interval=15):
        request = {'op': 'ping'}
        while True:
            await asyncio.sleep(interval)
            await self.web_socket.send_json(request)

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, web_socket, symbol=None, ch_type=str()):
        order_book = None
        price = None
        while True:
            msg = await web_socket.receive()
            # logger.debug(f"_handle_messages: symbol: {symbol}, ch_type: {ch_type}, msg.type: {msg.type}")
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                if self.client.data_streams.get(self.trade_id, None):
                    raise aiohttp.ClientOSError(f"Reconnecting WSS for {symbol}:{ch_type}:{self.trade_id}")
                else:
                    logger.info(f"Event stream stopped for {symbol}:{ch_type}:{self.trade_id}")
                    break
            elif msg.type is aiohttp.WSMsgType.ERROR:
                raise aiohttp.ClientOSError(f"For {symbol}:{ch_type} something went wrong with the WSS, reconnecting")
            msg_data = json.loads(gzip.decompress(msg.data) if msg.type is aiohttp.WSMsgType.BINARY else msg.data)
            # logger.debug(f"_handle_messages: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
            if self.exchange == 'binance':
                await self._handle_event(msg_data)
            elif self.exchange == 'ftx':
                if ch_type == 'orderbook' and msg_data.get('type') == 'partial':
                    order_book = ftx.OrderBook(msg_data.get('data', {}), symbol)
                elif msg_data.get('type') == 'update':
                    if ch_type == 'ticker':
                        _price = msg_data.get('data', {}).get('last', None)
                        if price != _price:
                            price = _price
                            await self._handle_event(msg_data, symbol, ch_type, order_book)
                    else:
                        await self._handle_event(msg_data, symbol, ch_type, order_book)
            elif self.exchange == 'bitfinex':
                # info and error handling
                if isinstance(msg_data, dict):
                    if msg_data.get('event') == 'subscribed':
                        chan_id = msg_data.get('chanId')
                        logger.info(f"bitfinex, ch_type: {ch_type}, chan_id: {chan_id}")
                    elif msg_data.get('event') == 'auth' and msg_data.get('status') == 'OK':
                        chan_id = msg_data.get('chanId')
                        logger.info(f"bitfinex, user stream chan_id: {chan_id}")
                    elif 'code' in msg_data:
                        code = msg_data.get('code')
                        if code == 10300:
                            raise aiohttp.ClientOSError('WSS Subscription failed (generic)')
                        elif code == 10301:
                            logger.error('WSS Already subscribed')
                            break
                        elif code == 10302:
                            logger.error(f"WSS Unknown channel {ch_type}")
                            break
                        elif code == 10305:
                            logger.error('WSS Reached limit of open channels')
                            break
                        elif code == 20051:
                            raise aiohttp.ClientOSError('WSS reconnection request received from exchange')
                        elif code == 20060:
                            logger.info('WSS entering in maintenance mode, trying reconnect after 120s')
                            await asyncio.sleep(120)
                            raise aiohttp.ClientOSError
                # data handling
                elif 'hb' not in msg_data and isinstance(msg_data, list):
                    if ch_type == 'book' and isinstance(msg_data[1][-1], list):
                        order_book = bfx.OrderBook(msg_data[1], symbol)
                    else:
                        await self._handle_event(msg_data, symbol, ch_type, order_book)
            elif self.exchange == 'huobi':
                # print(f"_handle_messages: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")
                if msg_data.get('ping'):
                    await self.web_socket.send_json({"pong": msg_data.get('ping')})
                elif msg_data.get('action') == 'ping':
                    pong = {
                        "action": "pong",
                        "data": {
                              "ts": msg_data.get('data').get('ts')
                        }
                    }
                    await self.web_socket.send_json(pong)
                elif msg_data.get('action') == 'req' and msg_data.get('code') == 200 and msg_data.get('ch') == 'auth':
                    return
                elif (msg_data.get('action') == 'sub' and
                      msg_data.get('code') == 500 and
                      msg_data.get('message') == '系统异常:'):
                    raise aiohttp.ClientOSError(f"Reconnecting Huobi user {ch_type} WSS")
                elif msg_data.get('tick') or msg_data.get('data'):
                    if ch_type == 'ticker':
                        _price = msg_data.get('tick', {}).get('lastPrice', None)
                        if price != _price:
                            price = _price
                            await self._handle_event(msg_data, symbol, ch_type)
                    else:
                        await self._handle_event(msg_data, symbol, ch_type)
                else:
                    logger.debug(f"Huobi undefined WSS: symbol: {symbol}, ch_type: {ch_type}, msg_data: {msg_data}")


class MarketEventsDataStream(EventsDataStream):

    def __init__(self, client, endpoint, user_agent, exchange, trade_id, channel=None):
        super().__init__(client, endpoint, user_agent, exchange, trade_id)
        self.channel = channel
        self.candles_max_time = None

    async def stop(self):
        """
        Stop market data stream
        """
        logger.info(f"Market WSS stop for {self.exchange}:{self.trade_id}:{self.channel}")
        if self.web_socket:
            await self.web_socket.close()

    async def start_wss(self):
        logger.info(f"Start market WSS {self.channel} for {self.exchange}")
        registered_streams = self.client.events.registered_streams.get(self.exchange, {}).get(self.trade_id, set())
        if self.exchange == 'binance':
            combined_streams = "/".join(registered_streams)
            self.web_socket = await self.session.ws_connect(f"{self.endpoint}/stream?streams={combined_streams}",
                                                            proxy=self.client.proxy)
            logger.info(f"Combined events stream started: {combined_streams}")
            await self._handle_messages(self.web_socket)
        else:
            symbol = self.channel.split('@')[0]
            ch_type = self.channel.split('@')[1]
            request = {}
            if self.exchange == 'ftx':
                self.web_socket = await self.session.ws_connect(self.endpoint,
                                                                receive_timeout=30,
                                                                proxy=self.client.proxy)
                if ch_type == 'miniTicker':
                    ch_type = 'ticker'
                elif ch_type == 'depth5':
                    ch_type = 'orderbook'
                request = {'op': 'subscribe', 'channel': ch_type, 'market': symbol}
                await self.web_socket.send_json(request)
                _task = asyncio.ensure_future(self._heartbeat_ftx())
                try:
                    await self._handle_messages(self.web_socket, symbol=symbol, ch_type=ch_type)
                finally:
                    _task.cancel()
            elif self.exchange == 'bitfinex':
                self.web_socket = await self.session.ws_connect(self.endpoint, heartbeat=15, proxy=self.client.proxy)
                if ch_type == 'miniTicker':
                    ch_type = 'ticker'
                    request = {'event': 'subscribe', 'channel': ch_type, 'pair': symbol}
                elif 'kline_' in ch_type:
                    ch_type = ch_type.replace('kline_', 'candles_')
                    tf = ch_type.split('_')[1]
                    request = {'event': 'subscribe', 'channel': 'candles', 'key': f"trade:{tf}:{symbol}"}
                elif ch_type == 'depth5':
                    ch_type = 'book'
                    request = {'event': 'subscribe', 'channel': ch_type, 'symbol': symbol, 'prec': 'P0', }
                await self.upstream_bitfinex(request, symbol, ch_type)
            elif self.exchange == 'huobi':
                self.web_socket = await self.session.ws_connect(self.endpoint,
                                                                receive_timeout=20,
                                                                proxy=self.client.proxy,
                                                                autoping=False)
                if ch_type == 'miniTicker':
                    ch_type = 'ticker'
                    request = {'sub': f"market.{symbol}.{ch_type}"}
                elif 'kline_' in ch_type:
                    tf = ch_type.split('_')[1]
                    request = {'sub': f"market.{symbol}.kline.{hbp.interval(tf)}"}
                elif ch_type == 'depth5':
                    request = {'sub': f"market.{symbol}.depth.step0"}
                await self.web_socket.send_json(request)
                await self._handle_messages(self.web_socket, symbol=symbol, ch_type=ch_type)

    async def _handle_event(self, content, symbol=None, ch_type=str(), order_book=None):
        # logger.info(f"MARKET_handle_event.content: symbol: {symbol}, ch_type: {ch_type}, content: {content}")
        self.try_count = 0
        if self.exchange == 'bitfinex':
            if 'candles' in ch_type:
                if isinstance(content[1][-1], list):
                    bfx_data = content[1][-1]
                else:
                    bfx_data = content[1]
                if self.candles_max_time is None or bfx_data[0] >= self.candles_max_time:
                    self.candles_max_time = bfx_data[0]
                    content = bfx.candle(bfx_data, symbol, ch_type)
                else:
                    return
            elif ch_type == 'ticker':
                content = bfx.ticker(content[1], symbol)
            elif ch_type == 'book' and isinstance(order_book, bfx.OrderBook):
                order_book.update_book(content[1])
                content = order_book.get_book()
        elif self.exchange == 'ftx':
            if ch_type == 'orderbook' and isinstance(order_book, ftx.OrderBook):
                if content['data']['checksum'] == order_book.update_book(content['data']):
                    content = order_book.get_book()
                else:
                    logger.warning("For orderbook WSS lost the current state, restarting the stream")
                    await asyncio.sleep(1)
                    raise aiohttp.ClientOSError
            elif ch_type == 'ticker':
                content = ftx.stream_convert(content, symbol, ch_type)
            else:
                return
        elif self.exchange == 'huobi':
            if ch_type == 'ticker':
                content = hbp.ticker(content, symbol)
            elif 'kline_' in ch_type:
                content = hbp.candle(content, symbol, ch_type)
            elif ch_type == 'depth5':
                content = hbp.order_book_ws(content, symbol)
            else:
                return
        #
        stream_name = None
        if isinstance(content, dict) and "stream" in content:
            stream_name = content["stream"]
            content = content["data"]
            content["stream"] = stream_name
            await self.client.events.wrap_event(content).fire()
        elif isinstance(content, list):
            for event_content in content:
                event_content["stream"] = stream_name
                await self.client.events.wrap_event(event_content).fire()


class HbpPrivateEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent, exchange, trade_id, symbol):
        super().__init__(client, endpoint, user_agent, exchange, trade_id)
        self.symbol = symbol

    async def stop(self):
        """
        Stop data stream
        """
        if self.web_socket:
            await self.web_socket.close()

    async def start_wss(self):
        self.web_socket = await self.session.ws_connect(self.endpoint,
                                                        receive_timeout=60,
                                                        proxy=self.client.proxy,
                                                        autoping=False)
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
        await self.web_socket.send_json(request)
        await self._handle_messages(self.web_socket)

        request = {
            "action": "sub",
            "ch": "accounts.update#2"
        }
        await self.web_socket.send_json(request)

        request = {
            "action": "sub",
            "ch": f"trade.clearing#{self.symbol.lower()}#0"
        }
        await self.web_socket.send_json(request)

        await self._handle_messages(self.web_socket)

    async def _handle_event(self, msg_data, *args):
        self.try_count = 0
        content = None
        if msg_data.get('data').get('accountId') == self.client.hbp_account_id:
            if msg_data.get('ch') == 'accounts.update#2':
                content = hbp.on_funds_update(msg_data)
            elif msg_data.get('ch') == f"trade.clearing#{self.symbol.lower()}#0":
                data = msg_data.get('data')
                content = hbp.on_order_update(data)
        if content:
            logger.debug(f"HbpPrivateEventsDataStream._handle_event.content: {content}")
            await self.client.events.wrap_event(content).fire()


class FtxPrivateEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent, exchange, trade_id, sub_account=None):
        super().__init__(client, endpoint, user_agent, exchange, trade_id)
        self.sub_account = sub_account

    async def stop(self):
        """
        Stop data stream
        """
        if self.web_socket:
            await self.web_socket.close()

    async def start_wss(self):
        self.web_socket = await self.session.ws_connect(self.endpoint, proxy=self.client.proxy, receive_timeout=30)
        ts = int(time.time() * 1000)
        data = f"{ts}websocket_login"
        request = {
            "op": "login",
            "args": {
                 "key": self.client.api_key,
                 "sign": generate_signature(self.exchange, self.client.api_secret, data),
                 "time": ts
             }
        }
        if self.sub_account:
            request['args']['subaccount'] = self.sub_account
        await self.web_socket.send_json(request)
        request = {'op': 'subscribe', 'channel': 'fills'}
        await self.web_socket.send_json(request)
        request = {'op': 'subscribe', 'channel': 'orders'}
        await self.web_socket.send_json(request)
        _task = asyncio.ensure_future(self._heartbeat_ftx())
        try:
            await self._handle_messages(self.web_socket)
        finally:
            _task.cancel()

    async def _handle_event(self, msg_data, *args):
        self.try_count = 0
        content = None
        if msg_data.get('channel') in ('fills', 'orders'):
            content = ftx.stream_convert(msg_data)
        if content:
            logger.debug(f"FtxPrivateEventsDataStream._handle_event.content: {content}")
            await self.client.events.wrap_event(content).fire()


class BfxPrivateEventsDataStream(EventsDataStream):

    async def stop(self):
        """
        Stop data stream
        """
        if self.web_socket:
            await self.web_socket.close()

    async def start_wss(self):
        self.web_socket = await self.session.ws_connect(self.endpoint, heartbeat=15, proxy=self.client.proxy)
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
        await self.upstream_bitfinex(request)

    async def _handle_event(self, msg_data, *args):
        self.try_count = 0
        logger.debug(f"USER_handle_event.msg_data: {msg_data}")
        content = None
        if msg_data[1] in ('wu', 'ws'):
            content = bfx.on_funds_update(msg_data[2])
        elif msg_data[1] == 'oc':
            order_id = msg_data[2][0]
            last_event = self.client.active_orders.get(order_id, {}).get('lastEvent', ())
            content = bfx.on_order_update(msg_data[2], last_event)
            if msg_data[2][13] == 'CANCELED':
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
            await self.client.events.wrap_event(content).fire()


class UserEventsDataStream(EventsDataStream):

    async def _heartbeat(self, listen_key, interval=60 * 30):
        # 30 minutes is recommended according to
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        while True:
            await asyncio.sleep(interval)
            await self.client.keep_alive_listen_key(listen_key)

    async def stop(self):
        """
        Stop user data stream
        """
        # logger.info(f"UserEventsDataStream.stop: handlers: {self.client.events.handlers}")
        if self.web_socket:
            await self.web_socket.close()

    async def start_wss(self):
        listen_key = (await self.client.create_listen_key())["listenKey"]
        self.web_socket = await self.session.ws_connect(f"{self.endpoint}/ws/{listen_key}",
                                                        heartbeat=15,
                                                        proxy=self.client.proxy)
        _task = asyncio.ensure_future(self._heartbeat(listen_key))
        try:
            await self._handle_messages(self.web_socket)
        finally:
            _task.cancel()

    async def _handle_event(self, content):
        self.try_count = 0
        logger.debug(f"UserEventsDataStream._handle_event.content: {content}")
        event = self.client.events.wrap_event(content)
        await event.fire()
