import toml
from decimal import Decimal

import exchanges_wrapper.martin as mr
from exchanges_wrapper import CONFIG_FILE

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


def get_account(account_name: str) -> dict:
    config = toml.load(str(CONFIG_FILE))
    accounts = config.get('accounts')

    for account in accounts:
        if account.get('name') == account_name:
            exchange = account['exchange']
            sub_account = account.get('sub_account_name')
            test_net = account['test_net']
            master_email = account.get('master_email')
            master_name = account.get('master_name')
            endpoint = config['endpoint'][exchange]

            ws_add_on = get_ws_add_on(endpoint, exchange)
            api_auth = get_api_auth(endpoint, exchange, test_net)
            api_public = endpoint['api_public']
            ws_public = get_ws_public(endpoint, exchange, test_net)
            ws_api, ws_auth = get_ws_api_auth(endpoint, exchange, test_net)

            if exchange == 'binance_us':
                exchange = 'binance'

            return {
                'exchange': exchange,
                'sub_account': sub_account,
                'test_net': test_net,
                'api_key': account['api_key'],
                'api_secret': account['api_secret'],
                'api_public': api_public,
                'ws_public': ws_public,
                'api_auth': api_auth,
                'ws_auth': ws_auth,
                'ws_add_on': ws_add_on,
                'passphrase': account.get('passphrase'),
                'master_email': master_email,
                'master_name': master_name,
                'two_fa': account.get('two_fa'),
                'ws_api': ws_api,
            }
    return {}

def get_ws_add_on(endpoint, exchange):
    if exchange == 'huobi':
        return endpoint.get('ws_public_mbr')
    elif exchange == 'okx':
        return endpoint.get('ws_business')
    return None

def get_api_auth(endpoint, exchange, test_net):
    if exchange == 'bitfinex':
        return endpoint['api_auth']
    return endpoint['api_test'] if test_net else endpoint['api_auth']

def get_ws_public(endpoint, exchange, test_net):
    return endpoint['ws_test_public'] if exchange == 'bybit' and test_net else endpoint['ws_public']

def get_ws_api_auth(endpoint, exchange, test_net):
    if exchange == 'bitfinex':
        ws_api = ws_auth = endpoint['ws_auth']
    else:
        ws_auth = endpoint['ws_test'] if test_net else endpoint['ws_auth']
        ws_api = endpoint.get('ws_api_test') if test_net else endpoint.get('ws_api')
        if exchange == 'okx':
            ws_api = ws_auth
    return ws_api, ws_auth
