#!/usr/bin/python3.8
# -*- coding: utf-8 -*-

from exchanges_wrapper import __version__

import aiohttp
import asyncio
import json
import hmac
import hashlib
import random
import logging
import time

import ftx_parser as ftx

logger = logging.getLogger('exch_srv_logger')


class EventsDataStream:
    def __init__(self, client, endpoint, user_agent, exchange='binance'):
        self.client = client
        self.endpoint = endpoint
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = f"exchange-wrapper, {__version__}"
        self.exchange = exchange
        self.web_socket = None
        self.try_count = 0

    async def start(self, *args, **kwargs):
        pass  # meant to be overridden in a subclass

    async def _handle_event(self, *args):
        pass  # meant to be overridden in a subclass

    async def _handle_messages(self, web_socket, symbol=None, ch_type=None):
        # logger.debug(f"_handle_messages.START: {web_socket}, symbol: {symbol}, ch_type: {ch_type}")
        self.try_count = 0
        msg_data_prev = {}
        while True:
            msg = await web_socket.receive()
            # print(f"_handle_messages.msg: {web_socket}, {msg}")
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
                # print(f"_handle_messages.msg_data: {msg_data}")
                if self.exchange == 'binance':
                    # print(f"binance, channel: {ch_type}")
                    await self._handle_event(msg_data)
                elif self.exchange == 'ftx' and msg_data.get('type') == 'update':
                    # print(f"ftx, channel: {ch_type}")
                    if msg_data.get('channel') not in ('fills', 'orders'):
                        _msg_data = eval(repr(msg_data))
                        if ftx.ftx_stream_compare(_msg_data, msg_data_prev, ch_type):
                            # logger.debug(f"_handle_messages.msg_data_LAST: {msg_data}")
                            msg_data_binance = ftx.ftx_stream_convert(msg_data, symbol, ch_type)
                            # logger.debug(f"_handle_messages.msg_data_binance: {msg_data_binance}")
                            await self._handle_event(msg_data_binance)
                        msg_data_prev = eval(repr(msg_data))
                    else:
                        logger.debug(f"_handle_messages.msg_data: {msg_data}")
                        msg_data_binance = ftx.ftx_stream_convert(msg_data)
                        logger.debug(f"_handle_messages.msg_data_binance: {msg_data_binance}")
                        if msg_data_binance:
                            await self._handle_event(msg_data_binance)


class MarketEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent, exchange='binance', channel=None):
        super().__init__(client, endpoint, user_agent, exchange)
        self.channel = channel

    async def stop(self):
        """
        Stop market data stream
        """
        logger.debug('MarketEventsDataStream.stop()')
        if self.web_socket:
            await self.web_socket.close()
        # print(f"stop.web_socket: {self.web_socket}, _state: {self.web_socket.closed}")

    async def start(self):
        registered_streams = self.client.events.registered_streams.get(self.exchange)
        logger.debug(f"MarketEventsDataStream.start().registered_streams: {registered_streams}")
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
                elif self.exchange == 'ftx':
                    if self.client.proxy:
                        self.web_socket = await session.ws_connect(
                            self.endpoint, heartbeat=15, proxy=self.client.proxy,)
                    else:
                        self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
                    symbol = self.channel.split('@')[0]
                    ch_type = self.channel.split('@')[1]
                    request = {'op': 'subscribe', 'channel': 'ticker', 'market': symbol}
                    await self.web_socket.send_json(request)
                    await self._handle_messages(self.web_socket, symbol=symbol, ch_type=ch_type)
        except aiohttp.ClientOSError as ex:
            logger.error(f"MarketEventsDataStream.start(): try_count: {self.try_count}: {ex}")
            if self.try_count > 100:
                return
            self.try_count += 1
            await asyncio.sleep(random.uniform(0.2, 0.5) * self.try_count)
            asyncio.ensure_future(self.start())

    async def _handle_event(self, content):
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
        logger.info('FtxPrivateEventsDataStream.stop()')
        if self.web_socket:
            await self.web_socket.close()

    async def start(self):
        logger.info(f"FtxPrivateEventsDataStream.start(): exchange: {self.exchange}, endpoint: {self.endpoint}")
        async with aiohttp.ClientSession() as session:
            if self.client.proxy:
                self.web_socket = await session.ws_connect(
                    self.endpoint, heartbeat=15, proxy=self.client.proxy)
            else:
                self.web_socket = await session.ws_connect(self.endpoint, heartbeat=15)
            ts = int(time.time() * 1000)
            data = f"{ts}websocket_login"
            signature = hmac.new(self.client.api_secret.encode("utf-8"),
                                 data.encode("utf-8"),
                                 hashlib.sha256).hexdigest()
            request = {
                "op": "login",
                "args": {
                     "key": self.client.api_key,
                     "sign": signature,
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

    async def _handle_event(self, content):
        # logger.debug(f"FtxPrivateEventsDataStream._handle_event.content: {content}")
        event = self.client.events.wrap_event(content)
        await event.fire()


class UserEventsDataStream(EventsDataStream):
    def __init__(self, client, endpoint, user_agent):
        super().__init__(client, endpoint, user_agent)

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
        # logger.info(f"UserEventsDataStream.stop: {self.client}")
        if self.web_socket:
            await self.web_socket.close()

    async def start(self):
        # logger.info(f"UserEventsDataStream.start: {self.client}")
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
        # print(f"user _handle_event.content: {content}")
        event = self.client.events.wrap_event(content)
        await event.fire()
