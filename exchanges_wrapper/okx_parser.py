"""
Parser for convert OKX REST API/WSS V5 response to Binance like result
"""
import time
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def fetch_server_time(res: []) -> {}:
    if res:
        return {'serverTime': int(res[0].get('ts'))}


def exchange_info(server_time: int, trading_symbol: [], tickers: [], symbol_t) -> {}:
    symbols = []
    symbols_price = {
        pair.get('instId').replace('-', ''): Decimal(pair.get('last'))
        for pair in tickers
    }
    for market in trading_symbol:
        _symbol = market.get("instId").replace('-', '')
        if symbols_price.get(_symbol) and _symbol == symbol_t:
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
                "maxPrice": "100000000",
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
                "minNotional": _min_notional,
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


def place_order_response(res: {}, req: {}) -> {}:
    return {
        "symbol": req["instId"].replace('-', ''),
        "orderId": int(res["ordId"]),
        "orderListId": -1,
        "clientOrderId": res["clOrdId"],
        "price": req["px"],
        "origQty": req["sz"],
        "executedQty": "0",
        "cummulativeQuoteQty": "0",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": req["ordType"].upper(),
        "side": req["side"].upper(),
    }


def account_information(res: [], u_time: str) -> {}:
    balances = []
    for asset in res:
        _binance_res = {
            "asset": asset.get('ccy'),
            "free": asset.get('availBal'),
            "locked": asset.get('frozenBal'),
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
        "brokered": False,
        "updateTime": int(u_time),
        "accountType": "SPOT",
        "balances": balances,
        "permissions": ["SPOT"],
    }


def order_book(res: {}) -> {}:
    asks = []
    bids = []
    binance_order_book = {"lastUpdateId": int(res.get('ts'))}
    [asks.append(ask[:2]) for ask in res.get('asks')]
    binance_order_book['asks'] = asks
    [bids.append(bid[:2]) for bid in res.get('bids')]
    binance_order_book['bids'] = bids
    return binance_order_book


def ticker_price_change_statistics(res: {}) -> {}:
    price_change = str(Decimal(res.get('last')) - Decimal(res.get('open24h')))
    price_change_percent = str(100 * (Decimal(res.get('last')) - Decimal(res.get('open24h'))) /
                               Decimal(res.get('open24h')))
    close_time = int(res.get('ts'))
    open_time = close_time - 60 * 60 * 24
    return {
        "symbol": res.get('instId').replace('-', ''),
        "priceChange": price_change,
        "priceChangePercent": price_change_percent,
        "weightedAvgPrice": str(
            Decimal(res.get('volCcy24h')) / Decimal(res.get('vol24h'))
        ),
        "prevClosePrice": res.get('open24h'),
        "lastPrice": res.get('last'),
        "lastQty": res.get('lastSz'),
        "bidPrice": res.get('bidPx'),
        "bidQty": res.get('bidSz'),
        "askPrice": res.get('askPx'),
        "askQty": res.get('askSz'),
        "openPrice": res.get('open24h'),
        "highPrice": res.get('high24h'),
        "lowPrice": res.get('low24h'),
        "volume": res.get('vol24h'),
        "quoteVolume": res.get('volCcy24h'),
        "openTime": open_time,
        "closeTime": close_time,
        "firstId": 0,
        "lastId": 1,
        "count": 1,
    }


def fetch_symbol_price_ticker(res: {}, symbol) -> {}:
    return {
        "symbol": symbol,
        "price": res.get('last')
    }


def ticker(res: {}) -> {}:
    symbol = res.get('instId').replace('-', '')
    return {
        'stream': f"{symbol.lower()}@miniTicker",
        'data': {
            "e": "24hrMiniTicker",
            "E": int(res.get('ts')) // 1000,
            "s": symbol,
            "c": str(res.get('last')),
            "o": str(res.get('open24h')),
            "h": str(res.get('high24h')),
            "l": str(res.get('low24h')),
            "v": str(res.get('vol24h')),
            "q": str(res.get('volCcy24h')),
        },
    }


def interval(_interval: str) -> str:
    resolution = {
        '1m': '1m',
        '3m': '3m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1H',
        '2h': '2H',
        '4h': '4H',
        '1d': '1Dutc',
        '1w': '1Wutc',
        '1M': '1Mutc'
    }
    return resolution.get(_interval, 0)


def klines(res: [], _interval: str) -> []:
    binance_klines = []
    for i in res:
        start_time = int(i[0])
        _candle = [
            start_time,
            i[1],
            i[2],
            i[3],
            i[4],
            i[5],
            start_time + interval2value(_interval) * 1000 - 1,
            i[6],
            1,
            '0.0',
            '0.0',
            '0.0',
        ]
        binance_klines.append(_candle)
    return binance_klines


def interval2value(_interval: str) -> int:
    resolution = {
        '1m': 60,
        '3m': 60 * 3,
        '5m': 60 * 5,
        '15m': 60 * 15,
        '30m': 60 * 30,
        '1H': 60 * 60,
        '2H': 60 * 60 * 2,
        '4H': 60 * 60 * 4,
        '1Dutc': 60 * 60 * 24,
        '1Wutc': 60 * 60 * 24 * 7,
        '1Mutc': 60 * 60 * 24 * 31
    }
    return resolution.get(_interval, 0)


def candle(res: [], symbol: str = None, ch_type: str = None) -> {}:
    symbol = symbol.replace('-', '').lower()
    start_time = int(res[0])
    _interval = ch_type.replace('kline_', '')
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
                'o': res[1],
                'c': res[4],
                'h': res[2],
                'l': res[3],
                'v': res[5],
                'n': 1,
                'x': False,
                'q': res[6],
                'V': '0.0',
                'Q': '0.0',
                'B': '0',
            },
        },
    }


def order_book_ws(res: {}, symbol: str) -> {}:
    symbol = symbol.replace('-', '').lower()
    return {
        'stream': f"{symbol}@depth5",
        'data': order_book(res)
    }


def on_funds_update(res: {}) -> {}:
    event_time = int(time.time() * 1000)
    data = res.get('details')
    funds = []
    ts = 0
    for currency in data:
        balance = {
            'a': currency.get('ccy'),
            'f': currency.get('availBal'),
            'l': currency.get('frozenBal'),
        }
        funds.append(balance)
        ts = max(ts, int(currency.get('uTime')))

    return {
        'e': 'outboundAccountPosition',
        'E': event_time,
        'u': ts or event_time,
        'B': funds,
    }


def on_order_update(res: {}) -> {}:
    # print(f"on_order_update.res: {res}")
    order_quantity = res.get('sz')
    order_price = res.get('px')
    quote_order_qty = str(Decimal(order_quantity) * Decimal(order_price))
    cumulative_filled_quantity = res.get('accFillSz')
    cumulative_quote_asset = str(Decimal(cumulative_filled_quantity) * Decimal(res.get('avgPx')))
    #
    last_executed_quantity = res.get('fillSz') or '0'
    last_executed_price = res.get('fillPx') or '0'
    last_quote_asset_transacted = str(Decimal(last_executed_quantity) * Decimal(last_executed_price))
    #
    if res.get('state') == 'canceled':
        status = 'CANCELED'
    elif res.get('state') == 'partially_filled':
        status = 'PARTIALLY_FILLED'
    elif res.get('state') == 'filled':
        status = 'FILLED'
    else:
        status = 'NEW'
    return {
        "e": "executionReport",
        "E": int(res.get('uTime')),
        "s": res.get('instId').replace('-', ''),
        "c": res.get('clOrdId'),
        "S": res.get('side').upper(),
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
        "i": int(res.get('ordId')),
        "l": last_executed_quantity,
        "z": cumulative_filled_quantity,
        "L": last_executed_price,
        "n": res.get('fillFee') or '0',
        "N": res.get('fillFeeCcy'),
        "T": res.get('uTime'),
        "t": int(res.get('tradeId') or -1),
        "I": 123456789,
        "w": True,
        "m": False,
        "M": False,
        "O": int(res.get('cTime')),
        "Z": cumulative_quote_asset,
        "Y": last_quote_asset_transacted,
        "Q": quote_order_qty,
    }


def on_balance_update(res: list, buffer: dict, transfer: bool) -> ():
    res_diff = []
    for i in res:
        asset = i.get('ccy')
        ccy_bal_new = i.get('cashBal')
        ccy_bal = buffer.get(asset)
        if ccy_bal and transfer:
            balance = {
                'e': 'balanceUpdate',
                'E': int(i.get('uTime')),
                'a': asset,
                'd': str(Decimal(ccy_bal_new) - Decimal(ccy_bal)),
                'T': int(time.time() * 1000)
            }
            res_diff.append(balance)
        buffer[asset] = ccy_bal_new
    return res_diff, buffer


def funding_wallet(res: []) -> []:
    balances = []
    for balance in res:
        _binance_res = {
            "asset": balance.get('ccy'),
            "free": balance.get('availBal'),
            "locked": "0",
            "freeze": balance.get('frozenBal'),
            "withdrawing": "0",
            "btcValuation": "0.0",
        }
        balances.append(_binance_res)
    return balances


def order_trade_list(res: []) -> []:
    binance_trade_list = []
    for trade in res:
        price = trade.get('fillPx')
        qty = trade.get('fillSz')
        quote_qty = str(Decimal(price) * Decimal(qty))
        binance_trade = {
            "symbol": trade.get('instId').replace('-', ''),
            "id": trade.get('tradeId'),
            "orderId": trade.get('ordId'),
            "orderListId": -1,
            "price": price,
            "qty": qty,
            "quoteQty": quote_qty,
            "commission": str(abs(float(trade.get('fee')))),
            "commissionAsset": trade.get('feeCcy'),
            "time": trade.get('ts'),
            "isBuyer": trade.get('side') == 'buy',
            "isMaker": trade.get('execType') == 'M',
            "isBestMatch": True,
        }
        binance_trade_list.append(binance_trade)
    return binance_trade_list
