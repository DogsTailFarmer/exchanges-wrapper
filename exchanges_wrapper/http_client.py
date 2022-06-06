#!/usr/bin/python3.8
# -*- coding: utf-8 -*-

import json
from urllib.parse import urlencode
from exchanges_wrapper import __version__
import logging
import aiohttp
import hashlib
import hmac
import time
from errors import (
    RateLimitReached,
    BinanceError,
    WAFLimitViolated,
    IPAddressBanned,
    HTTPError,
    QueryCanceled,
)

logger = logging.getLogger('exch_srv_logger')


class HttpClient:
    def __init__(self, api_key, api_secret, endpoint, user_agent, proxy,
                 session, exchange='binance', sub_account=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint
        self.rate_limit_reached = False
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = f"exchange-wrapper, {__version__}"
        self.proxy = proxy
        self.session = session if session else aiohttp.ClientSession()
        self.exchange = exchange
        self.sub_account = sub_account

    def _generate_signature(self, data):
        return hmac.new(self.api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()

    async def handle_errors(self, response):
        if response.status >= 500:
            logger.warning(f"An issue occurred on exchange's side: {response.status}: {response.url}")
            return {'success': False}
        if response.status == 429:
            self.rate_limit_reached = True if self.exchange == 'binance' else None
            raise RateLimitReached()
        # print(f"handle_errors.response: {response}")
        payload = await response.json()
        if payload and "code" in payload:
            # as defined here: https://github.com/binance/binance-spot-api-docs/blob/
            # master/errors.md#error-codes-for-binance-2019-09-25
            raise BinanceError(payload["msg"])
        if response.status >= 400:
            logger.error(f"handle_errors.response.status >= 400: {payload}")
            if response.status == 403:
                raise WAFLimitViolated()
            elif response.status == 418:
                raise IPAddressBanned()
            else:
                raise HTTPError(f"Malformed request: {payload}")
        # print(f"handle_errors.payload: {payload}")
        return payload

    async def send_api_call(
        self, path, method="GET", signed=False, send_api_key=True, **kwargs
    ):
        if self.rate_limit_reached:
            raise QueryCanceled(
                "Rate limit reached, to avoid an IP ban, this query has been automatically cancelled"
            )
        # return the JSON body of a call to Binance REST API
        # print(f"send_api_call.kwargs: {kwargs}")
        query_kwargs = {}
        content = str()
        ftx_post = self.exchange == 'ftx' and method == 'POST'
        _params = json.dumps(kwargs) if ftx_post else None
        url = f'{self.endpoint}{path}' if self.exchange == 'binance' else f'{self.endpoint}/{path}'
        if self.exchange == 'binance':
            query_kwargs = dict({"headers": {"User-Agent": self.user_agent}}, **kwargs,)
            if send_api_key:
                query_kwargs["headers"]["X-MBX-APIKEY"] = self.api_key
        elif self.exchange == 'ftx':
            # https://help.ftx.com/hc/en-us/articles/360052595091-2020-11-20-Ratelimit-Updates
            query_kwargs = {"headers": {"FTX-KEY": self.api_key}}
            content += urlencode(kwargs, safe='/')
            # print(f"send_api_call.content: {content}")
            if content and not ftx_post:
                url += f'?{content}'
            # print(f"send_api_call.url: {url}")
            if self.sub_account:
                query_kwargs["headers"]["FTX-SUBACCOUNT"] = self.sub_account
        if signed:
            if self.exchange == 'binance':
                location = "params" if "params" in kwargs else "data"
                query_kwargs[location]["timestamp"] = str(int(time.time() * 1000))
                if "params" in kwargs:
                    content += urlencode(kwargs["params"])
                if "data" in kwargs:
                    content += urlencode(kwargs["data"])
                query_kwargs[location]["signature"] = self._generate_signature(content)
                if self.proxy:
                    query_kwargs["proxy"] = self.proxy
            elif self.exchange == 'ftx':
                if ftx_post:
                    query_kwargs["headers"]["Content-Type"] = 'application/json'
                    query_kwargs.update({'data': _params})
                    content = f"{_params}"
                ts = int(time.time() * 1000)
                signature_payload = f'{ts}{method}/api/{path}'
                if content:
                    if ftx_post:
                        signature_payload += f'{content}'
                    else:
                        signature_payload += f'?{content}'
                # print(f"send_api_call.signature_payload: {signature_payload}")
                signature = self._generate_signature(signature_payload)
                query_kwargs["headers"]["FTX-SIGN"] = signature
                query_kwargs["headers"]["FTX-TS"] = str(ts)
        # logger.debug(f"send_api_call: method: {method}, url: {url}, **query_kwargs: {query_kwargs}")
        async with self.session.request(method, url, **query_kwargs) as response:
            # logger.debug(f"send_api_call.response: {response}")
            return await self.handle_errors(response)

    async def close_session(self):
        await self.session.close()
