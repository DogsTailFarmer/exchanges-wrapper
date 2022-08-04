#!/usr/bin/python3.8
# -*- coding: utf-8 -*-

from exchanges_wrapper import __version__

import aiohttp
import asyncio
import json
import random
import logging
import time
from decimal import Decimal

import exchanges_wrapper.ftx_parser as ftx
import exchanges_wrapper.bitfinex_parser as bfx
from exchanges_wrapper.c_structures import generate_signature

logger = logging.getLogger('exch_srv_logger')


class EventsDataStream:
    def __init__(self, client, endpoint, user_agent, exchange):
        self.client = client
        self.endpoint = endpoint
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = f"exchange-wrapper, {__version__}"
        self.exchange = exchange
        self.web_socket = None
        self.try_count = 0

    async def start(self):
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
                print(f"BfxPrivateEventsDataStream.msg: {msg}")
                await self._handle_messages(self.web_socket, symbol, ch_type)
            else:
                logger.info(f"Exchange in maintenance mode, trying reconnect. Exchange info: {msg}")
                await asyncio.sleep(10)
                raise aiohttp.ClientOSError

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, web_socket, symbol=None, ch_type=str()):
        logger.debug(f"_handle_messages: symbol: {symbol}, ch_type: {ch_type}")
        self.try_count = 0
        order_book = None
        price = None
        while True:
            msg = await web_socket.receive()
            # logger.debug(f"_handle_messages: symbol: {symbol}, ch_type: {ch_type}, msg: {msg}")
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                logger.error(
                    "Trying to receive something while the websocket is closed! Trying to reconnect."
                )
                asyncio.ensure_future(self.start())
                break
            elif msg.type is aiohttp.WSMsgType.ERROR:
                logger.error("Something went wrong with the websocket, reconnecting...")
                asyncio.ensure_future(self.start())
                break
            elif msg.type == aiohttp.WSMsgType.CLOSING:
                logger.info(f"_handle_messages loop is stopped for {symbol} {ch_type}")
                break
            if msg.data:
                msg_data = json.loads(msg.data)
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
                            print(f"bitfinex, ch_type: {ch_type}, chan_id: {chan_id}")
                        elif msg_data.get('event') == 'auth' and msg_data.get('status') == 'OK':
                            chan_id = msg_data.get('chanId')
                            print(f"bitfinex, user stream chan_id: {chan_id}")
                        elif 'code' in msg_data:
                            code = msg_data.get('code')
                            if code == 10300:
                                logger.error('WSS Subscription failed (generic)')
                                raise aiohttp.ClientOSError
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
                                logger.info('WSS reconnection request received from exchange')
                                asyncio.ensure_future(self.start())
                                break
                            elif code == 20060:
                                logger.info('WSS entering in maintenance mode, trying reconnect after 120s')
                                await asyncio.sleep(120)
                                asyncio.ensure_future(self.start())
                                break
                    # data handling
                    elif 'hb' not in msg_data and isinstance(msg_data, list):
                        if ch_type == 'book' and isinstance(msg_data[1][-1], list):
                            order_book = bfx.OrderBook(msg_data[1], symbol)
                        else:
                            await self._handle_event(msg_data, symbol, ch_type, order_book)


class MarketEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent, exchange, channel=None):
        super().__init__(client, endpoint, user_agent, exchange)
        self.channel = channel
        self.candles_max_time = None

    async def stop(self):
        """
        Stop market data stream
        """
        if self.web_socket:
            logger.debug('MarketEventsDataStream.stop()')
            await self.web_socket.close()
        # print(f"stop.web_socket: {self.web_socket}, _state: {self.web_socket.closed}")

    async def start(self):
        await self.stop()
        registered_streams = self.client.events.registered_streams.get(self.exchange)
        logger.debug(f"MarketEventsDataStream.start(): exchange: {self.exchange},"
                     f" channel: {self.channel},"
                     f" endpoint: {self.endpoint}")
        try:
            async with aiohttp.ClientSession() as session:
                if self.exchange == 'binance':
                    combined_streams = "/".join(registered_streams)
                    # print(f"start.combined_streams: {self.endpoint}/stream?streams={combined_streams}")
                    if self.client.proxy:
                        self.web_socket = await session.ws_connect(
                            f"{self.endpoint}/stream?streams={combined_streams}",
                            proxy=self.client.proxy,
                        )
                    else:
                        self.web_socket = await session.ws_connect(
                            f"{self.endpoint}/stream?streams={combined_streams}"
                        )
                    await self._handle_messages(self.web_socket)
                else:
                    symbol = self.channel.split('@')[0]
                    ch_type = self.channel.split('@')[1]
                if self.exchange == 'ftx':
                    if ch_type == 'miniTicker':
                        ch_type = 'ticker'
                    elif ch_type == 'depth5':
                        ch_type = 'orderbook'
                    if self.client.proxy:
                        self.web_socket = await session.ws_connect(
                            self.endpoint, heartbeat=15, proxy=self.client.proxy)
                    else:
                        self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
                    request = {'op': 'subscribe', 'channel': ch_type, 'market': symbol}
                    await self.web_socket.send_json(request)
                    await self._handle_messages(self.web_socket, symbol=symbol, ch_type=ch_type)
                elif self.exchange == 'bitfinex':
                    if ch_type == 'miniTicker':
                        ch_type = 'ticker'
                    elif 'kline_' in ch_type:
                        ch_type = ch_type.replace('kline_', 'candles_')
                    elif ch_type == 'depth5':
                        ch_type = 'book'
                    #
                    if self.client.proxy:
                        self.web_socket = await session.ws_connect(
                            self.endpoint, heartbeat=15, proxy=self.client.proxy)
                    else:
                        self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
                    #
                    if 'candles' in ch_type:
                        tf = ch_type.split('_')[1]
                        request = {'event': 'subscribe', 'channel': 'candles', 'key': f"trade:{tf}:{symbol}"}
                    elif ch_type == 'ticker':
                        request = {'event': 'subscribe', 'channel': ch_type, 'pair': symbol}
                    elif ch_type == 'book':
                        request = {'event': 'subscribe', 'channel': ch_type, 'symbol': symbol, 'prec': 'P0', }
                    #
                    await self.upstream_bitfinex(request, symbol, ch_type)
        except aiohttp.ClientOSError as ex:
            logger.error(f"MarketEventsDataStream.start(): try_count: {self.try_count}: {ex}")
            if self.try_count > 100:
                return
            self.try_count += 1
            await asyncio.sleep(random.uniform(0.2, 0.5) * self.try_count)
            asyncio.ensure_future(self.start())

    async def _handle_event(self, content, symbol=None, ch_type=str(), order_book=None):
        # logger.debug(f"MARKET_handle_event.content: symbol: {symbol}, ch_type: {ch_type}, content: {content}")
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
        #
        stream_name = None
        if "stream" in content:
            stream_name = content["stream"]
            content = content["data"]
        if isinstance(content, list):
            print('list')
            for event_content in content:
                event_content["stream"] = stream_name
                await self.client.events.wrap_event(event_content).fire()
        else:
            content["stream"] = stream_name
            await self.client.events.wrap_event(content).fire()


class FtxPrivateEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent, exchange, sub_account=None):
        super().__init__(client, endpoint, user_agent, exchange)
        self.sub_account = sub_account

    async def stop(self):
        """
        Stop data stream
        """
        if self.web_socket:
            logger.info('FtxPrivateEventsDataStream.stop()')
            await self.web_socket.close()

    async def start(self):
        await self.stop()
        logger.debug(f"FtxPrivateEventsDataStream.start(): exchange: {self.exchange}, endpoint: {self.endpoint}")
        async with aiohttp.ClientSession() as session:
            if self.client.proxy:
                self.web_socket = await session.ws_connect(
                    self.endpoint, heartbeat=15, proxy=self.client.proxy)
            else:
                self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
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
            await self._handle_messages(self.web_socket)

    async def _handle_event(self, msg_data, *args):
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
            logger.info('BfxPrivateEventsDataStream.stop()')
            await self.web_socket.close()

    async def start(self):
        await self.stop()
        logger.debug(f"BfxPrivateEventsDataStream.start(): exchange: {self.exchange}, endpoint: {self.endpoint}")
        async with aiohttp.ClientSession() as session:
            if self.client.proxy:
                self.web_socket = await session.ws_connect(
                    self.endpoint, heartbeat=15, proxy=self.client.proxy)
            else:
                self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
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

    async def _heartbeat(
        self, listen_key, interval=60 * 30
    ):  # 30 minutes is recommended according to
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md#pingkeep-alive-a-listenkey
        while True:
            await asyncio.sleep(interval)
            await self.client.keep_alive_listen_key(listen_key)

    async def stop(self):
        """
        Stop user data stream
        """
        if self.web_socket:
            logger.info(f"UserEventsDataStream.stop: {self.client}")
            await self.web_socket.close()

    async def start(self):
        await self.stop()
        logger.debug(f"UserEventsDataStream.start(): exchange: {self.exchange}, endpoint: {self.endpoint}")
        async with aiohttp.ClientSession() as session:
            listen_key = (await self.client.create_listen_key())["listenKey"]
            if self.client.proxy:
                self.web_socket = await session.ws_connect(
                    f"{self.endpoint}/ws/{listen_key}"
                )
            else:
                self.web_socket = await session.ws_connect(
                    f"{self.endpoint}/ws/{listen_key}", proxy=self.client.proxy
                )
            asyncio.ensure_future(self._heartbeat(listen_key))
            await self._handle_messages(self.web_socket)

    async def _handle_event(self, content):
        logger.debug(f"UserEventsDataStream._handle_event.content: {content}")
        event = self.client.events.wrap_event(content)
        await event.fire()
