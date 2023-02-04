#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client example for exchanges-wrapper, examples of use of server methods are given
"""

import asyncio
import toml
import uuid
# noinspection PyPackageRequirements
import grpc
# noinspection PyPackageRequirements
from google.protobuf import json_format
from exchanges_wrapper import api_pb2, api_pb2_grpc

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [('grpc.lb_policy_name', 'pick_first'),
                   ('grpc.enable_retries', 0),
                   ('grpc.keepalive_timeout_ms', 10000)]
RATE_LIMITER = 5
FILE_CONFIG = 'ms_cfg.toml'
config = toml.load(FILE_CONFIG)
EXCHANGE = config.get('exchange')
SYMBOL = 'BTCUSDT'


async def main(_exchange, _symbol):
    print(f"main.account_name: {_exchange}")
    # Create connection to the grpc powered server
    channel = grpc.aio.insecure_channel(target='localhost:50051', options=CHANNEL_OPTIONS)
    stub = api_pb2_grpc.MartinStub(channel)
    trade_id = str(uuid.uuid4().hex)
    client_id = None
    # Register client and get client_id for reuse connection
    # Example of exception handling by grpc connection
    try:
        client_id_msg = await stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
            trade_id=trade_id,
            account_name=_exchange,
            rate_limiter=RATE_LIMITER))
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except grpc.RpcError as ex:
        # noinspection PyUnresolvedReferences
        status_code = ex.code()
        # noinspection PyUnresolvedReferences
        print(f"Exception on register client: {status_code.name}, {ex.details()}")
        return
    else:
        client_id = client_id_msg.client_id
        exchange = client_id_msg.exchange
        print(f"main.exchange: {exchange}")
        print(f"main.client_id: {client_id}")
        print(f"main.srv_version: {client_id_msg.srv_version}")

    # Sample async call server method
    _exchange_info_symbol = await stub.FetchExchangeInfoSymbol(api_pb2.MarketRequest(
        trade_id=trade_id,
        client_id=client_id,
        symbol=_symbol))
    # Unpack result
    exchange_info_symbol = json_format.MessageToDict(_exchange_info_symbol)
    print("\n".join(f"{k}\t{v}" for k, v in exchange_info_symbol.items()))

    # Sample async functon call
    open_orders = await fetch_open_orders(stub, client_id, _symbol)
    print(f"open_orders: {open_orders}")

    # Subscribe to WSS
    # First you want to create all WSS task
    # Market stream
    asyncio.create_task(on_ticker_update(stub, client_id, _symbol, trade_id))
    # User Stream
    asyncio.create_task(on_order_update(stub, client_id, _symbol, trade_id))
    # Other market and user methods are used similarly: OnKlinesUpdate, OnFundsUpdate, OnOrderBookUpdate
    # Start WSS
    # The values of market_stream_count directly depend on the number of market
    # ws streams used in the strategy and declared above
    await stub.StartStream(api_pb2.StartStreamRequest(
        trade_id=trade_id,
        client_id=client_id,
        symbol=_symbol,
        market_stream_count=1))
    await asyncio.sleep(RATE_LIMITER)
    # Before stop program call StopStream() method
    await stub.StopStream(api_pb2.MarketRequest(trade_id=trade_id, client_id=client_id, symbol=_symbol))


async def on_ticker_update(_stub, _client_id, _symbol, trade_id):
    """
    24hr rolling window mini-ticker statistics. Truncated sample.
    :param trade_id:
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: {}
    """
    async for ticker in _stub.OnTickerUpdate(api_pb2.MarketRequest(
            trade_id=trade_id,
            client_id=_client_id,
            symbol=_symbol)):
        ticker_24h = {'openPrice': ticker.open_price,
                      'lastPrice': ticker.close_price,
                      'closeTime': ticker.event_time}
        print(f"on_ticker_update: {ticker.symbol} {ticker_24h}")


async def on_order_update(_stub, _client_id, _symbol, trade_id):
    """
    Orders are updated with the executionReport event.
    :param trade_id:
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md#order-update
    """
    async for event in _stub.OnOrderUpdate(api_pb2.MarketRequest(
            trade_id=trade_id,
            client_id=_client_id,
            symbol=_symbol)):
        print(f"on_order_update: {event.symbol}\n"
              f"order_id: {event.order_id}\n"
              f"order_status: {event.order_status}\n"
              f"cumulative_filled_quantity: {event.cumulative_filled_quantity}\n"
              f"quote_order_quantity: {event.quote_order_quantity}\n"
              f"quote_asset_transacted: {event.quote_asset_transacted}\n"
              f"client_order_id: {event.client_order_id}")


async def fetch_open_orders(_stub, _client_id, _symbol):
    """
    Get all open orders on a symbol.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#current-open-orders-user_data
    """
    _active_orders = await _stub.FetchOpenOrders(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol))
    active_orders = json_format.MessageToDict(_active_orders).get('items', [])
    print(f"active_orders: {active_orders}")
    return active_orders


async def fetch_order(_stub, _client_id, _symbol, _id: int, _filled_update_call: bool = False):
    """
    Check an order's status.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _id: order id
    :param _filled_update_call: if True and order's status is 'FILLED' generated event for OnOrderUpdate user stream
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#query-order-user_data
    """
    try:
        res = await _stub.FetchOrder(api_pb2.FetchOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            order_id=_id,
            filled_update_call=_filled_update_call))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except Exception as _ex:
        print(f"Exception in fetch_order: {_ex}")
        return {}
    else:
        print(f"For order {result.get('orderId')} fetched status is {result.get('status')}")
        return result


async def cancel_all_orders(_stub, _client_id, _symbol):
    """
    Cancel All Open Orders on a Symbol
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return:
     https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-all-open-orders-on-a-symbol-trade
    """
    res = await _stub.CancelAllOrders(api_pb2.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    result = json_format.MessageToDict(res)
    print(f"cancel_all_orders.result: {result}")


async def fetch_account_information(_stub, _client_id):
    """
    Account information (USER_DATA)
    :param _stub:
    :param _client_id:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-information-user_data
    """
    try:
        res = await _stub.FetchAccountInformation(api_pb2.OpenClientConnectionId(client_id=_client_id))
    except asyncio.CancelledError:
        pass
    except Exception as _ex:
        print(f"Exception fetch_account_information: {_ex}")
    else:
        balances = json_format.MessageToDict(res).get('balances', [])
        print(f"fetch_account_information.balances: {balances}")


async def fetch_funding_wallet(_stub, _client_id):
    """
    Get balances from Funding wallet for Binance and assets from 'main' account for FTX
    :param _stub:
    :param _client_id:
    :return: https://binance-docs.github.io/apidocs/spot/en/#funding-wallet-user_data
    """
    try:
        res = await _stub.FetchFundingWallet(api_pb2.FetchFundingWalletRequest(
            client_id=_client_id))
    except asyncio.CancelledError:
        pass
    except Exception as _ex:
        print(f"fetch_funding_wallet: {_ex}")
    else:
        funding_wallet = json_format.MessageToDict(res).get('balances', [])
        print(f"fetch_funding_wallet.funding_wallet: {funding_wallet}")


async def fetch_order_book(_stub, _client_id, _symbol):
    """
    Get order book, limit=5
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#order-book
    """
    _order_book = await _stub.FetchOrderBook(api_pb2.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    order_book = json_format.MessageToDict(_order_book)
    print(f"fetch_order_book.order_book: {order_book}")


async def fetch_symbol_price_ticker(_stub, _client_id, _symbol):
    """
    Get symbol price ticker
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#symbol-price-ticker
    """
    _price = await _stub.FetchSymbolPriceTicker(api_pb2.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    price = json_format.MessageToDict(_price)
    print(f"fetch_symbol_price_ticker.price: {price}")


async def fetch_ticker_price_change_statistics(_stub, _client_id, _symbol):
    """
    24hr ticker price change statistics
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return:
     https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#24hr-ticker-price-change-statistics
    """
    _ticker = await _stub.FetchTickerPriceChangeStatistics(api_pb2.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    ticker = json_format.MessageToDict(_ticker)
    print(f"fetch_ticker_price_change_statistics.ticker: {ticker}")


async def fetch_klines(_stub, _client_id, _symbol, _interval, _limit):
    """
    Kline/candlestick bars for a symbol. Klines are uniquely identified by their open time.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _interval: ENUM https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#enum-definitions
    :param _limit: Default 500; max 1000.
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
    """
    res = await _stub.FetchKlines(api_pb2.FetchKlinesRequest(
        client_id=_client_id,
        symbol=_symbol,
        interval=_interval,
        limit=_limit))
    kline = json_format.MessageToDict(res)
    print(f"fetch_klines.kline: {kline}")


async def fetch_account_trade_list(_stub, _client_id, _symbol, _limit, _start_time_ms):
    """
    Get trades for a specific account and symbol.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _limit: int: Default 500; max 1000
    :param _start_time_ms: int: optional, minimum time of fills to return, in Unix time (ms since 1970-01-01)
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-trade-list-user_data
    """
    _trades = await _stub.FetchAccountTradeList(api_pb2.AccountTradeListRequest(
        client_id=_client_id,
        symbol=_symbol,
        limit=_limit,
        start_time=_start_time_ms)
    )
    trades = json_format.MessageToDict(_trades).get('items', [])
    print(f"fetch_account_trade_list.trades: {trades}")


# Server exception handling example for methods where it's realized
# noinspection PyUnresolvedReferences
async def create_limit_order(_stub, _client_id, _symbol, _id: int, buy: bool, amount: str, price: str):
    """
    Send in a new Limit order.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _id: A unique id among open orders. Automatically generated if not sent.
    :param buy: True id BUY_side else False
    :param amount: Base asset quantity
    :param price:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#new-order--trade
    """
    try:
        res = await _stub.CreateLimitOrder(api_pb2.CreateLimitOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            buy_side=buy,
            quantity=amount,
            price=price,
            new_client_order_id=_id
        ))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except grpc.RpcError as ex:
        status_code = ex.code()
        print(f"Exception creating order {_id}: {status_code.name}, {ex.details()}")
        if status_code == grpc.StatusCode.FAILED_PRECONDITION:
            print("Do something. See except declare in exch_srv.CreateLimitOrder()")
    except Exception as _ex:
        print(f"Exception creating order {_id}: {_ex}")
    else:
        print(f"create_limit_order.result: {result}")


# Server exception handling example for methods where it's realized
# noinspection PyUnresolvedReferences
async def cancel_order(_stub, _client_id, _symbol, _id: int):
    """
    Cancel an active order.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _id: exchange order id
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#cancel-order-trade
    """
    try:
        res = await _stub.CancelOrder(api_pb2.CancelOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            order_id=_id))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except grpc.RpcError as ex:
        status_code = ex.code()
        print(f"Exception on cancel order for {_id}: {status_code.name}, {ex.details()}")
    except Exception as _ex:
        print(f"Exception on cancel order call for {_id}:\n{_ex}")
    else:
        print(f"Cancel order {_id} success: {result}")


if __name__ == "__main__":
    asyncio.run(main(EXCHANGE, SYMBOL))
