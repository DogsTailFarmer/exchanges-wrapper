#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ssl
from pathlib import Path

import grpclib.exceptions
import traceback
import asyncio
import logging.handlers

import exchanges_wrapper.tlg as tlg
from exchanges_wrapper import WORK_PATH, LOG_FILE_TLG, Server, graceful_exit
#
HEARTBEAT = 1  # Sec
CERT_DIR = Path(WORK_PATH, "keys")
CLIENT_CERT = Path(CERT_DIR, "tlg-client.pem")
SERVER_CERT = Path(CERT_DIR, "tlg-proxy.pem")
SERVER_KEY = Path(CERT_DIR, "tlg-proxy.key")
#
logger = logging.getLogger(__name__)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
fh = logging.handlers.RotatingFileHandler(LOG_FILE_TLG, maxBytes=1000000, backupCount=10)
fh.setFormatter(formatter)
fh.setLevel(logging.INFO)
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
sh.setLevel(logging.INFO)
#
root_logger = logging.getLogger()
root_logger.setLevel(min([fh.level, sh.level]))
root_logger.addHandler(fh)
root_logger.addHandler(sh)


def create_secure_context(server_cert: Path, server_key: Path, *, trusted: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH,
        cafile=str(trusted),
    )
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_cert_chain(str(server_cert), str(server_key))
    ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
    ctx.set_alpn_protocols(['h2'])
    return ctx


class TlgProxy(tlg.TlgProxyBase):

    async def post_message(self, request: tlg.Request) -> tlg.Response:
        logger.info(f"bot_id: {request.bot_id}")
        return tlg.Response(bot_id=request.bot_id)


def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


async def main(host: str = '127.0.0.1', port: int = 50061):
    if is_port_in_use(port):
        raise SystemExit(f"gRPC Telegram proxy: local port {port} already used")

    server = Server([TlgProxy()])
    with graceful_exit([server]):
        await server.start(
            host,
            port,
            ssl=create_secure_context(SERVER_CERT, SERVER_KEY, trusted=CLIENT_CERT)
        )
        logger.info(f"Starting Telegram proxy service on {host}:{port}")
        await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
