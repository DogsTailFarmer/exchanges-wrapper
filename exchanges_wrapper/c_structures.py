import hmac
import hashlib
import base64


class OrderUpdateEvent:
    def __init__(self, event_data: {}):
        self.symbol = event_data["symbol"]
        self.client_order_id = event_data["clientOrderId"]
        self.side = event_data["side"]
        self.order_type = event_data["type"]
        self.time_in_force = event_data["timeInForce"]
        self.order_quantity = event_data["origQty"]
        self.order_price = event_data["price"]
        self.stop_price = event_data["stopPrice"]
        self.iceberg_quantity = event_data["icebergQty"]
        self.order_list_id = event_data["orderListId"]
        self.original_client_id = event_data["clientOrderId"]
        self.execution_type = "TRADE"
        self.order_status = event_data["status"]
        self.order_reject_reason = "NONE"
        self.order_id = event_data["orderId"]
        self.last_executed_quantity = "0.0"
        self.cumulative_filled_quantity = event_data["executedQty"]
        self.last_executed_price = "0.0"
        self.commission_amount = "0.0"
        self.commission_asset = ""
        self.transaction_time = event_data["updateTime"]
        self.trade_id = -1
        self.ignore_a = int()
        self.in_order_book = True
        self.is_maker_side = False
        self.ignore_b = False
        self.order_creation_time = event_data["time"]
        self.quote_asset_transacted = event_data["cummulativeQuoteQty"]
        self.last_quote_asset_transacted = "0.0"
        self.quote_order_quantity = event_data["origQuoteOrderQty"]


class OrderTradesEvent:
    def __init__(self, event_data: {}):
        self.symbol = event_data["symbol"]
        self.client_order_id = ""
        self.side = "BUY" if event_data["isBuyer"] else "SELL"
        self.order_type = "LIMIT"
        self.time_in_force = "GTC"
        self.order_quantity = "0"
        self.order_price = "0"
        self.stop_price = "0"
        self.iceberg_quantity = "0"
        self.order_list_id = -1
        self.original_client_id = ""
        self.execution_type = "TRADE"
        self.order_status = "PARTIALLY_FILLED"
        self.order_reject_reason = "NONE"
        self.order_id = event_data["orderId"]
        self.last_executed_quantity = event_data["qty"]
        self.cumulative_filled_quantity = "0"
        self.last_executed_price = event_data["price"]
        self.commission_amount = event_data["commission"]
        self.commission_asset = event_data["commissionAsset"]
        self.transaction_time = event_data["time"]
        self.trade_id = event_data["id"]
        self.ignore_a = int()
        self.in_order_book = True
        self.is_maker_side = False
        self.ignore_b = False
        self.order_creation_time = event_data["time"]
        self.quote_asset_transacted = "0"
        self.last_quote_asset_transacted = event_data["quoteQty"]
        self.quote_order_quantity = "0"


def generate_signature(exchange, api_secret, data):
    if exchange == 'bitfinex':
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha384).hexdigest()
    elif exchange in ('huobi', 'okx'):
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
        sig = base64.b64encode(sig).decode()
    else:
        sig = hmac.new(api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig


def order(res: {}, response_type=None) -> {}:
    if response_type:
        binance_order = {
            "symbol": res.get('symbol'),
            "origClientOrderId": res.get('origClientOrderId'),
            "orderId": res.get('orderId'),
            "orderListId": res.get('orderListId'),
            "clientOrderId": res.get('clientOrderId'),
            "transactTime": res.get('time'),
            "price": res.get('price'),
            "origQty": res.get('origQty'),
            "executedQty": res.get('executedQty'),
            "cummulativeQuoteQty": res.get('cummulativeQuoteQty'),
            "status": res.get('status'),
            "timeInForce": res.get('timeInForce'),
            "type": res.get('type'),
            "side": res.get('side'),
        }
    elif response_type is None:
        binance_order = {
            "symbol": res.get('symbol'),
            "orderId": res.get('orderId'),
            "orderListId": res.get('orderListId'),
            "clientOrderId": res.get('clientOrderId'),
            "price": res.get('price'),
            "origQty": res.get('origQty'),
            "executedQty": res.get('executedQty'),
            "cummulativeQuoteQty": res.get('cummulativeQuoteQty'),
            "status": res.get('status'),
            "timeInForce": res.get('timeInForce'),
            "type": res.get('type'),
            "side": res.get('side'),
            "stopPrice": res.get('stopPrice'),
            "icebergQty": res.get('icebergQty'),
            "time": res.get('time'),
            "updateTime": res.get('updateTime'),
            "isWorking": res.get('isWorking'),
            "origQuoteOrderQty": res.get('origQuoteOrderQty'),
        }
    else:
        binance_order = {
            "symbol": res.get('symbol'),
            "orderId": res.get('orderId'),
            "orderListId": res.get('orderListId'),
            "clientOrderId": res.get('clientOrderId'),
            "price": res.get('price'),
            "origQty": res.get('origQty'),
            "executedQty": res.get('executedQty'),
            "cummulativeQuoteQty": res.get('cummulativeQuoteQty'),
            "status": res.get('status'),
            "timeInForce": res.get('timeInForce'),
            "type": res.get('type'),
            "side": res.get('side'),
        }
    # print(f"order.binance_order: {binance_order}")
    return binance_order
