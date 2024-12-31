#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ssl
from pathlib import Path
import asyncio
import uuid

from exchanges_wrapper import WORK_PATH, tlg as tlg, Channel, GRPCError

CERT_DIR = Path(WORK_PATH, "keys")
SERVER_CERT = Path(CERT_DIR, "tlg-proxy.pem")
CLIENT_CERT = Path(CERT_DIR, "tlg-client.pem")
CLIENT_KEY = Path(CERT_DIR, "tlg-client.key")


def create_secure_context(client_cert: Path, client_key: Path, *, trusted: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(trusted))
    ctx.load_cert_chain(str(client_cert), str(client_key))
    ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
    ctx.set_alpn_protocols(['h2'])
    return ctx


async def main():
    ssl_context = create_secure_context(CLIENT_CERT, CLIENT_KEY, trusted=SERVER_CERT)
    channel = Channel('localhost', 50061, ssl=ssl_context)
    stub = tlg.TlgProxyStub(channel)

    try:
        res = await stub.post_message(
            tlg.Request(
                bot_id=uuid.uuid4().hex
            )
        )
    except asyncio.CancelledError:
        channel.close()
    except GRPCError as ex:
        channel.close()
        status_code = ex.status
        print(f"Exception on register client: {status_code.name}, {ex.message}")
        return
    else:
        print(f"res: {res}")
        channel.close()


if __name__ == "__main__":
    asyncio.run(main())
