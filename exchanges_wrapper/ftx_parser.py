#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
Parser for convert FTX REST API/WSS response to Binance like result
"""
import time
import datetime
from decimal import Decimal
import logging

logger = logging.getLogger('exch_srv_logger')

CH_KEY = {
    'miniTicker': ['last'],
    'depth5': ['bid', 'ask'],
}
TIMESTAMP_PATTERN = "%Y-%m-%dT%H:%M:%S.%f"


def ftx_on_funds_update(res: []) -> {}:
    binance_funds = {
        'e': 'outboundAccountPosition',
        'E': int(time.time() * 1000),
        'u': int(time.time() * 1000),
    }
    funds = []
    for i in res:
        balance = {
            'a': i.get('asset'),
            'f': i.get('free'),
            'l': i.get('locked')
        }
        funds.append(balance)
    binance_funds['B'] = funds
    return binance_funds


def ftx_interval(interval: str) -> int:
    resolution = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '4h': 14400,
        '1d': 86400,
    }
    return resolution.get(interval, 0)


def ftx_exchange_info(res: []) -> {}:
    symbols = []
    for market in res:
        market_type = market.get("type")
        volume_usd24h = market.get("volumeUsd24h")
        if volume_usd24h and market_type == 'spot':
            # print(f"fetch_exchange_info.market: {market}")
            _symbol = str.replace(market.get('name'), '/', '')
            # print(f"fetch_exchange_info._symbol: {_symbol}")
            _base_asset = market.get('baseCurrency')
            _base_asset_precision = len(str(market.get('sizeIncrement'))) - 2
            _quote_asset = market.get('quoteCurrency')
            # Filters var
            _tick_size = market.get('priceIncrement')
            _min_qty = market.get('minProvideSize')
            _max_qty = market.get('largeOrderThreshold')
            _step_size = market.get('sizeIncrement')
            _min_notional = market.get('minProvideSize') * market.get('price')

            _price_filter = {
                "filterType": "PRICE_FILTER",
                "minPrice": str(_tick_size),
                "maxPrice": "100000.00000000",
                "tickSize": str(_tick_size)
            }
            _lot_size = {
                "filterType": "LOT_SIZE",
                "minQty": str(_min_qty),
                "maxQty": str(_max_qty),
                "stepSize": str(_step_size)
            }
            _min_notional = {
                "filterType": "MIN_NOTIONAL",
                "minNotional": str(_min_notional),
                "applyToMarket": True,
                "avgPriceMins": 5
            }

            symbol = {
                "symbol": _symbol,
                "status": "TRADING",
                "baseAsset": _base_asset,
                "baseAssetPrecision": _base_asset_precision,
                "quoteAsset": _quote_asset,
                "quotePrecision": _base_asset_precision,
                "quoteAssetPrecision": _base_asset_precision,
                "baseCommissionPrecision": 8,
                "quoteCommissionPrecision": 8,
                "orderTypes": ["LIMIT", "MARKET"],
                "icebergAllowed": False,
                "ocoAllowed": False,
                "quoteOrderQtyMarketAllowed": False,
                "allowTrailingStop": False,
                "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": False,
                "filters": [_price_filter, _lot_size, _min_notional],
                "permissions": ["SPOT"],
            }
            symbols.append(symbol)
            # print(f"fetch_exchange_info.symbol: {symbol}")

    _binance_res = {
        "timezone": "UTC",
        "serverTime": int(time.time() * 1000),
        "rateLimits": [],
        "exchangeFilters": [],
        "symbols": symbols,
    }
    return _binance_res


def ftx_order(order: {}, response_type=None) -> {}:
    # print(f"ftx_order.order: {order}")
    symbol = str.replace(order.get('market'), '/', '')
    order_id = order.get('id')
    order_list_id = -1
    client_order_id = order.get('clientId', str()) or str()
    price = str(order.get('price') or 0.0)
    orig_qty = str(order.get('size') or 0.0)
    executed_qty = str(order.get('filledSize') or 0.0)
    avg_fill_price = str(order.get('avgFillPrice') or 0.0)
    cummulative_quote_qty = str(Decimal(executed_qty) * Decimal(avg_fill_price))
    #
    ftx_status = order.get('status')
    if ftx_status in ('new', 'open') and not float(executed_qty):
        status = 'NEW'
    elif ftx_status in ('new', 'open') and float(executed_qty) and order.get('remainingSize'):
        status = 'PARTIALLY_FILLED'
    elif ftx_status == 'closed' and orig_qty == executed_qty:
        status = 'FILLED'
    else:
        status = 'CANCELED'
    #
    time_in_force = "GTC"
    _type = "LIMIT"
    side = order.get('side').upper()
    stop_price = '0.0'
    iceberg_qty = '0.0'
    #
    ftx_time = order.get('createdAt')
    _time = int(datetime.datetime.strptime(ftx_time.split('+')[0], TIMESTAMP_PATTERN).timestamp() * 1000)
    #
    update_time = _time
    is_working = True
    orig_quote_order_qty = str(Decimal(orig_qty) * Decimal(price))
    if response_type:
        binance_order = {
            "symbol": symbol,
            "origClientOrderId": client_order_id,
            "orderId": order_id,
            "orderListId": order_list_id,
            "clientOrderId": client_order_id,
            "transactTime": _time,
            "price": price,
            "origQty": orig_qty,
            "executedQty": executed_qty,
            "cummulativeQuoteQty": cummulative_quote_qty,
            "status": status,
            "timeInForce": time_in_force,
            "type": _type,
            "side": side,
        }
    elif response_type is None:
        binance_order = {
            "symbol": symbol,
            "orderId": order_id,
            "orderListId": order_list_id,
            "clientOrderId": client_order_id,
            "price": price,
            "origQty": orig_qty,
            "executedQty": executed_qty,
            "cummulativeQuoteQty": cummulative_quote_qty,
            "status": status,
            "timeInForce": time_in_force,
            "type": _type,
            "side": side,
            "stopPrice": stop_price,
            "icebergQty": iceberg_qty,
            "time": _time,
            "updateTime": update_time,
            "isWorking": is_working,
            "origQuoteOrderQty": orig_quote_order_qty,
        }
    else:
        binance_order = {
            "symbol": symbol,
            "orderId": order_id,
            "orderListId": order_list_id,
            "clientOrderId": client_order_id,
            "price": price,
            "origQty": orig_qty,
            "executedQty": executed_qty,
            "cummulativeQuoteQty": cummulative_quote_qty,
            "status": status,
            "timeInForce": time_in_force,
            "type": _type,
            "side": side,
        }
    # print(f"ftx_order.binance_order: {binance_order}")
    return binance_order


def ftx_orders(res: {}, response_type=None) -> []:
    # print(f"ftx_orders.res: {res}")
    binance_orders = []
    for order in res:
        i_order = ftx_order(order, response_type=response_type)
        binance_orders.append(i_order)
    # print(f"ftx_orders.binance_orders: {binance_orders}")
    return binance_orders


def ftx_fetch_funding_wallet(res: []) -> []:
    balances = []
    for balance in res:
        free = str(balance.get('free') or 0.0)
        total = str(balance.get('total') or 0.0)
        locked = str(Decimal(total) - Decimal(free))
        if float(total):
            _binance_res = {
                "asset": balance.get('coin'),
                "free": free,
                "locked": locked,
                "freeze": "0",
                "withdrawing": "0",
                "btcValuation": "0.0",
            }
            balances.append(_binance_res)
    return balances


def ftx_account_information(res: []) -> {}:
    balances = []
    for balance in res:
        free = str(balance.get('free') or 0.0)
        total = str(balance.get('total') or 0.0)
        locked = str(Decimal(total) - Decimal(free))
        _binance_res = {
            "asset": balance.get('coin'),
            "free": free,
            "locked": locked,
        }
        balances.append(_binance_res)

    binance_account_info = {
      "makerCommission": 0,
      "takerCommission": 0,
      "buyerCommission": 0,
      "sellerCommission": 0,
      "canTrade": True,
      "canWithdraw": False,
      "canDeposit": False,
      "updateTime": int(time.time() * 1000),
      "accountType": "SPOT",
      "balances": balances,
      "permissions": [
        "SPOT"
      ]
    }

    return binance_account_info


def ftx_order_book(res: {}) -> {}:
    binance_order_book = {"lastUpdateId": int(time.time() * 1000)}
    binance_order_book.update(
        {key: [[str(y) for y in x] for x in value] for key, value in res.items()}
    )
    return binance_order_book


def ftx_symbol_price_ticker(res: [], symbol):
    if symbol:
        binance_price_ticker = {
            "symbol": symbol,
            "price": str(res.get('price') or 0.0),
        }
    else:
        binance_price_ticker = []
        for i in res:
            price_ticker = {
                "symbol": i.get('name').replace('/', ''),
                "price": str(i.get('price') or 0.0),
            }
            binance_price_ticker.append(price_ticker)
    return binance_price_ticker


def ftx_ticker_price_change_statistics(res: [], symbol, end_time):
    _res = res[-1]
    ftx_time = _res.get('startTime')
    _time = int(datetime.datetime.strptime(ftx_time.split('+')[0], "%Y-%m-%dT%H:%M:%S").timestamp())
    binance_price_ticker = {
        "symbol": symbol,
        "priceChange": "0.0",
        "priceChangePercent": "0.0",
        "weightedAvgPrice": "0.0",
        "prevClosePrice": str(_res.get('open') or 0.0),
        "lastPrice": str(_res.get('close') or 0.0),
        "lastQty": "0.0",
        "bidPrice": "0.0",
        "bidQty": "0.0",
        "askPrice": "0.0",
        "askQty": "0.00",
        "openPrice": str(_res.get('open') or 0.0),
        "highPrice": str(_res.get('high') or 0.0),
        "lowPrice": str(_res.get('low') or 0.0),
        "volume": str(_res.get('volume') or 0.0),
        "quoteVolume": "0.0",
        "openTime": _time * 1000,
        "closeTime": end_time * 1000,
        "firstId": 0,
        "lastId": 1,
        "count": 1,
    }
    return binance_price_ticker


def ftx_klines(res: [], interval: int) -> []:
    binance_klines = []
    for i in res:
        start_time = int(datetime.datetime.strptime(i.get('startTime').split('+')[0],
                                                    "%Y-%m-%dT%H:%M:%S").timestamp() * 1000)
        candle = [
            start_time,
            str(i.get('open') or 0.0),
            str(i.get('high') or 0.0),
            str(i.get('low') or 0.0),
            str(i.get('close') or 0.0),
            str(i.get('volume') or 0.0),
            start_time + interval * 1000,
            '0.0',
            0,
            '0.0',
            '0.0',
            '0.0',
        ]
        binance_klines.append(candle)
    return binance_klines


def ftx_account_trade_list(res: []) -> []:
    binance_trade_list = []
    for trade in res:
        price = str(trade.get('price') or 0.0)
        qty = str(trade.get('size') or 0.0)
        quote_qty = str(Decimal(price) * Decimal(qty))
        ftx_time = trade.get('time')
        _time = int(datetime.datetime.strptime(ftx_time.split('+')[0], TIMESTAMP_PATTERN).timestamp() * 1000)
        binance_trade = {
            "symbol": trade.get('market').replace('/', ''),
            "id": trade.get('tradeId'),
            "orderId": trade.get('orderId'),
            "orderListId": -1,
            "price": price,
            "qty": qty,
            "quoteQty": quote_qty,
            "commission": str(trade.get('fee')),
            "commissionAsset": trade.get('feeCurrency'),
            "time": _time,
            "isBuyer": bool(trade.get('liquidity') == 'taker'),
            "isMaker": bool(trade.get('liquidity') == 'maker'),
            "isBestMatch": True,
        }
        binance_trade_list.append(binance_trade)
    return binance_trade_list


def ftx_stream_compare(msg_new: {}, msg_prev: {}, ch_type: str) -> bool:
    if not msg_prev:
        return True
    else:
        _msg_new = msg_new.get('data')
        _msg_prev = msg_prev.get('data')
        for i in CH_KEY.get(ch_type):
            if _msg_prev.get(i) != _msg_new.get(i):
                return True
        return False


# noinspection PyUnboundLocalVariable
def ftx_stream_convert(msg: {}, symbol: str = None, ch_type: str = None) -> {}:
    msg_binance = {}
    data = msg.get('data')
    _symbol = (symbol if symbol else data.get('market')).replace('/', '').lower()
    if ch_type == 'miniTicker':
        msg_binance = {
            'stream': f"{_symbol}@miniTicker",
            'data': {
                "e": "24hrMiniTicker",
                "E": int(data.get('time') * 1000),
                "s": _symbol.upper(),
                "c": str(data.get('last') or 0.0),
                "o": "0.0",
                "h": "0.0",
                "l": "0.0",
                "v": "0",
                "q": "0"
            }
        }
    elif ch_type == 'depth5':
        msg_binance = {
            'stream': f"{_symbol}@depth5",
            'data': {
                "lastUpdateId": int(data.get('time') * 1000),
                "bids": [[str(data.get('bid') or 0.0), "0.0"]],
                "asks": [[str(data.get('ask') or 0.0), "0.0"]]
            }
        }
    else:
        ftx_time = None
        if msg.get('channel') == 'orders' and data.get('status') == 'closed':
            ftx_time = data.get('createdAt')
            client_order_id = data.get('clientId')
            order_quantity = str(data.get('size'))
            order_price = str(data.get('price'))
            order_status = 'FILLED' if data.get('filledSize') == data.get('size') else 'CANCELED'
            order_id = data.get('id')
            last_executed_quantity = str(0.0)
            cumulative_filled_quantity = str(data.get('filledSize') or 0.0)
            last_executed_price = str(data.get('avgFillPrice') or 0.0)
            trade_id = -1
            cumulative_quote_asset = str(Decimal(cumulative_filled_quantity) * Decimal(last_executed_price))
            last_quote_asset = cumulative_quote_asset
            quote_order_qty = str(Decimal(order_quantity) * Decimal(order_price))
        elif msg.get('channel') == 'fills':
            ftx_time = data.get('time')
            client_order_id = data.get('clientOrderId')
            order_quantity = '0.0'
            order_price = '0.0'
            order_status = 'PARTIALLY_FILLED'
            order_id = data.get('orderId')
            last_executed_quantity = str(data.get('size') or 0.0)
            cumulative_filled_quantity = '0.0'
            last_executed_price = str(data.get('price') or 0.0)
            trade_id = data.get('tradeId')
            cumulative_quote_asset = '0.0'
            last_quote_asset = str(Decimal(last_executed_quantity) * Decimal(last_executed_price))
            quote_order_qty = '0.0'
        if ftx_time:
            _time = int(datetime.datetime.strptime(ftx_time.split('+')[0], TIMESTAMP_PATTERN).timestamp() * 1000)
            msg_binance = {
                "e": "executionReport",
                "E": _time,
                "s": _symbol.upper(),
                "c": client_order_id or str(),
                "S": data.get('side').upper(),
                "o": "LIMIT",
                "f": "GTC",
                "q": order_quantity,
                "p": order_price,
                "P": "0.00000000",
                "F": "0.00000000",
                "g": -1,
                "C": "",
                "x": "TRADE",
                "X": order_status,
                "r": "NONE",
                "i": order_id,
                "l": last_executed_quantity,
                "z": cumulative_filled_quantity,
                "L": last_executed_price,
                "n": '0.0',
                "N": "NONE",
                "T": _time,
                "t": trade_id,
                "I": 123456789,
                "w": True,
                "m": False,
                "M": False,
                "O": _time,
                "Z": cumulative_quote_asset,
                "Y": last_quote_asset,
                "Q": quote_order_qty
            }
    return msg_binance