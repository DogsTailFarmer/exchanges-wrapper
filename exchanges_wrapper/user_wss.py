import aiohttp
import asyncio
import random
import logging
import time
import traceback
import shortuuid


from exchanges_wrapper.errors import (
    RateLimitReached,
    ExchangeError,
    WAFLimitViolated,
    IPAddressBanned,
    HTTPError,
)

from exchanges_wrapper.definitions import RateLimitInterval
from exchanges_wrapper.c_structures import generate_signature


TIMEOUT = 10  # s WSS receive timeout


logger = logging.getLogger('exch_srv_logger')


class UserWSSession:
    def __init__(
            self, api_key: str,
            api_secret: str,
            session: aiohttp.ClientSession,
            endpoint="wss://testnet.binance.vision/ws-api/v3"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = session
        self.endpoint = endpoint
        self.trade_id = None
        self.web_socket = None
        self.listen_key = None
        self.try_count = 0
        self.operational_status = False
        self.order_handling = False
        self.retry_after = int(time.time() * 1000) - 1
        self.session_tasks = []
        self.queue = {}

    async def start(self, trade_id=shortuuid.uuid()):
        self.trade_id = trade_id or self.trade_id
        params = {"apiKey": 1}
        try:
            self.web_socket = await self.session.ws_connect(url=f"{self.endpoint}", heartbeat=500)
        except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectionError, asyncio.TimeoutError) as ex:
            await self._ws_error(ex)
        except Exception as ex:
            logger.error(f"UserWSSession start() other exception: {ex}")
            logger.debug(traceback.format_exc())
        else:
            self.session_tasks.append(asyncio.ensure_future(self._receive_msg()))
            self.operational_status = True
            self.order_handling = True
            try:
                res = await self.handle_request('userDataStream.start', params)
            except asyncio.TimeoutError:
                ex = "UserWSSession initiate timeout error"
                await self._ws_error(ex)
            else:
                self.try_count = 0
                self.listen_key = res.get('listenKey')
                self.session_tasks.append(asyncio.ensure_future(self._heartbeat()))
                self.session_tasks.append(asyncio.ensure_future(self._keepalive()))
                logger.info(f"UserWSSession started for {self.trade_id}")

                self.session_tasks.append(asyncio.ensure_future(self.test()))

    async def _ws_error(self, ex):
        if self.operational_status is not None:
            self.try_count += 1
            delay = random.randint(1, 5) * self.try_count
            logger.error(f"UserWSSession restart: delay: {delay}s, {ex}")
            await asyncio.sleep(delay)
            asyncio.ensure_future(self.start())

    async def handle_request(self, method: str, params: {} = None):
        if self.operational_status:
            _id = f"{self.trade_id}-{method.replace('.', '_')}"[-36:]
            queue = self.queue.setdefault(_id, asyncio.Queue())
            req = {'id': _id, "method": method}
            if params:
                if params.get('apiKey'):
                    params['apiKey'] = self.api_key
                if params.get('timestamp'):
                    params['timestamp'] = int(time.time() * 1000)
                if params.pop('signature', None):
                    payload = '&'.join(f"{key}={value}" for key, value in dict(sorted(params.items())).items())
                    params['signature'] = generate_signature('binance_ws', self.api_secret, payload)
                req['params'] = params
            await self._send_request(req)
            return self._handle_msg_error(await asyncio.wait_for(queue.get(), timeout=TIMEOUT))
        else:
            logger.warning(f"UserWSSession operational status is {self.operational_status}")
            return {}

    async def test(self, interval=1):
        params = {
            "apiKey": 1,
            "signature": 1,
            "timestamp": 1
        }
        while self.operational_status is not None:
            await asyncio.sleep(interval)
            try:
                res = await self.handle_request("account.rateLimits.orders", params)
            except Exception as ex:
                print(f"TEST: {ex}")
            else:
                print(f"TEST: {res}")
            break

    async def _keepalive(self, interval=10):
        while self.operational_status is not None:
            await asyncio.sleep(interval)
            if ((not self.operational_status or not self.order_handling)
                    and int(time.time() * 1000) - self.retry_after >= 0):
                try:
                    await self.handle_request("ping")
                except Exception as ex:
                    logger.warning(f"UserWSSession._keepalive: {ex}")
                else:
                    if not self.operational_status:
                        self.operational_status = True
                        logger.info("UserWSSession operational status restored")
                    else:
                        self.order_handling = True
                        logger.info("UserWSSession order limit restriction was cleared")

    async def _heartbeat(self, interval=60 * 30):
        params = {
            "listenKey": self.listen_key,
            "apiKey": 1
        }
        while self.operational_status is not None:
            await asyncio.sleep(interval)
            await self.handle_request("userDataStream.ping", params)

    async def stop(self):
        """
        Stop data stream
        """
        logger.info(f'STOP User WSS for {self.trade_id}')
        self.operational_status = None  # Not restart and break all loops
        self.order_handling = False
        req = {
            "id": f"{self.trade_id}-stop",
            "method": "userDataStream.stop",
            "params": {
                "listenKey": self.listen_key,
                "apiKey": self.api_key
            }
        }
        await self._send_request(req)
        [_task.cancel() for _task in self.session_tasks]
        if self.web_socket:
            await self.web_socket.close()

    async def _send_request(self, req: {}):
            try:
                await self.web_socket.send_json(req)
            except Exception as ex:
                logger.error(f"UserWSSession._send_request: {ex}")

    async def _receive_msg(self):
        while self.operational_status is not None:
            msg = await self.web_socket.receive_json()
            self._handle_rate_limits(msg.pop('rateLimits', []))
            queue = self.queue.get(msg.get('id'))
            if queue:
                await queue.put(msg)
            else:
                logger.warning(f"Can't get queue for transporting message: {msg}")

    def _handle_msg_error(self, msg):
        if msg.get('status') != 200:
            error_msg = msg.get('error')
            logger.error(f"UserWSSession get error: {error_msg}")
            if msg.get('status') >= 500:
                raise ExchangeError(f"An issue occurred on exchange's side: {error_msg}")
            if msg.get('status') == 403:
                self.operational_status = False
                raise WAFLimitViolated(WAFLimitViolated.message)
            self.retry_after = error_msg.get('data', {}).get('retryAfter', int((time.time() + 10) * 1000))
            if msg.get('status') == 418:
                self.operational_status = False
                raise IPAddressBanned(IPAddressBanned.message)
            if msg.get('status') == 429:
                self.operational_status = False
                raise RateLimitReached(RateLimitReached.message)
            raise HTTPError(f"Malformed request: status: {error_msg}")
        return msg.get('result')

    def _handle_rate_limits(self, rate_limits: []):
        def retry_after():
            return (int(time.time() / interval) + 1) * interval * 1000

        for rl in rate_limits:
            if rl.get('limit') - rl.get('count') <= 0:
                interval = rl.get('intervalNum') * RateLimitInterval[rl.get('interval')].value
                self.retry_after = max(self.retry_after, retry_after())
                if rl.get('rateLimitType') == 'REQUEST_WEIGHT':
                    self.operational_status = False
                elif rl.get('rateLimitType') == 'ORDERS':
                    self.order_handling = False
