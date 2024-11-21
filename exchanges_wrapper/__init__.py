#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REST API and WebSocket asyncio wrapper with grpc powered multiplexer server
 for crypto exchanges (Binance, Bitfinex, OKX, Huobi)
 Utilizes one connection for many accounts and trading pairs.
 For SPOT market only
"""
__authors__ = ["Th0rgal", "Jerry Fedorenko"]
__license__ = "MIT"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
__email__ = "jerry.fedorenko@yahoo.com"
__credits__ = ["https://github.com/DanyaSWorlD"]
__version__ = "2.1.21rc1"

from pathlib import Path
import shutil

from grpclib.server import Server, GRPCError, Status
from grpclib.client import Channel
from grpclib.utils import graceful_exit

__all__ = [
    Server, GRPCError, Status, Channel, graceful_exit
]

WORK_PATH = Path(Path.home(), ".MartinBinance")
CONFIG_PATH = Path(WORK_PATH, "config")
CONFIG_FILE = Path(CONFIG_PATH, "exch_srv_cfg.toml")
LAST_STATE_PATH = Path(WORK_PATH, "last_state")
LOG_PATH = Path(WORK_PATH, "exch_srv_log")
LOG_FILE = Path(LOG_PATH, "exch_srv.log")


def init():
    if CONFIG_FILE.exists():
        print(f"Server config found at {CONFIG_FILE}")
    else:
        print("Can't find config file! Creating it...")
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        LOG_PATH.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(Path(__file__).parent.absolute(), "exch_srv_cfg.toml.template"), CONFIG_FILE)
        print(f"Before first run place account(s) API key into {CONFIG_FILE}")
        raise SystemExit(1)


if __name__ == '__main__':
    init()
