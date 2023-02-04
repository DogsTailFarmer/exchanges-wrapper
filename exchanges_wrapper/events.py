import asyncio
import functools
from collections import defaultdict
import logging

from exchanges_wrapper.errors import UnknownEventType

logger = logging.getLogger('exch_srv_logger')


# based on: https://stackoverflow.com/a/2022629/10144963
class Handlers(list):
    async def __call__(self, *args, **kwargs):
        loop = asyncio.get_running_loop()
        trade_id = kwargs.pop('trade_id', None)
        _trade_id = None
        for func in self:
            try:
                _trade_id = func.args[2]
            except Exception as ex:  # skipcq: PYL-W0703
                logger.warning(f"Handlers error when try get trade_id: {ex}")
            if trade_id is None or trade_id == _trade_id:
                if asyncio.iscoroutinefunction(func):
                    await func(*args, **kwargs)
                    continue
                if kwargs:
                    func = functools.partial(func, **kwargs)
                loop.run_in_executor(None, func, *args)

    def __repr__(self):
        return f"Handlers({list.__repr__(self)})"


class Events:
    def __init__(self):
        self.handlers = defaultdict(Handlers)
        self.registered_streams = defaultdict(lambda: defaultdict(set))

    def register_user_event(self, listener, event_type):
        self.handlers[event_type].append(listener)

    def register_event(self, listener, event_type, exchange, trade_id):
        logger.info(f"register: event_type: {event_type}, exchange: {exchange}")
        self.registered_streams[exchange][trade_id] |= {event_type}
        if exchange == 'bitfinex':
            event_type = f"{event_type.split('@')[0][1:].replace(':', '').lower()}@{event_type.split('@')[1]}"
        elif exchange == 'okx':
            event_type = f"{event_type.split('@')[0].replace('-', '').lower()}@{event_type.split('@')[1]}"
        self.handlers[event_type].append(listener)
        logger.debug(f"register_event: registered_streams{self.registered_streams}")

    def unregister(self, exchange, trade_id):
        logger.info(f"Unregister events for {trade_id}")
        _event_types = self.handlers.keys()
        unregistered_event_types = []
        for _event_type in _event_types:
            _handlers = self.handlers.get(_event_type, [])
            _handlers[:] = [i for i in _handlers if i.args[2] != trade_id]
            if _handlers:
                self.handlers.update({_event_type: _handlers})
            else:
                unregistered_event_types.append(_event_type)
        for _event_type in unregistered_event_types:
            self.handlers.pop(_event_type, None)
        self.registered_streams.get(exchange, {}).pop(trade_id, None)

    def wrap_event(self, event_data):
        # print(f"wrap_event.event_data: {event_data}")
        wrapper_by_type = {
            "outboundAccountPosition": OutboundAccountPositionWrapper,
            "balanceUpdate": BalanceUpdateWrapper,
            "executionReport": OrderUpdateWrapper,
            "listStatus": ListStatus,
            "aggTrade": AggregateTradeWrapper,
            "trade": TradeWrapper,
            "kline": KlineWrapper,
            "24hrMiniTicker": SymbolMiniTickerWrapper,
            "24hrTicker": SymbolTickerWrapper,
            "bookTicker": SymbolBookTickerWrapper,
            "depth5": PartialBookDepthWrapper,
            "depth10": PartialBookDepthWrapper,
            "depth20": PartialBookDepthWrapper,
            "depth": DiffDepthWrapper,
        }

        stream = event_data["stream"] if "stream" in event_data else False
        event_type = event_data["e"] if "e" in event_data else stream
        if "@" in event_type:  # lgtm [py/member-test-non-container]
            event_type = event_type.split("@")[1]
        if event_type.startswith("kline_"):
            event_type = "kline"
        if event_type not in wrapper_by_type:
            raise UnknownEventType()
        wrapper = wrapper_by_type[event_type]
        return wrapper(event_data, self.handlers[stream if stream else event_type])


class EventWrapper:
    def __init__(self, _event_data, handlers):
        self.handlers = handlers

    async def fire(self, trade_id=None):
        if self.handlers:
            await self.handlers(self, trade_id=trade_id)


# MARKET EVENTS


class AggregateTradeWrapper(EventWrapper):
    def __init__(self, event_data, handlers):  # lgtm [py/similar-function]
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.aggregated_trade_id = event_data["a"]
        self.price = event_data["p"]
        self.quantity = event_data["q"]
        self.first_trade_id = event_data["f"]
        self.last_trade_id = event_data["l"]
        self.trade_time = event_data["T"]
        self.buyer_is_marker = event_data["m"]
        self.ignore = event_data["M"]


class TradeWrapper(EventWrapper):
    def __init__(self, event_data, handlers):  # lgtm [py/similar-function]
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.trade_id = event_data["t"]
        self.price = event_data["p"]
        self.quantity = event_data["q"]
        self.buyer_order_id = event_data["b"]
        self.seller_order_id = event_data["a"]
        self.trade_time = event_data["T"]
        self.buyer_is_marker = event_data["m"]
        self.ignore = event_data["M"]


class KlineWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        kline = event_data["k"]
        self.kline_start_time = kline["t"]
        self.kline_close_time = kline["T"]
        self.kline_symbol = kline["s"]
        self.kline_interval = kline["i"]
        self.kline_first_trade_id = kline["f"]
        self.kline_last_trade_id = kline["L"]
        self.kline_open_price = kline["o"]
        self.kline_close_price = kline["c"]
        self.kline_high_price = kline["h"]
        self.kline_low_price = kline["l"]
        self.kline_base_asset_volume = kline["v"]
        self.kline_trades_number = kline["n"]
        self.kline_closed = kline["x"]
        self.kline_quote_asset_volume = kline["q"]
        self.kline_taker_buy_base_asset_volume = kline["V"]
        self.kline_taker_buy_quote_asset_volume = kline["Q"]
        self.kline_ignore = kline["B"]


class SymbolMiniTickerWrapper(EventWrapper):
    def __init__(self, event_data, handlers):  # lgtm [py/similar-function]
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.close_price = event_data["c"]
        self.open_price = event_data["o"]
        self.high_price = event_data["h"]
        self.low_price = event_data["l"]
        self.total_traded_base_asset_volume = event_data["v"]
        self.total_traded_quote_asset_volume = event_data["q"]


class SymbolTickerWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.price_change = event_data["p"]
        self.price_change_percent = event_data["P"]
        self.weighted_average_price = event_data["w"]
        self.first_trade_before_window = event_data["x"]
        self.last_price = event_data["c"]
        self.last_quantity = event_data["Q"]
        self.best_bid_price = event_data["b"]
        self.best_bid_quantity = event_data["B"]
        self.best_ask_price = event_data["a"]
        self.best_ask_quantity = event_data["A"]
        self.open_price = event_data["o"]
        self.high_price = event_data["h"]
        self.low_price = event_data["l"]
        self.total_traded_base_asset_volume = event_data["v"]
        self.total_traded_quote_asset_volume = event_data["q"]
        self.statistics_open_time = event_data["O"]
        self.statistics_close_time = event_data["C"]
        self.first_trade_id = event_data["F"]
        self.last_trade_id = event_data["L"]
        self.total_trade_numbers = event_data["n"]


class SymbolBookTickerWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.order_book_updated = event_data["u"]
        self.symbol = event_data["s"]
        self.best_bid_price = event_data["b"]
        self.best_bid_quantity = event_data["B"]
        self.best_ask_price = event_data["a"]
        self.best_ask_quantity = event_data["A"]


class PartialBookDepthWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.last_update_id = event_data["lastUpdateId"]
        self.bids = event_data["bids"]
        self.asks = event_data["asks"]


class DiffDepthWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_type = event_data["e"]
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.first_update_id = event_data["U"]
        self.final_update_id = event_data["u"]
        self.bids = event_data["b"]
        self.asks = event_data["a"]


# ACCOUNT UPDATE


class OutboundAccountPositionWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_time = event_data["E"]
        self.last_update = event_data["u"]
        self.balances = dict(
            map(lambda x: (x["a"], {"free": x["f"], "locked": x["l"]}), event_data["B"])
        )


# BALANCE UPDATE


class BalanceUpdateWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_time = event_data["E"]
        self.asset = event_data["a"]
        self.balance_delta = event_data["d"]
        self.clear_time = event_data["T"]


# ORDER UPDATE


class OrderUpdateWrapper(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.client_order_id = event_data["c"]
        self.side = event_data["S"]
        self.order_type = event_data["o"]
        self.time_in_force = event_data["f"]
        self.order_quantity = event_data["q"]
        self.order_price = event_data["p"]
        self.stop_price = event_data["P"]
        self.iceberg_quantity = event_data["F"]
        self.order_list_id = event_data["g"]
        self.original_client_id = event_data["C"]
        self.execution_type = event_data["x"]
        self.order_status = event_data["X"]
        self.order_reject_reason = event_data["r"]
        self.order_id = event_data["i"]
        self.last_executed_quantity = event_data["l"]
        self.cumulative_filled_quantity = event_data["z"]
        self.last_executed_price = event_data["L"]
        self.commission_amount = event_data["n"]
        self.commission_asset = event_data["N"]
        self.transaction_time = event_data["T"]
        self.trade_id = event_data["t"]
        self.ignore_a = event_data["I"]
        self.in_order_book = event_data["w"]
        self.is_maker_side = event_data["m"]
        self.ignore_b = event_data["M"]
        self.order_creation_time = event_data["O"]
        self.quote_asset_transacted = event_data["Z"]
        self.last_quote_asset_transacted = event_data["Y"]
        self.quote_order_quantity = event_data["Q"]


class ListStatus(EventWrapper):
    def __init__(self, event_data, handlers):
        super().__init__(event_data, handlers)
        self.event_time = event_data["E"]
        self.symbol = event_data["s"]
        self.order_list_id = event_data["g"]
        self.contingency_type = event_data["c"]
        self.list_status_type = event_data["l"]
        self.list_order_status = event_data["L"]
        self.list_reject_reason = event_data["r"]
        self.list_client_order_id = event_data["C"]
        # noinspection PyArgumentList
        self.orders = dict(
            map(lambda x: (x["s"], {"orderId": x["i"], "clientOrderId": x["c"]})),
            event_data["O"],
        )
