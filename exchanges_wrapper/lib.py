from decimal import Decimal
import exchanges_wrapper.martin as mr

REST_RATE_LIMIT_INTERVAL = {
    "bitfinex": {
        "default": 0.6667,  # 90 requests per minute
    },
}

FILTER_TYPE_MAP = {
    'PRICE_FILTER': mr.FetchExchangeInfoSymbolResponseFiltersPriceFilter,
    'PERCENT_PRICE': mr.FetchExchangeInfoSymbolResponseFiltersPercentPrice,
    'LOT_SIZE': mr.FetchExchangeInfoSymbolResponseFiltersLotSize,
    'MIN_NOTIONAL': mr.FetchExchangeInfoSymbolResponseFiltersMinNotional,
    'NOTIONAL': mr.FetchExchangeInfoSymbolResponseFiltersNotional,
    'ICEBERG_PARTS': mr.FetchExchangeInfoSymbolResponseFiltersIcebergParts,
    'MARKET_LOT_SIZE': mr.FetchExchangeInfoSymbolResponseFiltersMarketLotSize,
    'MAX_NUM_ORDERS': mr.FetchExchangeInfoSymbolResponseFiltersMaxNumOrders,
    'MAX_NUM_ICEBERG_ORDERS': mr.FetchExchangeInfoSymbolResponseFiltersMaxNumIcebergOrders,
    'MAX_POSITION': mr.FetchExchangeInfoSymbolResponseFiltersMaxPosition,
}


class OrderTradesEvent:
    def __init__(self, event_data: {}):
        self.symbol = event_data["symbol"]
        self.client_order_id = event_data["clientOrderId"]
        self.side = "BUY" if event_data["isBuyer"] else "SELL"
        self.order_type = "LIMIT"
        self.time_in_force = "GTC"
        self.order_quantity = event_data["origQty"]
        self.order_price = event_data["orderPrice"]
        self.stop_price = "0"
        self.iceberg_quantity = "0"
        self.order_list_id = -1
        self.original_client_id = ""
        self.execution_type = "TRADE"
        self.order_reject_reason = "NONE"
        self.order_id = event_data["orderId"]
        self.last_executed_quantity = event_data["qty"]
        self.cumulative_filled_quantity = event_data["executedQty"]
        self.order_status = event_data["status"]
        self.last_executed_price = event_data["price"]
        self.commission_amount = event_data["commission"]
        self.commission_asset = event_data["commissionAsset"]
        self.transaction_time = event_data["updateTime"]
        self.trade_id = event_data["id"]
        self.ignore_a = int()
        self.in_order_book = True
        self.is_maker_side = event_data["isMaker"]
        self.ignore_b = False
        self.order_creation_time = event_data["time"]
        self.quote_asset_transacted = event_data["cummulativeQuoteQty"]
        self.last_quote_asset_transacted = event_data["quoteQty"]
        self.quote_order_quantity = str(Decimal(self.order_quantity) * Decimal(self.order_price))
