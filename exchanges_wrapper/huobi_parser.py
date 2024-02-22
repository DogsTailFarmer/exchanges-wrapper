"""
Parser for convert Huobi REST API/WSS response to Binance like result
"""
import time
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def on_balance_update(res: {}) -> {}:
    return {
        'e': 'balanceUpdate',
        'E': res.get('transactTime'),
        'a': res.get('currency').upper(),
        'd': str(res.get('transactAmt')),
        'T': int(time.time() * 1000),
    }


def fetch_server_time(res: {}) -> {}:
    return {'serverTime': res}


def exchange_info(server_time: int, _symbol_params) -> {}:
    _tick_size = str(10**(-_symbol_params.get('pp')))
    _price_filter = {
        "filterType": "PRICE_FILTER",
        "minPrice": _tick_size,
        "maxPrice": "100000000",
        "tickSize": _tick_size
    }
    _lot_size = {
        "filterType": "LOT_SIZE",
        "minQty": str(_symbol_params.get('minoa')),
        "maxQty": str(_symbol_params.get('maxoa')),
        "stepSize": str(10**(-_symbol_params.get('ap')))
    }
    _min_notional = {
        "filterType": "MIN_NOTIONAL",
        "minNotional": str(_symbol_params.get('minov')),
        "applyToMarket": True,
        "avgPriceMins": 5
    }
    _percent_price = {
        "filterType": "PERCENT_PRICE",
        "multiplierUp": "5",
        "multiplierDown": "0.2",
        "avgPriceMins": 5
    }

    symbol = {
        "symbol": _symbol_params.get("symbol").upper(),
        "status": "TRADING",
        "baseAsset": _symbol_params.get("bc").upper(),
        "baseAssetPrecision": _symbol_params.get("ap"),
        "quoteAsset": _symbol_params.get("qc").upper(),
        "quoteAssetPrecision": _symbol_params.get("vp"),
        "baseCommissionPrecision": 8,
        "quoteCommissionPrecision": 8,
        "orderTypes": ["LIMIT", "MARKET"],
        "icebergAllowed": False,
        "ocoAllowed": False,
        "quoteOrderQtyMarketAllowed": False,
        "allowTrailingStop": False,
        "cancelReplaceAllowed": False,
        "isSpotTradingAllowed": True,
        "isMarginTradingAllowed": False,
        "filters": [_price_filter, _lot_size, _min_notional, _percent_price],
        "permissions": ["SPOT"],
    }

    return {
        "timezone": "UTC",
        "serverTime": server_time,
        "rateLimits": [],
        "exchangeFilters": [],
        "symbols": [symbol],
    }


def orders(res: [], response_type=None) -> []:
    binance_orders = []
    for _order in res:
        i_order = order(_order, response_type=response_type)
        binance_orders.append(i_order)
    return binance_orders


def order(res: {}, response_type=None) -> {}:
    symbol = res.get('symbol').upper()
    order_id = res.get('id')
    order_list_id = -1
    client_order_id = res.get('client-order-id')
    price = res.get('price', "0")
    orig_qty = res.get('amount', "0")
    executed_qty = res.get('filled-amount', res.get('field-amount', "0"))
    cummulative_quote_qty = res.get('filled-cash-amount', res.get('field-cash-amount', "0"))
    orig_quote_order_qty = str(Decimal(orig_qty) * Decimal(price))
    #
    if res.get('state') in ('canceled', 'partial-canceled'):
        status = 'CANCELED'
    elif res.get('state') == 'partial-filled':
        status = 'PARTIALLY_FILLED'
    elif res.get('state') == 'filled':
        status = 'FILLED'
    else:
        status = 'NEW'
    #
    _type = "LIMIT"
    time_in_force = "GTC"
    side = 'BUY' if 'buy' in res.get('type') else 'SELL'
    stop_price = '0.0'
    iceberg_qty = '0.0'
    _time = res.get('created-at')
    update_time = res.get('canceled-at') or res.get('finished-at') or _time
    is_working = True
    #
    if response_type:
        return {
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
        return {
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
        return {
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


def account_information(res: {}) -> {}:
    balances = []
    res[:] = [i for i in res if i.get('balance') != '0']
    assets = {}
    for balance in res:
        asset = balance.get('currency')
        asset_i = assets.get(asset, {})
        if balance.get('available'):
            asset_i.setdefault('available', balance.get('available'))
        else:
            asset_i.setdefault('frozen', balance.get('balance', '0'))
        assets[asset] = asset_i
    for asset in assets:
        free = assets.get(asset, {}).get('available', '0')
        locked = assets.get(asset, {}).get('frozen', '0')
        _binance_res = {
            "asset": asset.upper(),
            "free": free,
            "locked": locked,
        }
        balances.append(_binance_res)

    return {
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
        "permissions": ["SPOT"],
    }


def order_book(res: {}) -> {}:
    binance_order_book = {"lastUpdateId": res.get('ts')}
    binance_order_book.setdefault('bids', res.get('bids'))
    binance_order_book.setdefault('asks', res.get('asks'))
    return binance_order_book


def order_book_ws(res: {}, symbol: str) -> {}:
    bids = res.get('tick').get('bids')[:5]
    asks = res.get('tick').get('asks')[:5]
    return {
        'stream': f"{symbol}@depth5",
        'data': {'lastUpdateId': res.get('ts'),
                 'bids': bids,
                 'asks': asks,
                 }
    }


def fetch_symbol_price_ticker(res: {}, symbol) -> {}:
    return {
        "symbol": symbol,
        "price": str(res.get('data')[0].get('price'))
    }


def ticker_price_change_statistics(res: {}, symbol) -> {}:
    return {
        "symbol": symbol,
        "priceChange": str(res.get('close') - res.get('open')),
        "priceChangePercent": str(
            100 * (res.get('close') - res.get('open')) / res.get('open')
        ),
        "weightedAvgPrice": "0.0",
        "prevClosePrice": str(res.get('open')),
        "lastPrice": str(res.get('close')),
        "lastQty": "0.0",
        "bidPrice": "0",
        "bidQty": "0.0",
        "askPrice": "0",
        "askQty": "0.00",
        "openPrice": str(res.get('open')),
        "highPrice": str(res.get('high')),
        "lowPrice": str(res.get('low')),
        "volume": str(res.get('vol')),
        "quoteVolume": "0.0",
        "openTime": int(time.time() * 1000) - 60 * 60 * 24,
        "closeTime": int(time.time() * 1000),
        "firstId": 0,
        "lastId": res.get('id'),
        "count": res.get('count'),
    }


def ticker(res: {}, symbol: str = None) -> {}:
    tick = res.get('tick')
    return {
        'stream': f"{symbol}@miniTicker",
        'data': {
            "e": "24hrMiniTicker",
            "E": int(res.get('ts') / 1000),
            "s": symbol.upper(),
            "c": str(tick.get('lastPrice')),
            "o": str(tick.get('open')),
            "h": str(tick.get('high')),
            "l": str(tick.get('low')),
            "v": str(tick.get('amount')),
            "q": str(tick.get('vol')),
        },
    }


def interval(_interval) -> str:
    resolution = {
        '1m': '1min',
        '5m': '5min',
        '15m': '15min',
        '30m': '30min',
        '1h': '60min',
        '4h': '4hour',
        '1d': '1day',
        '1w': '1week',
        '1M': '1mon'
    }
    return resolution.get(_interval, 'unresolved')


def interval2value(_interval) -> int:
    resolution = {
        '1min': 60,
        '5min': 5 * 60,
        '15min': 15 * 60,
        '30min': 30 * 60,
        '60min': 60 * 60,
        '4hour': 4 * 60 * 60,
        '1day': 24 * 60 * 60,
        '1week': 7 * 24 * 60 * 60,
        '1mon': 31 * 24 * 60 * 60
    }
    return resolution.get(_interval, 0)


def klines(res: [], _interval: str) -> []:
    binance_klines = []
    for i in res:
        start_time = i.get('id') * 1000
        _candle = [
            start_time,
            str(i.get('open')),
            str(i.get('high')),
            str(i.get('low')),
            str(i.get('close')),
            str(i.get('amount')),
            start_time + interval2value(_interval) * 1000 - 1,
            str(i.get('vol')),
            i.get('count'),
            '0.0',
            '0.0',
            '0.0',
        ]
        binance_klines.append(_candle)
    return binance_klines


def candle(res: [], symbol: str = None, ch_type: str = None) -> {}:
    tick = res.get('tick')
    start_time = tick.get('id')
    _interval = ch_type.split('_')[1]
    end_time = start_time + interval2value(interval(_interval)) * 1000 - 1
    return {
        'stream': f"{symbol}@{ch_type}",
        'data': {
            'e': 'kline',
            'E': int(time.time()),
            's': symbol.upper(),
            'k': {
                't': start_time,
                'T': end_time,
                's': symbol.upper(),
                'i': _interval,
                'f': 100,
                'L': 200,
                'o': str(tick.get('open')),
                'c': str(tick.get('close')),
                'h': str(tick.get('high')),
                'l': str(tick.get('low')),
                'v': str(tick.get('amount')),
                'n': tick.get('count'),
                'x': False,
                'q': str(tick.get('vol')),
                'V': '0.0',
                'Q': '0.0',
                'B': '0',
            },
        },
    }


def on_funds_update(data: {}) -> {}:
    event_time = int(time.time() * 1000)
    binance_funds = {
        'e': 'outboundAccountPosition',
        'E': event_time,
        'u': data.get('changeTime') or event_time,
    }
    total = data.get('balance')
    free = data.get('available')
    locked = str(Decimal(total) - Decimal(free))
    balance = {
        'a': data.get('currency').upper(),
        'f': free,
        'l': locked
    }
    funds = [balance]
    binance_funds['B'] = funds
    return binance_funds


def on_order_update(_order: {}) -> {}:
    event = _order['lastEvent']
    order_quantity = event.get('orderSize', event.get('orderValue'))
    order_price = event.get('orderPrice', event.get('tradePrice'))
    quote_order_qty = str(Decimal(order_quantity) * Decimal(order_price))
    cumulative_filled_quantity = _order['executedQty']
    cumulative_quote_asset = str(Decimal(cumulative_filled_quantity) * Decimal(order_price))
    #
    last_executed_quantity = event.get('tradeVolume')
    last_executed_price = event.get('tradePrice')
    last_quote_asset_transacted = str(Decimal(last_executed_quantity) * Decimal(last_executed_price))
    #
    if event.get('orderStatus') in ('canceled', 'partial-canceled'):
        status = 'CANCELED'
    elif cumulative_filled_quantity >= Decimal(order_quantity):
        status = 'FILLED'
    elif event.get('orderStatus') == 'partial-filled' or cumulative_filled_quantity > 0:
        status = 'PARTIALLY_FILLED'
    else:
        status = 'NEW'
    return {
        "e": "executionReport",
        "E": int(time.time() * 1000),
        "s": event.get('symbol').upper(),
        "c": event.get('clientOrderId'),
        "S": event.get('orderSide').upper(),
        "o": "LIMIT",
        "f": "GTC",
        "q": order_quantity,
        "p": order_price,
        "P": "0.00000000",
        "F": "0.00000000",
        "g": -1,
        "C": "",
        "x": "TRADE",
        "X": status,
        "r": "NONE",
        "i": event.get('orderId'),
        "l": last_executed_quantity,
        "z": str(cumulative_filled_quantity),
        "L": last_executed_price,
        "n": event.get('transactFee'),
        "N": event.get('feeCurrency').upper(),
        "T": event.get('tradeTime'),
        "t": event.get('tradeId'),
        "I": 123456789,
        "w": True,
        "m": not event.get('aggressor'),
        "M": False,
        "O": event.get('orderCreateTime'),
        "Z": cumulative_quote_asset,
        "Y": last_quote_asset_transacted,
        "Q": quote_order_qty,
    }


def account_trade_list(res: []) -> []:
    binance_trade_list = []
    for trade in res:
        price = trade['price']
        qty = trade['filled-amount']
        quote_qty = str(Decimal(price) * Decimal(qty))
        binance_trade = {
            "symbol": trade['symbol'].upper(),
            "id": trade['trade-id'],
            "orderId": int(trade['order-id']),
            "orderListId": -1,
            "price": price,
            "qty": qty,
            "quoteQty": quote_qty,
            "commission": trade['filled-fees'],
            "commissionAsset": trade['fee-currency'],
            "time": trade['created-at'],
            "isBuyer": 'buy' in trade['type'],
            "isMaker": trade['role'] == 'maker',
            "isBestMatch": True,
        }
        binance_trade_list.append(binance_trade)
    return binance_trade_list
