#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance WS API connector for User Data Stream requests
https://developers.binance.com/docs/binance-trading-api/websocket_api#general-api-information
Fully implemented methods of connection management, keepalive, rate limits control
"""
__authors__ = ["Jerry Fedorenko"]
__license__ = "MIT"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
__email__ = "jerry.fedorenko@yahoo.com"
__credits__ = []
__version__ = "1.0.0b2"

import logging

TIMEOUT = 10  # sec timeout for WSS receive
logger = logging.getLogger('exch_srv_logger')
