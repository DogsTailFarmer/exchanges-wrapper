"""
Parser for convert Bybit REST API/WSS V5 response to Binance like result
"""
import time
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def fetch_server_time(res: {}) -> {}:
    return {'serverTime': int(res['timeNano']) // 1000000}


def exchange_info(server_time: int, trading_symbol: []) -> {}:
    symbols = []

    for market in trading_symbol:

        _price_filter = {
            "filterType": "PRICE_FILTER",
            "minPrice": '0',
            "maxPrice": '0',
            "tickSize": market['priceFilter']['tickSize']
        }
        _lot_size = {
            "filterType": "LOT_SIZE",
            "minQty": market['lotSizeFilter']['minOrderQty'],
            "maxQty": market['lotSizeFilter']['maxOrderQty'],
            "stepSize": market['lotSizeFilter']['minOrderQty']
        }
        _min_notional = {
            "filterType": "MIN_NOTIONAL",
            "minNotional": market['lotSizeFilter']['minOrderAmt'],
            "applyToMarket": True,
            "avgPriceMins": 0,
        }
        _percent_price = {
            "filterType": "PERCENT_PRICE",
            "multiplierUp": "5",
            "multiplierDown": "0.2",
            "avgPriceMins": 5
        }

        symbol = {
            "symbol": market['symbol'],
            "status": "TRADING",
            "baseAsset": market['baseCoin'],
            "baseAssetPrecision": len(market['lotSizeFilter']['basePrecision']) - 2,
            "quoteAsset": market['quoteCoin'],
            "quotePrecision": 8,
            "quoteAssetPrecision": len(market['lotSizeFilter']['quotePrecision']) - 2,
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
        symbols.append(symbol)

    return {
        "timezone": "UTC",
        "serverTime": server_time,
        "rateLimits": [],
        "exchangeFilters": [],
        "symbols": symbols,
    }


def orders(res: list, response_type=None) -> list:
    return [order(_order, response_type=response_type) for _order in res]


def order(res: dict, response_type=None) -> dict:
    symbol = res['symbol']
    order_id = int(res['orderId'])
    order_list_id = -1
    client_order_id = res.get('orderLinkId')
    price = res['price']
    orig_qty = res['qty']
    executed_qty = res['cumExecQty']
    cummulative_quote_qty = res['cumExecValue'] or '0.0'
    orig_quote_order_qty = str(Decimal(orig_qty) * Decimal(price))

    state = res['orderStatus']
    status = {
        'Rejected': 'REJECTED',
        'Canceled': 'CANCELED',
        'PartiallyFilledCanceled': 'CANCELED',
        'PartiallyFilled': 'PARTIALLY_FILLED',
        'Filled': 'FILLED'
    }.get(state, 'NEW')

    _type = "LIMIT"
    time_in_force = "GTC"
    side = res['side'].upper()
    stop_price = '0.0'
    iceberg_qty = '0.0'
    _time = int(res['createdTime'])
    update_time = int(res['updatedTime'])
    is_working = True

    response = {
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

    if response_type:
        response |= {
            "origClientOrderId": client_order_id,
            "transactTime": _time,
        }
    elif response_type is None:
        response |= {
            "stopPrice": stop_price,
            "icebergQty": iceberg_qty,
            "time": _time,
            "updateTime": update_time,
            "isWorking": is_working,
            "origQuoteOrderQty": orig_quote_order_qty,
        }

    return response


def order_book(res: {}) -> {}:
    return {"lastUpdateId": res['u'],
            "bids": res['b'],
            "asks": res['a'],
            }
