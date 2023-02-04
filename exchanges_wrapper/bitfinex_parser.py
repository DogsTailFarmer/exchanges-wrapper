"""
Parser for convert Bitfinex REST API/WSS response to Binance like result
"""
import time
from decimal import Decimal
import logging

logger = logging.getLogger('exch_srv_logger')


class OrderBook:
    def __init__(self, _order_book, symbol) -> None:
        self.symbol = symbol[1:].replace(':', '').lower()
        self.last_update_id = 1
        self.asks = {}
        self.bids = {}
        for i in _order_book:
            if i[2] > 0:
                self.bids[str(i[0])] = str(i[2])
            else:
                self.asks[str(i[0])] = str(abs(i[2]))

    def get_book(self) -> dict:
        bids = list(map(list, self.bids.items()))
        bids.sort(key=lambda x: float(x[0]), reverse=True)
        asks = list(map(list, self.asks.items()))
        asks.sort(key=lambda x: float(x[0]), reverse=False)
        return {
            'stream': f"{self.symbol}@depth5",
            'data': {'lastUpdateId': self.last_update_id,
                     'bids': bids[0:5],
                     'asks': asks[0:5],
                     }
        }

    def update_book(self, _update):
        self.last_update_id += 1
        if _update[1]:
            if _update[2] > 0:
                self.bids[str(_update[0])] = str(_update[2])
            else:
                self.asks[str(_update[0])] = str(abs(_update[2]))
        else:
            if _update[2] > 0:
                self.bids.pop(str(_update[0]), None)
            else:
                self.asks.pop(str(_update[0]), None)

    def __call__(self):
        return self


def get_symbols(symbols_details: []) -> str:
    symbols = []
    res = ",t"
    for symbol_details in symbols_details:
        symbol = symbol_details['pair']
        if 'f0' not in symbol:
            symbols.append(symbol.upper())
    return f"t{res.join(symbols)}"


def tick_size(precision, _price):
    x = int(_price)
    _price = str(_price)
    if '.' not in _price:
        _price += ".0"
    k = len(_price.split('.')[1])
    x = len(_price.split('.')[0]) if k and x else 0
    if k + x - precision > 0:
        k = precision - x
    elif k + x - precision < 0:
        k += precision - x - k
    res = (1 / 10 ** k) if k else 1
    return res


def symbol_name(_pair: str) -> ():
    if ':' in _pair:
        pair = _pair.replace(':', '').upper()
        base_asset = _pair.split(':')[0].upper()
        quote_asset = _pair.split(':')[1].upper()
    else:
        pair = _pair.upper()
        base_asset = _pair[0:3].upper()
        quote_asset = _pair[3:].upper()
    return pair, base_asset, quote_asset


def exchange_info(symbols_details: [], tickers: []) -> {}:
    symbols = []
    symbols_price = {}
    for pair in tickers:
        symbols_price[pair[0].replace(':', '').upper()[1:]] = pair[7]
    for market in symbols_details:
        if 'f0' not in market.get("pair"):
            _symbol, _base_asset, _quote_asset = symbol_name(market.get("pair"))
            _base_asset_precision = len(str(market.get('minimum_order_size'))) - 2
            # Filters var
            _price = symbols_price.get(_symbol, 0.0)
            _tick_size = tick_size(market.get('price_precision'), _price)
            _min_qty = float(market.get('minimum_order_size'))
            _max_qty = float(market.get('maximum_order_size'))
            _step_size = 0.00001
            _min_notional = _min_qty * _price

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

    _binance_res = {
        "timezone": "UTC",
        "serverTime": int(time.time() * 1000),
        "rateLimits": [],
        "exchangeFilters": [],
        "symbols": symbols,
    }
    return _binance_res


def account_information(res: []) -> {}:
    balances = []
    for balance in res:
        if balance[0] == 'exchange':
            total = str(balance[2] or 0.0)
            free = str(balance[4] or 0.0)
            locked = str(Decimal(total) - Decimal(free))
            _binance_res = {
                "asset": balance[1],
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


def order(res: [], response_type=None, wss_te=None) -> {}:
    # print(f"order.order: {res}")
    symbol = res[3][1:].replace(':', '')
    order_id = res[0]
    order_list_id = -1
    client_order_id = str(res[2]) or str()
    price = str(res[16] or 0.0)
    orig_qty = str(abs(res[7]) or 0.0)
    executed_qty = str(Decimal(orig_qty) - Decimal(str(abs(res[6]))))
    avg_fill_price = str(res[17] or 0.0)
    cummulative_quote_qty = str(Decimal(executed_qty) * Decimal(avg_fill_price))
    orig_quote_order_qty = str(Decimal(orig_qty) * Decimal(price))
    #
    if 'CANCELED' in res[13]:
        status = 'CANCELED'
    elif Decimal(orig_qty) > Decimal(executed_qty) > 0:
        status = 'PARTIALLY_FILLED'
    elif  Decimal(executed_qty) >= Decimal(orig_qty):
        status = 'FILLED'
    else:
        status = 'NEW'
    #
    _type = "LIMIT"
    # https://docs.bitfinex.com/reference/ws-auth-trades
    if wss_te:
        executed_qty = Decimal(str(0))
        cummulative_quote_qty = Decimal(str(0))
        trades_id = []
        for trade in wss_te:
            trade_id = trade[0]
            if trade_id not in trades_id:
                trades_id.append(trade_id)
                exec_amount = Decimal(str(abs(trade[4])))
                exec_price = Decimal(str(trade[5]))
                executed_qty += exec_amount
                cummulative_quote_qty += exec_amount * exec_price
        if executed_qty >= Decimal(orig_qty):
            status = 'FILLED'
        else:
            status = 'PARTIALLY_FILLED'
        executed_qty = str(executed_qty)
        cummulative_quote_qty = str(cummulative_quote_qty)
        _type = "MARKET"

    time_in_force = "GTC"
    side = 'BUY' if res[7] > 0 else 'SELL'
    stop_price = '0.0'
    iceberg_qty = '0.0'
    _time = res[4]
    update_time = res[5]
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


def orders(res: [], response_type=None) -> []:
    binance_orders = []
    for _order in res:
        i_order = order(_order, response_type=response_type)
        binance_orders.append(i_order)
    return binance_orders


def order_book(res: []) -> {}:
    binance_order_book = {"lastUpdateId": int(time.time() * 1000)}
    bids = []
    asks = []
    for i in res:
        if i[2] > 0:
            bids.append([str(i[0]), str(i[2])])
        else:
            asks.append([str(i[0]), str(abs(i[2]))])
    binance_order_book['bids'] = bids
    binance_order_book['asks'] = asks
    return binance_order_book


def ticker_price_change_statistics(res: [], symbol):
    binance_price_ticker = {
        "symbol": symbol,
        "priceChange": str(res[4]),
        "priceChangePercent": str(res[5]),
        "weightedAvgPrice": "0.0",
        "prevClosePrice": str(res[6] - res[4]),
        "lastPrice": str(res[6]),
        "lastQty": "0.0",
        "bidPrice": str(res[0]),
        "bidQty": "0.0",
        "askPrice": str(res[2]),
        "askQty": "0.00",
        "openPrice": str(res[6] - res[4]),
        "highPrice": str(res[8]),
        "lowPrice": str(res[9]),
        "volume": str(res[7]),
        "quoteVolume": "0.0",
        "openTime": int(time.time() * 1000) - 60 * 60 * 24,
        "closeTime": int(time.time() * 1000),
        "firstId": 0,
        "lastId": 1,
        "count": 1,
    }
    return binance_price_ticker


def fetch_symbol_price_ticker(res: [], symbol) -> {}:
    symbol_ticker = {
        "symbol": symbol,
        "price": str(res[6]),
    }
    return symbol_ticker


def interval(_interval: str) -> int:
    resolution = {
        '1m': 60,
        '5m': 5 * 60,
        '15m': 15 * 60,
        '30m': 30 * 60,
        '1h': 60 * 60,
        '3h': 3 * 60 * 60,
        '6h': 6 * 60 * 60,
        '12h': 12 * 60 * 60,
        '1D': 24 * 60 * 60,
        '1W': 7 * 24 * 60 * 60,
        '14D': 14 * 24 * 60 * 60,
        '1M': 31 * 24 * 60 * 60
    }
    return resolution.get(_interval, 0)


def klines(res: [], _interval: str) -> []:
    binance_klines = []
    for i in res:
        start_time = i[0]
        _candle = [
            start_time,
            str(i[1]),
            str(i[3]),
            str(i[4]),
            str(i[2]),
            str(i[5]),
            start_time + interval(_interval) * 1000 - 1,
            '0.0',
            0,
            '0.0',
            '0.0',
            '0.0',
        ]
        binance_klines.append(_candle)
    return binance_klines


def candle(res: [], symbol: str = None, ch_type: str = None) -> {}:
    symbol = symbol[1:].replace(':', '')
    start_time = res[0]
    _interval = ch_type.split('_')[1]
    binance_candle = {
        'stream': f"{symbol.lower()}@{ch_type.replace('candles', 'kline')}",
        'data': {'e': 'kline',
                 'E': int(time.time()),
                 's': symbol,
                 'k': {
                     't': start_time,
                     'T': start_time + interval(_interval) * 1000 - 1,
                     's': symbol,
                     'i': _interval,
                     'f': 100,
                     'L': 200,
                     'o': str(res[1]),
                     'c': str(res[2]),
                     'h': str(res[3]),
                     'l': str(res[4]),
                     'v': str(res[5]),
                     'n': 100,
                     'x': False,
                     'q': '0.0',
                     'V': '0.0',
                     'Q': '0.0',
                     'B': '0'}}
    }
    return binance_candle


def account_trade_list(res: []) -> []:
    binance_trade_list = []
    for trade in res:
        price = str(trade[5])
        qty = str(abs(trade[4]))
        quote_qty = str(Decimal(price) * Decimal(qty))
        binance_trade = {
            "symbol": trade[1][1:].replace(':', ''),
            "id": trade[0],
            "orderId": trade[3],
            "orderListId": -1,
            "price": price,
            "qty": qty,
            "quoteQty": quote_qty,
            "commission": str(abs(trade[9])),
            "commissionAsset": trade[10],
            "time": trade[2],
            "isBuyer": bool(trade[4] > 0),
            "isMaker": bool(trade[8] == 1),
            "isBestMatch": True,
        }
        binance_trade_list.append(binance_trade)
    return binance_trade_list


def ticker(res: [], symbol: str = None) -> {}:
    _symbol = symbol[1:].replace(':', '').lower()
    msg_binance = {
        'stream': f"{_symbol}@miniTicker",
        'data': {
            "e": "24hrMiniTicker",
            "E": int(time.time()),
            "s": _symbol.upper(),
            "c": str(res[6]),
            "o": str(res[6] - res[4]),
            "h": str(res[8]),
            "l": str(res[9]),
            "v": str(res[7]),
            "q": "0"
        }
    }
    return msg_binance


def on_funds_update(res: []) -> {}:
    binance_funds = {
        'e': 'outboundAccountPosition',
        'E': int(time.time() * 1000),
        'u': int(time.time() * 1000),
    }
    funds = []
    if not isinstance(res[0], list):
        res = [res]
    for i in res:
        if i[0] == 'exchange':
            total = str(i[2])
            free = str(i[4] or total)
            locked = str(Decimal(total) - Decimal(free))
            balance = {
                'a': i[1],
                'f': free,
                'l': locked
            }
            funds.append(balance)
    binance_funds['B'] = funds
    return binance_funds


def on_balance_update(res: []) -> {}:
    balance = {
        'e': 'balanceUpdate',
        'E': res[3],
        'a': res[1],
        'd': res[5],
        'T': int(time.time() * 1000)
    }
    return balance


def on_order_update(res: [], last_event: tuple) -> {}:
    # print(f"on_order_update.res: {res}")
    side = 'BUY' if res[7] > 0 else 'SELL'
    #
    order_quantity = str(abs(res[7]))
    cumulative_filled_quantity = str(Decimal(order_quantity) - Decimal(str(abs(res[6]))))
    cumulative_quote_asset = str(Decimal(cumulative_filled_quantity) * Decimal(str(res[17])))
    quote_order_qty = str(Decimal(order_quantity) * Decimal(str(res[16])))
    #
    trade_id = -1
    last_executed_quantity = "0"
    last_executed_price = "0"
    if last_event:
        trade_id = last_event[0]
        last_executed_quantity = last_event[1]
        last_executed_price = last_event[2]
    last_quote_asset_transacted = str(Decimal(last_executed_quantity) * Decimal(last_executed_price))
    if 'CANCELED' in res[13]:
        status = 'CANCELED'
    elif Decimal(order_quantity) > Decimal(cumulative_filled_quantity) > 0:
        status = 'PARTIALLY_FILLED'
    elif  Decimal(cumulative_filled_quantity) >= Decimal(order_quantity):
        status = 'FILLED'
    else:
        status = 'NEW'
    #
    msg_binance = {
        "e": "executionReport",
        "E": res[5],
        "s": res[3][1:].replace(':', ''),
        "c": str(res[2]),
        "S": side,
        "o": "LIMIT",
        "f": "GTC",
        "q": order_quantity,
        "p": str(res[16]),
        "P": "0.00000000",
        "F": "0.00000000",
        "g": -1,
        "C": "",
        "x": "TRADE",
        "X": status,
        "r": "NONE",
        "i": res[0],
        "l": last_executed_quantity,
        "z": cumulative_filled_quantity,
        "L": last_executed_price,
        "n": '0.0',
        "N": "NONE",
        "T": res[5],
        "t": trade_id,
        "I": 123456789,
        "w": True,
        "m": False,
        "M": False,
        "O": res[4],
        "Z": cumulative_quote_asset,
        "Y": last_quote_asset_transacted,
        "Q": quote_order_qty
    }
    return msg_binance


def on_order_trade(res: [], executed_qty: str) -> {}:
    # print(f"on_order_trade.res: {res}")
    side = 'BUY' if res[4] > 0 else 'SELL'
    #
    status = 'PARTIALLY_FILLED'
    #
    last_executed_quantity = str(abs(res[4]))
    last_executed_price = str(res[5])
    last_quote_asset = str(Decimal(last_executed_quantity) * Decimal(last_executed_price))
    msg_binance = {
        "e": "executionReport",
        "E": res[2],
        "s": res[1][1:].replace(':', ''),
        "c": str(res[11]),
        "S": side,
        "o": "LIMIT",
        "f": "GTC",
        "q": "0.0",
        "p": str(res[7]),
        "P": "0.00000000",
        "F": "0.00000000",
        "g": -1,
        "C": "NEW",
        "x": "TRADE",
        "X": status,
        "r": "NONE",
        "i": res[3],
        "l": last_executed_quantity,
        "z": executed_qty,
        "L": last_executed_price,
        "n": str(res[9]),
        "N": res[10],
        "T": res[2],
        "t": res[0],
        "I": 123456789,
        "w": True,
        "m": bool(res[8] == 1),
        "M": False,
        "O": res[2],
        "Z": "0.0",
        "Y": last_quote_asset,
        "Q": "0.0"
    }
    return msg_binance


def funding_wallet(res: []) -> []:
    balances = []
    for balance in res:
        if balance[0] in ('exchange', 'funding'):
            total = str(balance[2] or 0.0)
            free = str(balance[4] or 0.0)
            locked = str(Decimal(total) - Decimal(free))
            if float(total):
                _binance_res = {
                    "asset": balance[1],
                    "free": free,
                    "locked": locked,
                    "freeze": "0",
                    "withdrawing": "0",
                    "btcValuation": "0.0",
                }
                balances.append(_binance_res)

    return balances
