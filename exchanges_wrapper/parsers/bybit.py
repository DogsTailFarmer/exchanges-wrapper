"""
Parser for convert Bybit REST API/WSS V5 response to Binance like result
"""
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class OrderBook:
    def __init__(self, snapshot) -> None:
        self.symbol = snapshot["s"].lower()
        self.last_update_id = snapshot["seq"]
        self.asks = {i[0]: i[1] for i in snapshot["a"]}
        self.bids = {i[0]: i[1] for i in snapshot["b"]}

    # noinspection PyTypeChecker
    def get_book(self) -> dict:
        return {
            'stream': f"{self.symbol}@depth5",
            'data': {
                'lastUpdateId': self.last_update_id,
                'bids': list(map(list, self.bids.items()))[:5],
                'asks': list(map(list, self.asks.items()))[:5],
            },
        }

    def update_book(self, delta):
        self.last_update_id = delta["seq"]
        for i in delta["a"]:
            if Decimal(i[1]):
                self.asks[i[0]] = i[1]
            else:
                self.asks.pop(i[0], None)

        if len(delta["a"]) > 1:
            self.asks = dict(sorted(self.asks.items(), key=lambda x: float(x[0]), reverse=False))

        for i in delta["b"]:
            if Decimal(i[1]):
                self.bids[i[0]] = i[1]
            else:
                self.bids.pop(i[0], None)

        if len(delta["b"]) > 1:
            self.bids = dict(sorted(self.bids.items(), key=lambda x: float(x[0]), reverse=True))

    # def __call__(self):
        # return self


def fetch_server_time(res: dict) -> dict:
    return {'serverTime': int(res['timeNano']) // 1000000}


def exchange_info(server_time: int, trading_symbol: list) -> dict:
    symbols = []

    for market in trading_symbol:

        _price_filter = {
            "filterType": "PRICE_FILTER",
            "minPrice": market['priceFilter']['tickSize'],
            "maxPrice": '1000000',
            "tickSize": market['priceFilter']['tickSize']
        }
        _lot_size = {
            "filterType": "LOT_SIZE",
            "minQty": market['lotSizeFilter']['minOrderQty'],
            "maxQty": market['lotSizeFilter']['maxOrderQty'],
            "stepSize": market['lotSizeFilter']['basePrecision']
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
            "avgPriceMins": 0
        }

        symbol = {
            "symbol": market['symbol'],
            "status": "TRADING",
            "baseAsset": market['baseCoin'],
            "baseAssetPrecision": len(market['lotSizeFilter']['basePrecision']) - 2,
            "quoteAsset": market['quoteCoin'],
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
        'Cancelled': 'CANCELED',
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


def order_book(res: dict) -> dict:
    return {"lastUpdateId": res['u'],
            "bids": res['b'],
            "asks": res['a'],
            }


def ticker_price_change_statistics(res: dict, ts: int) -> dict:
    return {
        "symbol": res["symbol"],
        "priceChange": str(Decimal(res["lastPrice"]) - Decimal(res["prevPrice24h"])),
        "priceChangePercent": res["price24hPcnt"],
        "weightedAvgPrice": str(Decimal(res["turnover24h"]) / Decimal(res["volume24h"])),
        "prevClosePrice": res["prevPrice24h"],
        "lastPrice": res["lastPrice"],
        "lastQty": "0.0",
        "bidPrice": res["bid1Price"],
        "bidQty": res["bid1Size"],
        "askPrice": res["ask1Price"],
        "askQty": res["ask1Size"],
        "openPrice": res["prevPrice24h"],
        "highPrice": res["highPrice24h"],
        "lowPrice": res["lowPrice24h"],
        "volume": res["volume24h"],
        "quoteVolume": res["turnover24h"],
        "openTime": ts,
        "closeTime": ts - 60 * 60 * 24,
        "firstId": 0,
        "lastId": 1,
        "count": 1,
    }


def account_information(res: list, ts: int) -> dict:
    balances = []
    for asset in res:
        locked = asset["locked"]
        free = str(Decimal(asset.get("walletBalance")) - Decimal(locked))
        balances.append({
            "asset": asset["coin"],
            "free": free,
            "locked": locked,
        })
    return {
        "makerCommission": 0,
        "takerCommission": 0,
        "buyerCommission": 0,
        "sellerCommission": 0,
        "canTrade": True,
        "canWithdraw": False,
        "canDeposit": False,
        "brokered": False,
        "updateTime": ts,
        "accountType": "SPOT",
        "balances": balances,
        "permissions": ["SPOT"],
    }


def ticker(res: dict) -> dict:
    symbol = res.get('symbol')
    return {
        'stream': f"{symbol.lower()}@miniTicker",
        'data': {
            "e": "24hrMiniTicker",
            "E": res.get('ts'),
            "s": symbol,
            "c": res.get('lastPrice'),
            "o": res.get('prevPrice24h'),
            "h": res.get('highPrice24h'),
            "l": res.get('lowPrice24h'),
            "v": res.get('volume24h'),
            "q": res.get('turnover24h'),
        },
    }


def interval(_interval: str) -> str:
    resolution = {
        '1m': '1',
        '3m': '3',
        '5m': '5',
        '15m': '15',
        '30m': '30',
        '1h': '60',
        '2h': '120',
        '4h': '240',
        '1d': 'D',
        '1w': 'W',
        '1M': 'M'
    }
    return resolution.get(_interval, 0)


def klines(res: list, _interval: str) -> list:
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
        '1': 60,
        '3': 60 * 3,
        '5': 60 * 5,
        '15': 60 * 15,
        '30': 60 * 30,
        '120': 60 * 60,
        '240': 60 * 60 * 2,
        'D': 60 * 60 * 24,
        'W': 60 * 60 * 24 * 7,
        'M': 60 * 60 * 24 * 31
    }
    return resolution.get(_interval, 0)


def candle(res: dict, symbol: str = None, ch_type: str = None) -> dict:
    symbol = symbol.lower()
    return {
        'stream': f"{symbol}@{ch_type}",
        'data': {
            'e': 'kline',
            'E': res["timestamp"],
            's': symbol,
            'k': {
                't': res["start"],
                'T': res["end"],
                's': symbol,
                'i': ch_type.replace('kline_', ''),
                'f': 100,
                'L': 200,
                'o': res["open"],
                'c': res["close"],
                'h': res["high"],
                'l': res["low"],
                'v': res["volume"],
                'n': 100,
                'x': res["confirm"],
                'q': res["turnover"],
                'V': '0.0',
                'Q': '0.0',
                'B': '0',
            },
        },
    }


def place_order_response(res: dict, req: dict) -> dict:
    return {
        "symbol": req["symbol"],
        "orderId": int(res["orderId"]),
        "orderListId": -1,
        "clientOrderId": res["orderLinkId"],
        "transactTime": res["ts"],
        "price": req["price"],
        "origQty": req["qty"],
        "executedQty": "0",
        "cummulativeQuoteQty": "0",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": req["orderType"].upper(),
        "side": req["side"].upper(),
    }


def on_trade_update(res: dict) -> dict:
    order_quantity = Decimal(res.get("orderQty", res.get("qty")))
    order_price = Decimal(res.get("orderPrice", res.get("price")))
    quote_order_qty = str(order_quantity * order_price)

    leaves_qty = Decimal(res["leavesQty"])
    cumulative_filled_quantity = res.get("cumExecQty", str(order_quantity - leaves_qty))
    cumulative_quote_asset = res.get("cumExecValue", str(Decimal(cumulative_filled_quantity) * order_price))

    last_executed_quantity = res.get("execQty", cumulative_filled_quantity)
    last_executed_price = res.get("execPrice", res.get("avgPrice"))
    last_quote_asset_transacted = res.get("execValue", cumulative_quote_asset)

    if leaves_qty == order_quantity:
        status = 'NEW'
    elif leaves_qty > 0:
        status = 'PARTIALLY_FILLED'
    else:
        status = 'FILLED'

    return {
        "e": "executionReport",
        "E": int(res.get("execTime", res.get("updatedTime"))),
        "s": res["symbol"],
        "c": res["orderLinkId"],
        "S": res["side"].upper(),
        "o": res["orderType"].upper(),
        "f": "GTC",
        "q": str(order_quantity),
        "p": str(order_price),
        "P": "0.00000000",
        "F": "0.00000000",
        "g": -1,
        "C": "",
        "x": "TRADE",
        "X": status,
        "r": "NONE",
        "i": int(res["orderId"]),
        "l": last_executed_quantity,
        "z": cumulative_filled_quantity,
        "L": last_executed_price,
        "n": res.get("execFee", res.get("cumExecFee")),
        "N": res.get("feeCurrency", ""),
        "T": int(res.get("execTime", res.get("updatedTime"))),
        "t": int(res.get("execId", -1)),
        "I": 123456789,
        "w": True,
        "m": res.get("isMaker", False),
        "M": False,
        "O": int(res.get("execTime", res.get("createdTime"))),
        "Z": cumulative_quote_asset,
        "Y": last_quote_asset_transacted,
        "Q": quote_order_qty,
    }


def on_funds_update(res: dict) -> dict:
    event_time = res["creationTime"]
    data = res["coin"]
    funds = []
    for currency in data:
        balance = {
            'a': currency["coin"],
            'f': currency["availableToWithdraw"],
            'l': currency["locked"],
        }
        funds.append(balance)
    return {
        'e': 'outboundAccountPosition',
        'E': event_time,
        'u': event_time,
        'B': funds,
    }


def on_balance_update(data_in: list, ts: str, symbol: str, mode: str, uid=None) -> list:
    data_out = []
    if mode == 'internal':
        for i in data_in:
            if i['coin'] in symbol and 'UNIFIED' in (i['fromAccountType'], i['toAccountType']):
                data_out.append(
                    {
                        i['transferId']: {
                            'e': 'balanceUpdate',
                            'E': i['timestamp'],
                            'a': i['coin'],
                            'd': i['amount'] if i['toAccountType'] == 'UNIFIED' else '-'+i['amount'],
                            'T': ts,
                        }
                    }
                )
    elif mode == 'universal':
        for i in data_in:
            if i['coin'] in symbol and \
                    ((i['fromAccountType'] == 'UNIFIED' and i['fromMemberId'] == str(uid))
                     or (i['toAccountType'] == 'UNIFIED' and i['toMemberId'] == str(uid))):
                data_out.append(
                    {
                        i['transferId']: {
                            'e': 'balanceUpdate',
                            'E': i['timestamp'],
                            'a': i['coin'],
                            'd': i['amount'] if int(i['toMemberId']) == uid else '-'+i['amount'],
                            'T': ts,
                        }
                    }
                )
    elif mode == 'log':
        for i in data_in:
            if i['currency'] in symbol:
                data_out.append(
                    {
                        i['id']: {
                            'e': 'balanceUpdate',
                            'E': i['transactionTime'],
                            'a': i['currency'],
                            'd': i['cashFlow'],
                            'T': ts,
                        }
                    }
                )
    return data_out


def funding_wallet(res: []) -> []:
    balances = []
    for balance in res:
        _free = Decimal(balance["transferBalance"])
        _wallet = Decimal(balance["walletBalance"])
        _binance_res = {
            "asset": balance["coin"],
            "free": str(_free),
            "locked": "0",
            "freeze": str(_wallet - _free),
            "withdrawing": "0",
            "btcValuation": "0.0",
        }
        if _free or _wallet:
            balances.append(_binance_res)
    return balances


def order_trade_list(res: []) -> []:
    trades = []
    for trade in reversed(res):
        trades.append(
            {
                "symbol": trade['symbol'],
                "id": int(trade['execId']),
                "orderId": int(trade['orderId']),
                "orderListId": -1,
                "price": trade['execPrice'],
                "qty": trade['execQty'],
                "quoteQty": trade['execValue'],
                "commission": trade['execFee'],
                "commissionAsset": trade['feeCurrency'],
                "time": int(trade['execTime']),
                "isBuyer": trade['side'] == 'Buy',
                "isMaker": trade['isMaker'],
                "isBestMatch": True
            }
        )
    return trades
