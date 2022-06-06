# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

import api_pb2 as api__pb2


class MartinStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.OpenClientConnection = channel.unary_unary(
                '/martin.Martin/OpenClientConnection',
                request_serializer=api__pb2.OpenClientConnectionRequest.SerializeToString,
                response_deserializer=api__pb2.OpenClientConnectionId.FromString,
                )
        self.FetchServerTime = channel.unary_unary(
                '/martin.Martin/FetchServerTime',
                request_serializer=api__pb2.OpenClientConnectionId.SerializeToString,
                response_deserializer=api__pb2.FetchServerTimeResponse.FromString,
                )
        self.FetchOpenOrders = channel.unary_unary(
                '/martin.Martin/FetchOpenOrders',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchOpenOrdersResponse.FromString,
                )
        self.CancelAllOrders = channel.unary_unary(
                '/martin.Martin/CancelAllOrders',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchOpenOrdersResponse.FromString,
                )
        self.FetchExchangeInfoSymbol = channel.unary_unary(
                '/martin.Martin/FetchExchangeInfoSymbol',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchExchangeInfoSymbolResponse.FromString,
                )
        self.FetchAccountInformation = channel.unary_unary(
                '/martin.Martin/FetchAccountInformation',
                request_serializer=api__pb2.OpenClientConnectionId.SerializeToString,
                response_deserializer=api__pb2.FetchAccountBalanceResponse.FromString,
                )
        self.FetchOrderBook = channel.unary_unary(
                '/martin.Martin/FetchOrderBook',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchOrderBookResponse.FromString,
                )
        self.FetchSymbolPriceTicker = channel.unary_unary(
                '/martin.Martin/FetchSymbolPriceTicker',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchSymbolPriceTickerResponse.FromString,
                )
        self.FetchTickerPriceChangeStatistics = channel.unary_unary(
                '/martin.Martin/FetchTickerPriceChangeStatistics',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchTickerPriceChangeStatisticsResponse.FromString,
                )
        self.FetchKlines = channel.unary_unary(
                '/martin.Martin/FetchKlines',
                request_serializer=api__pb2.FetchKlinesRequest.SerializeToString,
                response_deserializer=api__pb2.FetchKlinesResponse.FromString,
                )
        self.FetchAccountTradeList = channel.unary_unary(
                '/martin.Martin/FetchAccountTradeList',
                request_serializer=api__pb2.AccountTradeListRequest.SerializeToString,
                response_deserializer=api__pb2.AccountTradeListResponse.FromString,
                )
        self.OnTickerUpdate = channel.unary_stream(
                '/martin.Martin/OnTickerUpdate',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.OnTickerUpdateResponse.FromString,
                )
        self.OnOrderBookUpdate = channel.unary_stream(
                '/martin.Martin/OnOrderBookUpdate',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.FetchOrderBookResponse.FromString,
                )
        self.StopStream = channel.unary_unary(
                '/martin.Martin/StopStream',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.SimpleResponse.FromString,
                )
        self.StartStream = channel.unary_unary(
                '/martin.Martin/StartStream',
                request_serializer=api__pb2.StartStreamRequest.SerializeToString,
                response_deserializer=api__pb2.SimpleResponse.FromString,
                )
        self.OnFundsUpdate = channel.unary_stream(
                '/martin.Martin/OnFundsUpdate',
                request_serializer=api__pb2.OnFundsUpdateRequest.SerializeToString,
                response_deserializer=api__pb2.OnFundsUpdateResponse.FromString,
                )
        self.OnOrderUpdate = channel.unary_stream(
                '/martin.Martin/OnOrderUpdate',
                request_serializer=api__pb2.MarketRequest.SerializeToString,
                response_deserializer=api__pb2.OnOrderUpdateResponse.FromString,
                )
        self.CreateLimitOrder = channel.unary_unary(
                '/martin.Martin/CreateLimitOrder',
                request_serializer=api__pb2.CreateLimitOrderRequest.SerializeToString,
                response_deserializer=api__pb2.CreateLimitOrderResponse.FromString,
                )
        self.CancelOrder = channel.unary_unary(
                '/martin.Martin/CancelOrder',
                request_serializer=api__pb2.CancelOrderRequest.SerializeToString,
                response_deserializer=api__pb2.CancelOrderResponse.FromString,
                )
        self.FetchOrder = channel.unary_unary(
                '/martin.Martin/FetchOrder',
                request_serializer=api__pb2.FetchOrderRequest.SerializeToString,
                response_deserializer=api__pb2.FetchOrderResponse.FromString,
                )
        self.ResetRateLimit = channel.unary_unary(
                '/martin.Martin/ResetRateLimit',
                request_serializer=api__pb2.OpenClientConnectionId.SerializeToString,
                response_deserializer=api__pb2.SimpleResponse.FromString,
                )
        self.OnKlinesUpdate = channel.unary_stream(
                '/martin.Martin/OnKlinesUpdate',
                request_serializer=api__pb2.FetchKlinesRequest.SerializeToString,
                response_deserializer=api__pb2.OnKlinesUpdateResponse.FromString,
                )
        self.FetchFundingWallet = channel.unary_unary(
                '/martin.Martin/FetchFundingWallet',
                request_serializer=api__pb2.FetchFundingWalletRequest.SerializeToString,
                response_deserializer=api__pb2.FetchFundingWalletResponse.FromString,
                )


class MartinServicer(object):
    """Missing associated documentation comment in .proto file."""

    def OpenClientConnection(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchServerTime(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchOpenOrders(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CancelAllOrders(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchExchangeInfoSymbol(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchAccountInformation(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchOrderBook(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchSymbolPriceTicker(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchTickerPriceChangeStatistics(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchKlines(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchAccountTradeList(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def OnTickerUpdate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def OnOrderBookUpdate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def StopStream(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def StartStream(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def OnFundsUpdate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def OnOrderUpdate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CreateLimitOrder(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CancelOrder(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchOrder(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ResetRateLimit(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def OnKlinesUpdate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchFundingWallet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_MartinServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'OpenClientConnection': grpc.unary_unary_rpc_method_handler(
                    servicer.OpenClientConnection,
                    request_deserializer=api__pb2.OpenClientConnectionRequest.FromString,
                    response_serializer=api__pb2.OpenClientConnectionId.SerializeToString,
            ),
            'FetchServerTime': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchServerTime,
                    request_deserializer=api__pb2.OpenClientConnectionId.FromString,
                    response_serializer=api__pb2.FetchServerTimeResponse.SerializeToString,
            ),
            'FetchOpenOrders': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchOpenOrders,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchOpenOrdersResponse.SerializeToString,
            ),
            'CancelAllOrders': grpc.unary_unary_rpc_method_handler(
                    servicer.CancelAllOrders,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchOpenOrdersResponse.SerializeToString,
            ),
            'FetchExchangeInfoSymbol': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchExchangeInfoSymbol,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchExchangeInfoSymbolResponse.SerializeToString,
            ),
            'FetchAccountInformation': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchAccountInformation,
                    request_deserializer=api__pb2.OpenClientConnectionId.FromString,
                    response_serializer=api__pb2.FetchAccountBalanceResponse.SerializeToString,
            ),
            'FetchOrderBook': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchOrderBook,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchOrderBookResponse.SerializeToString,
            ),
            'FetchSymbolPriceTicker': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchSymbolPriceTicker,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchSymbolPriceTickerResponse.SerializeToString,
            ),
            'FetchTickerPriceChangeStatistics': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchTickerPriceChangeStatistics,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchTickerPriceChangeStatisticsResponse.SerializeToString,
            ),
            'FetchKlines': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchKlines,
                    request_deserializer=api__pb2.FetchKlinesRequest.FromString,
                    response_serializer=api__pb2.FetchKlinesResponse.SerializeToString,
            ),
            'FetchAccountTradeList': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchAccountTradeList,
                    request_deserializer=api__pb2.AccountTradeListRequest.FromString,
                    response_serializer=api__pb2.AccountTradeListResponse.SerializeToString,
            ),
            'OnTickerUpdate': grpc.unary_stream_rpc_method_handler(
                    servicer.OnTickerUpdate,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.OnTickerUpdateResponse.SerializeToString,
            ),
            'OnOrderBookUpdate': grpc.unary_stream_rpc_method_handler(
                    servicer.OnOrderBookUpdate,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.FetchOrderBookResponse.SerializeToString,
            ),
            'StopStream': grpc.unary_unary_rpc_method_handler(
                    servicer.StopStream,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.SimpleResponse.SerializeToString,
            ),
            'StartStream': grpc.unary_unary_rpc_method_handler(
                    servicer.StartStream,
                    request_deserializer=api__pb2.StartStreamRequest.FromString,
                    response_serializer=api__pb2.SimpleResponse.SerializeToString,
            ),
            'OnFundsUpdate': grpc.unary_stream_rpc_method_handler(
                    servicer.OnFundsUpdate,
                    request_deserializer=api__pb2.OnFundsUpdateRequest.FromString,
                    response_serializer=api__pb2.OnFundsUpdateResponse.SerializeToString,
            ),
            'OnOrderUpdate': grpc.unary_stream_rpc_method_handler(
                    servicer.OnOrderUpdate,
                    request_deserializer=api__pb2.MarketRequest.FromString,
                    response_serializer=api__pb2.OnOrderUpdateResponse.SerializeToString,
            ),
            'CreateLimitOrder': grpc.unary_unary_rpc_method_handler(
                    servicer.CreateLimitOrder,
                    request_deserializer=api__pb2.CreateLimitOrderRequest.FromString,
                    response_serializer=api__pb2.CreateLimitOrderResponse.SerializeToString,
            ),
            'CancelOrder': grpc.unary_unary_rpc_method_handler(
                    servicer.CancelOrder,
                    request_deserializer=api__pb2.CancelOrderRequest.FromString,
                    response_serializer=api__pb2.CancelOrderResponse.SerializeToString,
            ),
            'FetchOrder': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchOrder,
                    request_deserializer=api__pb2.FetchOrderRequest.FromString,
                    response_serializer=api__pb2.FetchOrderResponse.SerializeToString,
            ),
            'ResetRateLimit': grpc.unary_unary_rpc_method_handler(
                    servicer.ResetRateLimit,
                    request_deserializer=api__pb2.OpenClientConnectionId.FromString,
                    response_serializer=api__pb2.SimpleResponse.SerializeToString,
            ),
            'OnKlinesUpdate': grpc.unary_stream_rpc_method_handler(
                    servicer.OnKlinesUpdate,
                    request_deserializer=api__pb2.FetchKlinesRequest.FromString,
                    response_serializer=api__pb2.OnKlinesUpdateResponse.SerializeToString,
            ),
            'FetchFundingWallet': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchFundingWallet,
                    request_deserializer=api__pb2.FetchFundingWalletRequest.FromString,
                    response_serializer=api__pb2.FetchFundingWalletResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'martin.Martin', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class Martin(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def OpenClientConnection(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/OpenClientConnection',
            api__pb2.OpenClientConnectionRequest.SerializeToString,
            api__pb2.OpenClientConnectionId.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchServerTime(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchServerTime',
            api__pb2.OpenClientConnectionId.SerializeToString,
            api__pb2.FetchServerTimeResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchOpenOrders(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchOpenOrders',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchOpenOrdersResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CancelAllOrders(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/CancelAllOrders',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchOpenOrdersResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchExchangeInfoSymbol(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchExchangeInfoSymbol',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchExchangeInfoSymbolResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchAccountInformation(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchAccountInformation',
            api__pb2.OpenClientConnectionId.SerializeToString,
            api__pb2.FetchAccountBalanceResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchOrderBook(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchOrderBook',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchOrderBookResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchSymbolPriceTicker(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchSymbolPriceTicker',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchSymbolPriceTickerResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchTickerPriceChangeStatistics(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchTickerPriceChangeStatistics',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchTickerPriceChangeStatisticsResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchKlines(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchKlines',
            api__pb2.FetchKlinesRequest.SerializeToString,
            api__pb2.FetchKlinesResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchAccountTradeList(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchAccountTradeList',
            api__pb2.AccountTradeListRequest.SerializeToString,
            api__pb2.AccountTradeListResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def OnTickerUpdate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/martin.Martin/OnTickerUpdate',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.OnTickerUpdateResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def OnOrderBookUpdate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/martin.Martin/OnOrderBookUpdate',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.FetchOrderBookResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def StopStream(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/StopStream',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.SimpleResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def StartStream(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/StartStream',
            api__pb2.StartStreamRequest.SerializeToString,
            api__pb2.SimpleResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def OnFundsUpdate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/martin.Martin/OnFundsUpdate',
            api__pb2.OnFundsUpdateRequest.SerializeToString,
            api__pb2.OnFundsUpdateResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def OnOrderUpdate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/martin.Martin/OnOrderUpdate',
            api__pb2.MarketRequest.SerializeToString,
            api__pb2.OnOrderUpdateResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CreateLimitOrder(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/CreateLimitOrder',
            api__pb2.CreateLimitOrderRequest.SerializeToString,
            api__pb2.CreateLimitOrderResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CancelOrder(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/CancelOrder',
            api__pb2.CancelOrderRequest.SerializeToString,
            api__pb2.CancelOrderResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchOrder(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchOrder',
            api__pb2.FetchOrderRequest.SerializeToString,
            api__pb2.FetchOrderResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def ResetRateLimit(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/ResetRateLimit',
            api__pb2.OpenClientConnectionId.SerializeToString,
            api__pb2.SimpleResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def OnKlinesUpdate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/martin.Martin/OnKlinesUpdate',
            api__pb2.FetchKlinesRequest.SerializeToString,
            api__pb2.OnKlinesUpdateResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def FetchFundingWallet(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/martin.Martin/FetchFundingWallet',
            api__pb2.FetchFundingWalletRequest.SerializeToString,
            api__pb2.FetchFundingWalletResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)