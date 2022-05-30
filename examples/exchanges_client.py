#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
Client example for exchanges-wrapper exch_srv.py
"""

import asyncio
import toml
# noinspection PyPackageRequirements
import grpc
# noinspection PyPackageRequirements
from google.protobuf import json_format
import api_pb2
import api_pb2_grpc

# Set id exchange from ms_cfg.toml
ID_EXCHANGE = 0

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [('grpc.lb_policy_name', 'pick_first'),
                   ('grpc.enable_retries', 0),
                   ('grpc.keepalive_timeout_ms', 10000)]
HEARTBEAT = 2  # Sec
RATE_LIMITER = HEARTBEAT * 5
FILE_CONFIG = 'ms_cfg.toml'
config = toml.load(FILE_CONFIG)
EXCHANGE = config.get('exchange')
SYMBOL = 'BTCUSDT'


async def main(_symbol):
    account_name = EXCHANGE[ID_EXCHANGE]
    print(f"main.account_name: {account_name}")  # lgtm [py/clear-text-logging-sensitive-data]
    channel = grpc.aio.insecure_channel(target='localhost:50051', options=CHANNEL_OPTIONS)
    stub = api_pb2_grpc.MartinStub(channel)
    client_id_msg = await stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
        account_name=account_name,
        rate_limiter=RATE_LIMITER))
    print(f"main.client_id: {client_id_msg.client_id}")
    print(f"main.srv_version: {client_id_msg.srv_version}")
    #
    _exchange_info_symbol = await stub.FetchExchangeInfoSymbol(api_pb2.MarketRequest(
        client_id=client_id_msg.client_id,
        symbol=_symbol))
    exchange_info_symbol = json_format.MessageToDict(_exchange_info_symbol)
    print("\n".join(f"{k}\t{v}" for k, v in exchange_info_symbol.items()))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(SYMBOL))
    loop.stop()
    loop.close()
