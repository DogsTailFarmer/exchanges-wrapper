#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Parser for convert OKX REST API/WSS response to Binance like result
"""
from decimal import Decimal
import logging

logger = logging.getLogger('exch_srv_logger')


def fetch_server_time(res: []) -> {}:
    if res:
        return {'serverTime': int(res[0].get('ts'))}


def exchange_info(server_time: int, trading_symbol: [], tickers: []) -> {}:
    symbols = []
    symbols_price = {}
    for pair in tickers:
        symbols_price[pair.get('instId').replace('-', '')] = Decimal(pair.get('last'))

    for market in trading_symbol:
        _symbol = market.get("instId").replace('-', '')
        _base_asset = market.get("baseCcy")
        _quote_asset = market.get("quoteCcy")
        _base_asset_precision = len(market.get('lotSz')) - 2
        # Filters var
        _tick_size = market.get('tickSz')
        _min_qty = market.get('minSz')
        _max_qty = market.get('maxLmtSz')
        _step_size = market.get('lotSz')
        _min_notional = str(Decimal(_min_qty) * symbols_price.get(_symbol))
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
            "avgPriceMins": 0
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
            "cancelReplaceAllowed": False,
            "isSpotTradingAllowed": True,
            "isMarginTradingAllowed": False,
            "filters": [_price_filter, _lot_size, _min_notional],
            "permissions": ["SPOT"],
        }
        symbols.append(symbol)

    _binance_res = {
        "timezone": "UTC",
        "serverTime": server_time,
        "rateLimits": [],
        "exchangeFilters": [],
        "symbols": symbols,
    }
    return _binance_res


def orders(res: [], response_type=None) -> []:
    binance_orders = []
    for _order in res:
        i_order = order(_order, response_type=response_type)
        binance_orders.append(i_order)
    return binance_orders


def order(res: {}, response_type=None) -> {}:
    symbol = res.get('instId').replace('-', '')
    order_id = int(res.get('ordId'))
    order_list_id = -1
    client_order_id = res.get('clOrdId')
    price = res.get('px', "0")
    orig_qty = res.get('sz', "0")
    executed_qty = res.get('accFillSz')
    avg_filled_price = res.get('avgPx') or "0"
    cummulative_quote_qty = str(Decimal(executed_qty) * Decimal(avg_filled_price))
    orig_quote_order_qty = str(Decimal(orig_qty) * Decimal(price))
    #
    if res.get('state') == 'canceled':
        status = 'CANCELED'
    elif res.get('state') == 'partially_filled':
        status = 'PARTIALLY_FILLED'
    elif res.get('state') == 'filled':
        status = 'FILLED'
    else:
        status = 'NEW'
    #
    _type = "LIMIT"
    time_in_force = "GTC"
    side = 'BUY' if 'buy' in res.get('side') else 'SELL'
    stop_price = '0.0'
    iceberg_qty = '0.0'
    _time = int(res.get('cTime'))
    update_time = int(res.get('uTime'))
    is_working = True
    #
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
    # print(f"order.binance_order: {binance_order}")
    return binance_order


def account_information(res: [], u_time: str) -> {}:
    balances = []
    for asset in res:
        _binance_res = {
            "asset": asset.get('ccy'),
            "free": asset.get('availBal'),
            "locked": asset.get('frozenBal'),
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
      "brokered": False,
      "updateTime": int(u_time),
      "accountType": "SPOT",
      "balances": balances,
      "permissions": [
        "SPOT"
      ]
    }
    return binance_account_info


def order_book(res: {}) -> {}:
    binance_order_book = {"lastUpdateId": res.get('ts')}
    binance_order_book.setdefault('bids', res.get('bids'))
    binance_order_book.setdefault('asks', res.get('asks'))
    return binance_order_book
