#!/usr/bin/python3.8
# -*- coding: utf-8 -*-

import hmac
import hashlib


def generate_signature(exchange, api_secret, data):
    if exchange == 'bitfinex':
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha384).hexdigest()
    else:
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig
