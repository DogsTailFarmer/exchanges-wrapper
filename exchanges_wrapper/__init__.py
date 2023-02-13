#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REST API and WebSocket asyncio wrapper with grpc powered multiplexer server
 for crypto exchanges (Binance, Bitfinex, OKX, Huobi,)
 Utilizes one connection for many accounts and trading pairs.
 For SPOT market only
"""
__authors__ = ["Th0rgal", "Jerry Fedorenko"]
__license__ = "MIT"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
__email__ = "jerry.fedorenko@yahoo.com"
__credits__ = ["https://github.com/DanyaSWorlD"]
__version__ = "1.2.10b0"

from pathlib import Path
import shutil
#
import platform
print(f"Python {platform.python_version()}")
#
WORK_PATH = Path(Path.home(), ".MartinBinance")
CONFIG_PATH = Path(WORK_PATH, "config")
CONFIG_FILE = Path(CONFIG_PATH, "exch_srv_cfg.toml")
LOG_PATH = Path(WORK_PATH, "exch_srv_log")
LOG_FILE = Path(LOG_PATH, "exch_srv.log")

if CONFIG_FILE.exists():
    print(f"Config found at {CONFIG_FILE}")
else:
    print("Can't find config file! Creating it...")
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    LOG_PATH.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(Path(__file__).parent.absolute(), "exch_srv_cfg.toml.template"), CONFIG_FILE)
    print(f"Before first run place account(s) API key into {CONFIG_FILE}")
    raise SystemExit(1)
