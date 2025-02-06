import asyncio
import ujson as json
from urllib.parse import urlencode, urlparse

import aiohttp
import logging
import time
from datetime import datetime, timezone
from crypto_ws_api.ws_session import generate_signature
from exchanges_wrapper.errors import (
    RateLimitReached,
    ExchangeError,
    WAFLimitViolated,
    IPAddressBanned,
    HTTPError,
    QueryCanceled,
)
from exchanges_wrapper.parsers.bybit import RateLimitHandler


logger = logging.getLogger(__name__)

AJ = 'application/json'
STATUS_BAD_REQUEST = 400
STATUS_UNAUTHORIZED = 401
STATUS_FORBIDDEN = 403
STATUS_I_AM_A_TEAPOT = 418  # HTTP status code for IPAddressBanned
ERR_TIMESTAMP_OUTSIDE_RECV_WINDOW = "Timestamp for this request is outside of the recvWindow"
TIMEOUT = aiohttp.ClientTimeout(total=60)

class HttpClient:
    def __init__(self, params: dict):
        self.api_key = params['api_key']
        self.api_secret = params['api_secret']
        self.passphrase = params['passphrase']
        self.endpoint = params['endpoint']
        self.exchange = params['exchange']
        self.test_net = params['test_net']
        self.rate_limit_reached = False
        self.rest_cycle_lock = asyncio.Lock()
        self.session = None
        self._session_mutex = asyncio.Lock()
        self.ex_imps = {}  #  exchanges implementation
        self.declare_exchanges_implementation()
        self.rate_limit_handler = RateLimitHandler() if self.exchange == 'bybit' else None

    def declare_exchanges_implementation(self):
        # noinspection PyTypeChecker
        self.ex_imps = {
        'binance': self._binance_request,
        'bitfinex': self._bitfinex_request,
        'bybit': self._bybit_request,
        'huobi': self._huobi_request,
        'okx': self._okx_request
        }

    async def _create_session_if_required(self):
        if self.session is None or self.session.closed:
            async with self._session_mutex:
                self.session = aiohttp.ClientSession(timeout=TIMEOUT)

    async def handle_errors(self, response, path=None):
        if response.status >= 500:
            raise ExchangeError(
                f"{'API request rejected' if self.exchange == 'bitfinex' else 'An issue occurred on exchange side'}:"
                f" {response.status}: {response.url}: {response.reason}"
            )
        if response.status == 429 or (self.exchange == 'bybit' and response.status == STATUS_FORBIDDEN):
            logger.error(f"API RateLimitReached: {response.url}")
            self.rate_limit_reached = self.exchange in ('binance', 'okx', 'bybit')
            raise RateLimitReached(RateLimitReached.message)

        try:
            payload = await response.json()
        except aiohttp.ContentTypeError:
            payload = None

        if response.status >= 400:
            if response.status == STATUS_BAD_REQUEST:
                if payload:
                    if payload.get("error", "") == "ERR_RATE_LIMIT":
                        self.rate_limit_reached = True
                        raise RateLimitReached(RateLimitReached.message)
                    elif self.exchange == 'binance' and payload.get('code', 0) == -1021:
                        raise ExchangeError(ERR_TIMESTAMP_OUTSIDE_RECV_WINDOW)
                    else:
                        raise ExchangeError(f"ExchangeError: {payload}")
                elif response.reason != "Bad Request":
                    raise ExchangeError(f"ExchangeError: {response.reason}:{response.text}")

            elif (
                    response.status == STATUS_UNAUTHORIZED
                    and self.exchange == 'okx'
                    and payload
                    and payload.get('code', 0) == '50102'
            ):
                raise ExchangeError(ERR_TIMESTAMP_OUTSIDE_RECV_WINDOW)
            elif response.status == STATUS_FORBIDDEN and self.exchange != 'okx':
                raise WAFLimitViolated(WAFLimitViolated.message)
            elif response.status == STATUS_I_AM_A_TEAPOT:
                raise IPAddressBanned(IPAddressBanned.message)
            else:
                raise HTTPError(f"Malformed request: {payload}:{response.reason}:{response.text}")

        if self.exchange == 'bybit' and payload:
            if payload.get('retCode') == 0:
                return payload.get('result'), payload.get('time')
            elif payload.get('retCode') == 10002:
                raise ExchangeError(ERR_TIMESTAMP_OUTSIDE_RECV_WINDOW)
            elif payload.get('retCode') == 10006:
                self.rate_limit_handler.fire_exceeded_rate_limit(path)
                logger.warning(f"ByBit API: {payload.get('retMsg')}")
                return payload.get('result'), payload.get('time')
            else:
                raise ExchangeError(f"API request failed: {response.status}:{response.reason}:{payload}")
        elif self.exchange == 'huobi' and payload and (payload.get('status') == 'ok' or payload.get('ok')):
            return payload.get('data', payload.get('tick'))
        elif self.exchange == 'okx' and payload and payload.get('code') == '0':
            return payload.get('data', [])
        elif self.exchange not in ('binance', 'bitfinex') \
                or (self.exchange == 'binance' and payload and "code" in payload):
            raise ExchangeError(f"API request failed: {response.status}:{response.reason}:{payload}")
        else:
            return payload

    async def send_api_call(self,
                            path,
                            method="GET",
                            signed=False,
                            send_api_key=True,
                            endpoint=None,
                            timeout=None,
                            **kwargs):
        if self.rate_limit_reached:
            raise QueryCanceled(QueryCanceled.message)
        return await self.ex_imps[self.exchange](path, method, signed, send_api_key, endpoint, timeout, **kwargs)

    async def send_request(self, method, url, timeout, query_kwargs, path=None):
        await self._create_session_if_required()
        try:
            async with self.session.request(method, url, timeout=timeout, **query_kwargs) as response:

                if self.exchange == 'bybit':
                    self.rate_limit_handler.update(path, response.headers)

                return await self.handle_errors(response)
        except (aiohttp.ClientConnectionError, asyncio.exceptions.TimeoutError):
            await self.session.close()
            raise ExchangeError("HTTP ClientConnectionError, the connection will be restored")

    async def _binance_request(self, path, method, signed, send_api_key, endpoint, timeout, **kwargs):
        _endpoint = endpoint or self.endpoint
        url = f'{_endpoint}{path}'
        query_kwargs = dict({"headers": {"Content-Type": AJ}}, **kwargs)
        if send_api_key:
            query_kwargs["headers"]["X-MBX-APIKEY"] = self.api_key
        if signed:
            content = str()
            location = "params" if "params" in kwargs else "data"
            query_kwargs[location]["timestamp"] = str(int(time.time() * 1000))
            if "params" in kwargs:
                content += urlencode(kwargs["params"], safe="@")
            if "data" in kwargs:
                content += urlencode(kwargs["data"])
            query_kwargs[location]["signature"] = generate_signature(self.exchange, self.api_secret, content)
        return await self.send_request(method, url, timeout, query_kwargs)

    async def _bitfinex_request(self, path, method, signed, send_api_key, endpoint, timeout, **kwargs):
        _endpoint = endpoint or self.endpoint
        bfx_post = (method == 'POST' and kwargs) or "params" in kwargs
        _params = json.dumps(kwargs) if bfx_post else None
        url = f'{_endpoint}/{path}'
        query_kwargs = {"headers": {"Accept": AJ}}
        if kwargs and not bfx_post:
            url += f"?{urlencode(kwargs, safe='/')}"
        if bfx_post and "params" in kwargs:
            query_kwargs['data'] = _params

        if signed:
            async with self.rest_cycle_lock:
                ts = int(time.time() * 1000000)
                query_kwargs["headers"]["Content-Type"] = AJ
                if bfx_post:
                    query_kwargs['data'] = _params
                if send_api_key:
                    query_kwargs["headers"]["bfx-apikey"] = self.api_key
                signature_payload = f'/api/{path}{ts}'
                if _params:
                    signature_payload += f"{_params}"
                query_kwargs["headers"]["bfx-signature"] = generate_signature(self.exchange,
                                                                              self.api_secret,
                                                                              signature_payload)
                query_kwargs["headers"]["bfx-nonce"] = str(ts)

                return await self.send_request(method, url, timeout, query_kwargs)

        return await self.send_request(method, url, timeout, query_kwargs)

    async def _bybit_request(self, path, method, signed, _send_api_key, endpoint, timeout, **kwargs):
        await self.rate_limit_handler.wait(path)

        url = endpoint or self.endpoint
        query_kwargs = {}
        data = None
        headers = None
        query_string = urlencode(kwargs)

        if method == 'GET':
            url += f'{path}?{query_string}'

        if signed:
            ts = int(time.time() * 1000)

            if method == 'GET':
                signature_payload = f"{ts}{self.api_key}{query_string}"
            else:
                url += path
                data = json.dumps(kwargs)
                signature_payload = f"{ts}{self.api_key}{data}"

            signature = generate_signature(self.exchange, self.api_secret, signature_payload)
            headers = {
                "Content-Type": AJ,
                "X-Referer": "9KEW1K",
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": str(ts)
            }

        query_kwargs['data'] = data
        query_kwargs['headers'] = headers
        return await self.send_request(method, url, timeout, query_kwargs, path)

    async def _huobi_request(self, path, method, signed, _send_api_key, endpoint, timeout, **kwargs):
        _endpoint = endpoint or self.endpoint
        query_kwargs = {}
        _params = {}
        url = f"{_endpoint}/{path}?"
        if signed:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            _params = {
                "AccessKeyId": self.api_key,
                "SignatureMethod": 'HmacSHA256',
                "SignatureVersion": '2',
                "Timestamp": ts
            }
            if method == 'GET':
                _params.update(**kwargs)
            else:
                query_kwargs['json'] = kwargs
            signature_payload = f"{method}\n{urlparse(_endpoint).hostname}\n/{path}\n{urlencode(_params)}"
            signature = generate_signature(self.exchange, self.api_secret, signature_payload)
            _params['Signature'] = signature
        elif method == 'GET':
            _params = kwargs
        url += urlencode(_params)
        return await self.send_request(method, url, timeout, query_kwargs)

    async def _okx_request(self, path, method, signed, _send_api_key, endpoint, timeout, **kwargs):
        _endpoint = endpoint or self.endpoint
        query_kwargs = {}
        data = None
        headers = None
        if method == 'GET' and kwargs:
            path += f"?{urlencode(kwargs)}"
        url = f'{_endpoint}{path}'
        if signed:
            ts = f"{datetime.now(timezone.utc).replace(tzinfo=None).isoformat('T', 'milliseconds')}Z"
            if method == 'POST' and kwargs:
                data = json.dumps(kwargs.get('data') if 'data' in kwargs else kwargs)
                signature_payload = f"{ts}{method}{path}{data}"
            else:
                signature_payload = f"{ts}{method}{path}"
            signature = generate_signature(self.exchange, self.api_secret, signature_payload)
            headers = {
                "Content-Type": AJ,
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
                "OK-ACCESS-TIMESTAMP": ts
            }
            if self.test_net:
                headers["x-simulated-trading"] = '1'

        query_kwargs['data'] = data
        query_kwargs['headers'] = headers
        return await self.send_request(method, url, timeout, query_kwargs)
