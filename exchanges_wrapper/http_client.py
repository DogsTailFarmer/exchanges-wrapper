#!/usr/bin/python3
# -*- coding: utf-8 -*-

import json
from urllib.parse import urlencode, urlparse
from exchanges_wrapper import __version__
import logging
import time
from datetime import datetime
from exchanges_wrapper.c_structures import generate_signature
from exchanges_wrapper.errors import (
    RateLimitReached,
    ExchangeError,
    WAFLimitViolated,
    IPAddressBanned,
    HTTPError,
    QueryCanceled,
)

logger = logging.getLogger('exch_srv_logger')


class HttpClient:
    def __init__(self,
                 api_key,
                 api_secret,
                 endpoint,
                 user_agent,
                 proxy,
                 session,
                 exchange,
                 sub_account):
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint
        self.rate_limit_reached = False
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = f"exchange-wrapper, {__version__}"
        self.proxy = proxy
        self.session = session
        self.exchange = exchange
        self.sub_account = sub_account

    async def handle_errors(self, response):
        if response.status >= 500:
            raise ExchangeError(f"An issue occurred on exchange's side: {response.status}: {response.url}:"
                                f" {response.reason}")
        if response.status == 429:
            self.rate_limit_reached = True if self.exchange == 'binance' else None
            raise RateLimitReached(RateLimitReached.message)
        payload = await response.json()
        if payload and "code" in payload:
            # as defined here: https://github.com/binance/binance-spot-api-docs/blob/
            # master/errors.md#error-codes-for-binance-2019-09-25
            raise ExchangeError(payload["msg"])
        if response.status >= 400:
            logger.debug(f"handle_errors.response.status >= 400: {payload}")
            if response.status == 400 and payload and payload.get("error", str()) == "ERR_RATE_LIMIT":
                raise RateLimitReached(RateLimitReached.message)
            elif response.status == 403:
                raise WAFLimitViolated(WAFLimitViolated.message)
            elif response.status == 418:
                raise IPAddressBanned(IPAddressBanned.message)
            else:
                raise HTTPError(f"Malformed request: {payload}")
        if self.exchange in ('binance', 'bitfinex'):
            return payload
        elif self.exchange == 'ftx' and payload and payload.get('success'):
            return payload.get('result')
        elif self.exchange == 'huobi' and payload and payload.get('status') == 'ok':
            return payload.get('data', payload.get('tick'))
        else:
            raise HTTPError(f"API request failed: {payload}")

    async def send_api_call(self,
                            path,
                            method="GET",
                            signed=False,
                            send_api_key=True,
                            endpoint=None,
                            timeout=None,
                            **kwargs):
        # print(f"send_api_call.request: path: {path}, kwargs: {kwargs}")
        if self.rate_limit_reached:
            raise QueryCanceled(
                "Rate limit reached, to avoid an IP ban, this query has been cancelled"
            )
        _endpoint = endpoint or self.endpoint
        query_kwargs = {}
        _params = {}
        content = str()
        ftx_post = self.exchange == 'ftx' and method == 'POST'
        bfx_post = self.exchange == 'bitfinex' and ((method == 'POST' and kwargs) or "params" in kwargs)
        ts = None
        if self.exchange == 'huobi':
            url = f"{_endpoint}/{path}?"
            if signed:
                ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                _params = {
                    "AccessKeyId": self.api_key,
                    "SignatureMethod": 'HmacSHA256',
                    "SignatureVersion": '2',
                    "Timestamp": ts
                }
                if method == 'GET':
                    _params.update(**kwargs)
                else:
                    query_kwargs.update({'json': kwargs})
                signature_payload = f"{method}\n{urlparse(_endpoint).hostname}\n/{path}\n{urlencode(_params)}"
                signature = generate_signature(self.exchange, self.api_secret, signature_payload)
                _params.update({'Signature': signature})
            else:
                if method == 'GET':
                    _params = kwargs
            url += urlencode(_params)
        else:
            _params = json.dumps(kwargs) if ftx_post or bfx_post else None
            url = f'{_endpoint}{path}' if self.exchange == 'binance' else f'{_endpoint}/{path}'
            ts = int(time.time() * 1000)

        if self.exchange == 'binance':
            query_kwargs = dict({"headers": {"User-Agent": self.user_agent}}, **kwargs,)
            if send_api_key:
                query_kwargs["headers"]["X-MBX-APIKEY"] = self.api_key
        elif self.exchange in ('ftx', 'bitfinex'):
            # https://help.ftx.com/hc/en-us/articles/360052595091-2020-11-20-Ratelimit-Updates
            query_kwargs = {"headers": {"Accept": 'application/json'}}
            if self.exchange == 'ftx':
                query_kwargs["headers"]["FTX-KEY"] = self.api_key
                if self.sub_account:
                    query_kwargs["headers"]["FTX-SUBACCOUNT"] = self.sub_account
            content += urlencode(kwargs, safe='/')
            if content and not ftx_post and not bfx_post:
                url += f'?{content}'
            if bfx_post and "params" in kwargs:
                query_kwargs.update({'data': _params})
        if signed and self.exchange != 'huobi':
            query_kwargs["headers"]["Content-Type"] = 'application/json'
            if self.exchange == 'binance':
                location = "params" if "params" in kwargs else "data"
                query_kwargs[location]["timestamp"] = str(ts)
                if "params" in kwargs:
                    content += urlencode(kwargs["params"])
                if "data" in kwargs:
                    content += urlencode(kwargs["data"])
                query_kwargs[location]["signature"] = generate_signature(self.exchange, self.api_secret, content)
                if self.proxy:
                    query_kwargs["proxy"] = self.proxy
            elif self.exchange == 'ftx':
                if ftx_post:
                    query_kwargs.update({'data': _params})
                    content = f"{_params}"
                signature_payload = f'{ts}{method}/api/{path}'
                if content:
                    if ftx_post:
                        signature_payload += f'{content}'
                    else:
                        signature_payload += f'?{content}'
                query_kwargs["headers"]["FTX-SIGN"] = generate_signature(self.exchange,
                                                                         self.api_secret,
                                                                         signature_payload)
                query_kwargs["headers"]["FTX-TS"] = str(ts)
            elif self.exchange == 'bitfinex':
                if bfx_post:
                    query_kwargs.update({'data': _params})
                if send_api_key:
                    query_kwargs["headers"]["bfx-apikey"] = self.api_key
                signature_payload = f'/api/{path}{ts}'
                if _params:
                    signature_payload += f"{_params}"
                query_kwargs["headers"]["bfx-signature"] = generate_signature(self.exchange,
                                                                              self.api_secret,
                                                                              signature_payload)
                query_kwargs["headers"]["bfx-nonce"] = str(ts)
        # print(f"send_api_call.request: url: {url}, query_kwargs: {query_kwargs}")
        async with self.session.request(method, url, timeout=timeout, **query_kwargs) as response:
            # print(f"send_api_call.response: url: {response.url}, status: {response.status}")
            return await self.handle_errors(response)
