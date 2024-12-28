#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client example for exchanges-wrapper, examples of use of server methods are given
"""
import ast
import asyncio
import toml
import uuid
import simplejson as json

from exchanges_wrapper import martin as mr, Channel, Status, GRPCError

RATE_LIMITER = 5
FILE_CONFIG = 'ms_cfg.toml'
config = toml.load(FILE_CONFIG)
EXCHANGE = config.get('exchange')
SYMBOL = 'BNBUSDT'


async def main(_exchange, _symbol):
    print(f"main.account_name: {_exchange}")
    # Create connection to the grpc powered server
    channel = Channel('127.0.0.1', 50051)
    stub = mr.MartinStub(channel)
    trade_id = str(uuid.uuid4().hex)
    client_id = None
    # Register client and get client_id for reuse connection
    # Example of exception handling by grpc connection
    try:
        client_id_msg = await stub.open_client_connection(mr.OpenClientConnectionRequest(
            trade_id=trade_id,
            account_name=_exchange,
            symbol=SYMBOL,
            rate_limiter=RATE_LIMITER))
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except GRPCError as ex:
        channel.close()
        status_code = ex.status
        print(f"Exception on register client: {status_code.name}, {ex.message}")
        return
    else:
        client_id = client_id_msg.client_id
        exchange = client_id_msg.exchange
        print(f"main.exchange: {exchange}")
        print(f"main.client_id: {client_id}")
        print(f"main.srv_version: {client_id_msg.srv_version}")

    # Sample async call server method
    _exchange_info_symbol = await stub.fetch_exchange_info_symbol(mr.MarketRequest(
        trade_id=trade_id,
        client_id=client_id,
        symbol=_symbol))
    # Unpack result
    exchange_info_symbol = _exchange_info_symbol.to_pydict()
    print("\n".join(f"{k}\t{v}" for k, v in exchange_info_symbol.items()))

    # Sample async functon call
    open_orders = await fetch_open_orders(stub, client_id, _symbol)
    print(f"open_orders: {open_orders}")

    # Subscribe to WSS
    # First you want to create all WSS task
    # Market stream
    # noinspection PyAsyncCall
    asyncio.create_task(on_ticker_update(stub, client_id, _symbol, trade_id))
    # User Stream
    # noinspection PyAsyncCall
    asyncio.create_task(on_order_update(stub, client_id, _symbol, trade_id))
    # Other market and user methods are used similarly: OnKlinesUpdate, OnFundsUpdate, OnOrderBookUpdate
    # Start WSS
    # The values of market_stream_count directly depend on the number of market
    # ws streams used in the strategy and declared above
    await stub.start_stream(mr.StartStreamRequest(
        trade_id=trade_id,
        client_id=client_id,
        symbol=_symbol,
        market_stream_count=1))
    await asyncio.sleep(RATE_LIMITER)
    # Before stop program call StopStream() method
    await stub.stop_stream(mr.MarketRequest(trade_id=trade_id, client_id=client_id, symbol=_symbol))
    channel.close()


async def on_ticker_update(_stub, _client_id, _symbol, trade_id):
    """
    24hr rolling window mini-ticker statistics. Truncated sample.
    :param trade_id:
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: {}
    """
    async for ticker in _stub.on_ticker_update(mr.MarketRequest(
            trade_id=trade_id,
            client_id=_client_id,
            symbol=_symbol)):
        print(f"on_ticker_update: {ticker.to_pydict()}")


async def on_order_update(_stub, _client_id, _symbol, trade_id):
    """
    Orders are updated with the executionReport event.
    :param trade_id:
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md#order-update
    """
    async for event in _stub.on_order_update(mr.MarketRequest(
            trade_id=trade_id,
            client_id=_client_id,
            symbol=_symbol)):
        print(json.loads(event.result))


async def on_balance_update(_stub, _client_id, _symbol, trade_id):
    """
    Get data when asset transferred or withdrawal from account
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param trade_id:
    :return:
    """
    async for res in _stub.on_balance_update(mr.MarketRequest(
            trade_id=trade_id,
            client_id=_client_id,
            symbol=_symbol)):
        print(json.loads(res.event))


async def fetch_open_orders(_stub, _client_id, _symbol):
    """
    Get all open orders on a symbol.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#current-open-orders-user_data
    """
    _active_orders = await _stub.fetch_open_orders(mr.MarketRequest(client_id=_client_id, symbol=_symbol))
    active_orders = list(map(json.loads, _active_orders.orders))
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
        res = await _stub.fetch_order(mr.FetchOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            order_id=_id,
            filled_update_call=_filled_update_call))
        result = res.to_pydict()
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
    res = await _stub.cancel_all_orders(mr.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    result = ast.literal_eval(json.loads(res.result))
    print(f"cancel_all_orders.result: {result}")


async def fetch_account_information(_stub, _client_id):
    """
    Account information (USER_DATA)
    :param _stub:
    :param _client_id:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#account-information-user_data
    """
    try:
        res = await _stub.fetch_account_information(mr.OpenClientConnectionId(client_id=_client_id))
    except asyncio.CancelledError:
        pass
    except Exception as _ex:
        print(f"Exception fetch_account_information: {_ex}")
    else:
        balances = list(map(json.loads, res.items))
        print(f"fetch_account_information.balances: {balances}")


async def fetch_funding_wallet(_stub, _client_id):
    """
    Get balances from Funding wallet for Binance and assets from 'main' account for FTX
    :param _stub:
    :param _client_id:
    :return: https://binance-docs.github.io/apidocs/spot/en/#funding-wallet-user_data
    """
    try:
        res = await _stub.fetch_funding_wallet(mr.FetchFundingWalletRequest(
            client_id=_client_id))
    except asyncio.CancelledError:
        pass
    except Exception as _ex:
        print(f"fetch_funding_wallet: {_ex}")
    else:
        funding_wallet = list(map(json.loads, res.items))
        print(f"fetch_funding_wallet.funding_wallet: {funding_wallet}")


async def fetch_order_book(_stub, _client_id, _symbol):
    """
    Get order book, limit=5
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#order-book
    """
    _order_book = await _stub.fetch_order_book(mr.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    order_book = _order_book.to_pydict()
    print(f"fetch_order_book.order_book: {order_book}")


async def fetch_symbol_price_ticker(_stub, _client_id, _symbol):
    """
    Get symbol price ticker
    :param _stub:
    :param _client_id:
    :param _symbol:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#symbol-price-ticker
    """
    _price = await _stub.fetch_symbol_price_ticker(mr.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    price = _price.to_pydict()
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
    _ticker = await _stub.fetch_ticker_price_change_statistics(mr.MarketRequest(
        client_id=_client_id,
        symbol=_symbol))
    ticker = _ticker.to_pydict()
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
    res = await _stub.fetch_klines(mr.FetchKlinesRequest(
        client_id=_client_id,
        symbol=_symbol,
        interval=_interval,
        limit=_limit))
    kline = list(map(json.loads, res.items))
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
    _trades = await _stub.fetch_account_trade_list(mr.AccountTradeListRequest(
        client_id=_client_id,
        symbol=_symbol,
        limit=_limit,
        start_time=_start_time_ms)
    )
    trades = list(map(json.loads, _trades.items))
    print(f"fetch_account_trade_list.trades: {trades}")


async def transfer2master(_stub, symbol: str, amount: str):
    """
    Send request to transfer asset from subaccount to main account
    Binance, OKX: not additional settings needed
    Bitfinex: for subaccount setting 2FA method, set WITHDRAWAL permission for API key,
     in config for subaccount set 2FA key and master account EMail
    Huobi: in config for subaccount set master_name for Main account
    :param _stub:
    :param symbol:
    :param amount:
    :return:
    """
    try:
        res = await _stub.transfer_to_master(mr.MarketRequest, symbol=symbol, amount=amount)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except GRPCError as ex:
        status_code = ex.status
        print(f"Exception transfer {symbol} to main account: {status_code.name}, {ex.message}")
    except Exception as _ex:
        print(f"Exception transfer {symbol} to main account: {_ex}")
    else:
        if res.success:
            print(f"Sent {amount} {symbol} to main account")
        else:
            print(f"Not sent {amount} {symbol} to main account\n,{res.result}")


async def transfer2sub(_stub, email: str, symbol: str, amount: str):
    """
    Send request to transfer asset from subaccount to subaccount
    Binance sub to sub only
    :param _stub:
    :param email:
    :param symbol:
    :param amount:
    :return:
    """
    try:
        res = await _stub.transfer_to_sub(
            mr.MarketRequest,
            symbol=symbol,
            amount=amount,
            data=email
        )
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except GRPCError as ex:
        status_code = ex.status
        print(f"Exception transfer {symbol} to sub account: {status_code.name}, {ex.message}")
    except Exception as _ex:
        print(f"Exception transfer {symbol} to sub account: {_ex}")
    else:
        if res.success:
            print(f"Sent {amount} {symbol} to sub account {email}")
        else:
            print(f"Not sent {amount} {symbol} to sub account {email}\n,{res.result}")


# Server exception handling example for methods where it's realized
async def create_limit_order(_stub, _client_id, _symbol, _id: int, buy: bool, amount: str, price: str):
    """
    Send in a new Limit order.
    :param _stub:
    :param _client_id:
    :param _symbol:
    :param _id: A unique id among open orders. Automatically generated if not sent
    :param buy: True id BUY_side else False
    :param amount: Base asset quantity
    :param price:
    :return: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#new-order--trade
    """
    try:
        res = await _stub.create_limit_order(mr.CreateLimitOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            buy_side=buy,
            quantity=amount,
            price=price,
            new_client_order_id=_id
        ))
        result = res.to_pydict()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except GRPCError as ex:
        status_code = ex.status
        print(f"Exception creating order {_id}: {status_code.name}, {ex.message}")
        if status_code == Status.FAILED_PRECONDITION:
            print("Do something. See except declare in exch_srv.CreateLimitOrder()")
    except Exception as _ex:
        print(f"Exception creating order {_id}: {_ex}")
    else:
        print(f"create_limit_order.result: {result}")


# Server exception handling example for methods where it's realized
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
        res = await _stub.cancel_order(mr.CancelOrderRequest(
            client_id=_client_id,
            symbol=_symbol,
            order_id=_id))
        result = res.to_pydict()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except GRPCError as ex:
        status_code = ex.status
        print(f"Exception on cancel order for {_id}: {status_code.name}, {ex.message}")
    except Exception as _ex:
        print(f"Exception on cancel order call for {_id}:\n{_ex}")
    else:
        print(f"Cancel order {_id} success: {result}")


if __name__ == "__main__":
    asyncio.run(main(EXCHANGE, SYMBOL))
