## 2.1.21 2024-11-xx
### Update
* structure optimization
* Dependency: bump requirements

## 2.1.20 2024-09-14
### Fix
* Downgraded `betterproto` to `2.0.0b6`

## 2.1.19 2024-09-13
### Fix
* `pyproject.toml`

## 2.1.18 2024-09-13
### Fix
* Dependency conflict

## 2.1.17 2024-09-13
### Update
* Dependency: Up requirements for crypto-ws-api==2.0.13

## 2.1.16 2024-09-13
### Fix
* `OKX`: get_exchange_info: <class 'decimal.ConversionSyntax'> [#82](https://github.com/DogsTailFarmer/martin-binance/issues/82#issue-2467548368)

### Update
* `HTX`: monitoring PING interval from server for each WSS channel and restart if timing out
* Dependency

## 2.1.15 2024-07-12
### Added for new features
* `Binance`: add method `transfer_to_sub()`. See use example in `example/exch_client.py`

## 2.1.14 2024-07-07
### Fix
* `Bybit`: `fetch_ledgers()` doubling of incoming transfers to a subaccount

## 2.1.13 2024-06-26
### Fix
* `HTX`: WSS missed account change event

### Update
* Dependency

## 2.1.12 2024-04-30
### Fix
* `Docker`: [#49 ImportError: cannot import name 'version' from 'exchanges_wrapper'](https://github.com/DogsTailFarmer/exchanges-wrapper/issues/49#issue-2272432093)

### Update
* `send_request`: controlling rate_limit by changing exception handling
* `Bitfinex`: sync `nonce` for connections group
* Dependency: Up requirements for crypto-ws-api==2.0.11

## 2.1.11 2024-04-19
### Update
* Some minor improvements
* Dependency: Up requirements for crypto-ws-api==2.0.10

## 2.1.10 2024-04-16
### Update
* `Bitfinex`: `client.fetch_order()`: searching on `origin_client_order_id` also

## 2.1.9 2024-04-14
### Fix
* Creating and manage asynchronous tasks

## 2.1.8 2024-04-08
### Update
* `Bitfinex`: add logging for `cancel_order()` and `cancel_all_orders()` methods
* Add debug logging for `open_client_connection()` and `client.load()`

## 2.1.7 2024-03-29
### Fix
* `Bybit`: http error handling: handling events that are not explicitly described

## 2.1.6 2024-03-29
### Fix
* `Bybit`: `on_balance_update`: missed event during transfer from API

### Update
* Dependency: Up requirements for crypto-ws-api==2.0.8

## 2.1.5 2024-03-25
### Fix
* `Bybit`: `on_balance_update`: duplication during transfer from web-interface
* Some exception handling

### Update
* Dependency: Up requirements for crypto-ws-api==2.0.7

## 2.1.4 2024-03-22
### Update
* Refine HTTP handle errors

## 2.1.3 2024-03-21
### Fix
* Change `datetime.now(timezone.utc).replace(tzinfo=None)` for format compatibility

### Update
* HTTP handle errors, for `response.status == 400` differ pure `Bad Request` and other reasons

## 2.1.2 2024-03-19
### Fix
* Some SonarLint issues

## 2.1.1 2024-03-16
### Update
* `Bybit`: `fetch_order`, `fetch_order_trade_list`: deep refine
* Some minor improvements

## 2.1.0 2024-03-15
### Update
* `on_order_book_update`: skip partially empty event
* `fetch_order_trade_list`: `ByBit`: remove `endTime` limit
* `exch_srv.py`: request processing is carried out in the method `send_request`

## 2.0.1 2024-03-11
### Added for new features
* `gRPC` proto: `OpenClientConnectionId` add `real_market` field

## 2.0.0.post1 2024-03-10
### Fix
* Incomplete description of dependencies

## 2.0.0 2024-03-09
### Update
* Example

## 2.0.0b2 2024-03-08
### Update
* Migrate `gRPC` from [grpcio](https://grpc.io/) to [grpclib](https://github.com/vmagamedov/grpclib) + [python-betterproto](https://github.com/danielgtaylor/python-betterproto)

## 1.4.17 2024-03-04
### Update
* `CreateLimitOrder()` and `FetchOpenOrders`: Exception handling reduced to one type
* Dependency: Up requirements for `grpcio` and `grpcio-tools` to 1.62.0
* Dependency: Up requirements for aiohttp==3.9.3

## 1.4.16 2024-02-25
### Fix
* `CreateLimitOrder()`: Missed `trade_id` parameter in fetch_order() call

### Update
* Refine error handling in `http_client`

## 1.4.15 2024-02-02
### Fix
* `HTX`: order Status set on cumulative_filled_quantity value only and `status` from event is ignored

## 1.4.14 2024-02-19
### Fix
* Exception in fetch_order: 'KeyError': 'commission'
* `fetch_order_trade_list()`: variables type inconsistent
* HTX: correcting order Status depending on cumulative_filled_quantity

## 1.4.13 2024-02-18
### Fix
* `FetchOrder()`: conditions for generating a trading event(s)

## 1.4.12 2024-02-12
### Fix
* `c_structures.OrderTradesEvent`: some fields are mixed up
* Bybit: generating a redundant order fill event
* `create_trade_stream_event`: using actual order status instead of estimated status

## 1.4.11.post1 2024-02-11
### Fix
* Bitfinex: setting original order quantity for placed order when first getting event is `te` type

## 1.4.11 2024-02-11
### Fix
* Bitfinex: use `symbol` parameter for cancel all order

## 1.4.10 2024-02-09
### Fix
* Generate trading events on the partial filled missing event
* Dependency: Rollback `grpcio` and `grpcio-tools` to 1.48.2

## 1.4.9 2024-02-07
### Fix
* Some minor fixes

## 1.4.9b5 2024-02-07
### Update
* Dependency: Up requirements for `grpcio` and `grpcio-tools` to 1.60.1

## 1.4.9b3 2024-02-07
### Update
* Bitfinex: refining order processing

## 1.4.9b2 2024-02-05
### Fix
* Binance: `TransferToMaster`: sentence `Email address should be encoded. e.g. alice@test.com should be encoded into
alice%40test.com` from API docs they are False, must be `content += urlencode(kwargs["params"], safe="@")`

### Update
* HTX: changed deprecated endpoint "v1/common/symbols" to "v1/settings/common/market-symbols"
* Binance: `GET /api/v3/exchangeInfo` from response remove deprecated `quotePrecision`

## 1.4.8 2024-02-02
### Added for new features
* Binance: `TransferToMaster` now can be used for collect assets on the subaccount

## 1.4.7.post6 2024-01-31
### Fix
* Bitfinex: order processing

## 1.4.7 2024-01-25
### Fix
* Bybit: filter LOT_SIZE.stepSize
* Bitfinex: filter LOT_SIZE.stepSize

### Added for new features
* Binance: new method [`OneClickArrivalDeposit`](https://binance-docs.github.io/apidocs/spot/en/#one-click-arrival-deposit-apply-for-expired-address-deposit-user_data)

### Update
* Bitfinex: refine the order processing
* Dependency: Up requirements for Python>=3.9

## v1.4.6 2024-01-06
### Update
* FetchOrder: Bitfinex: generate trades events for orders older than the last two weeks

## v1.4.5 2024-01-05
### Fix
* `exch_client.py` init error

### Update
* replacing json with ujson to improve performance
* Dependency: Up requirements for crypto-ws-api==2.0.6

## v1.4.4 2023-12-13
### Update
* Before send cancel order result checking if it was being executed and generating trade event
* Rollback 1.4.3
    - Binance: in create Limit order parameters adding parameter "selfTradePreventionMode": "NONE"

## v1.4.3 2023-12-12
### Fix
*  For limit order get status EXPIRED_IN_MATCH on Binance testnet #42
    + Binance: in create Limit order parameters adding parameter "selfTradePreventionMode": "NONE"
    + For method json_format.ParseDict(..., ignore_unknown_fields=True) parameter added

## v1.4.2 2023-12-11
### Update
* Some minor improvements

## v1.4.1 2023-12-01
### Update
* Bybit: fetch_ledgers(): get transfer event from Sub account to Main account on Main account

## v1.4.0 2023-11-23
### Update
* Some minor improvements

## v1.4.0rc6 2023-11-11
### Fix
* FetchOrder for Demo - ByBitSub01: BTCUSDT: 0 exception: list index out of range
* OKX: get ws_api endpoint from config
* ByBit: send and handling WSS keepalive message

## v1.4.0rc3 2023-11-01
### Fix
* websockets v12.0 raised `ConnectionClosed` exception
* Dependency: Up requirements for crypto-ws-api==2.0.5.post3

## v1.4.0rc1 2023-10-31
### Fix
* Bitfinex: WSS Information message processing logic adjusted

### Update
* Dependency: Up requirements for crypto-ws-api==2.0.5
* Other dependency
* protobuf format for:
    + OpenClientConnectionRequest
    + FetchOrderRequest

### Added for new features
* Bybit exchange V5 API support implemented. Supported account type is
[Unified Trading Account](https://testnet.bybit.com/en/help-center/article/Introduction-to-Bybit-Unified-Trading-Account),
for main and sub-accounts. Spot Trading only.

## v1.3.7.post4 2023-10-09
### Update
* Dependency: Up requirements for crypto-ws-api==2.0.4

## v1.3.7.post3 2023-10-05
### Update
* Dependency: Up requirements for crypto-ws-api==2.0.3.post1

## v1.3.7.post2 2023-09-30
### Update
* Dependency: Up requirements for crypto-ws-api==2.0.3

## v1.3.7.post1 2023-09-24
### Fix
* [2023-09-24 07:10:21,076: ERROR] Fetch order trades for HuobiSub2: HTUSDT exception: Client.fetch_order_trade_list()
missing 1 required positional argument: 'trade_id'
*  exchanges_wrapper.huobi_parser.account_trade_list: incorrect key for `orderId`

### Update
* Dependency: Up requirements for crypto-ws-api==2.0.2.post1

## v1.3.7 2023-09-19
### Fix
* Bitfinex: fix 500 `Internal server error`, caused by a Nonce value sequence failure

### Update
* For web socket connection migrated from aiohttp.ws_connection to websockets.client
* Bitfinex: Implemented rate limit control for the Bitfinex REST API.
* Bitfinex: Refine handling of active orders
* OnOrderBookUpdate: change queue to LifoQueue, for get last actual order book row

### Don't fix
* gRPC [(grpcio + grpcio-tools)](https://github.com/grpc/grpc): massive memory leak for version later than 1.48.2

## v1.3.6b7 2023-08-20
### Fix
* The `exch_srv_cfg.toml` wants to be updated from `exch_srv_cfg.toml.template`:
```toml
[endpoint.okx]
    api_public = 'https://aws.okx.com'
    api_auth = 'https://aws.okx.com'
    ws_public = 'wss://wsaws.okx.com:8443/ws/v5/public'
    ws_auth = 'wss://wsaws.okx.com:8443/ws/v5/private'
    ws_business = 'wss://ws.okx.com:8443/ws/v5/business'
    api_test = 'https://aws.okx.com'
    ws_test = 'wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999'
```

## v1.3.6b4 2023-08-18
### Fix
* [ Can't resolve missed PARTIALLY_FILLED event #29 ](https://github.com/DogsTailFarmer/exchanges-wrapper/issues/29#issue-1857179139)
* [ OKX changed WSS endpoint for Candlesticks channel #27 ](https://github.com/DogsTailFarmer/exchanges-wrapper/issues/27#issue-1852639540)

The `exch_srv_cfg.toml` wants to be updated from `exch_srv_cfg.toml.template`:
```toml
[endpoint.okx]
    api_public = 'https://aws.okx.com'
    api_auth = 'https://aws.okx.com'
    ws_public = 'wss://wsaws.okx.com:8443/ws/v5/public'
    ws_business = 'wss://ws.okx.com:8443/ws/v5/business'
    api_test = 'https://aws.okx.com'
    ws_test = 'wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999'
```
## v1.3.5rc1 2023-08-08
### Update
* Dependency: Up requirements for crypto-ws-api~=2.0.0rc3
* Optimise code by [Sourcery AI](https://docs.sourcery.ai/Guides/Getting-Started/PyCharm/) refactoring engine
* Some minor improvements

## v1.3.5b0 - 2023-07-26
### Added for new features
*  Binance, OKX: Most requests use WSS first, REST API is used as a backup and in the case of single rare requests

## v1.3.4-1 2023-07-19
### Fix
```
ERROR: Cannot install crypto_ws_api and grpcio==1.56.0 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested grpcio==1.56.0
    exchanges-wrapper 1.3.3 depends on grpcio==1.48.1
    The user requested grpcio==1.56.0
    exchanges-wrapper 1.3.2 depends on grpcio==1.48.1

```

## v1.3.4 2023-07-17
### Update
* Up requirements for grpcio to 1.56.0
```bazaar
Known security vulnerabilities detected
Dependency grpcio 	Version < 1.53.0 	Upgrade to ~> 1.53.0
```
* Bitfinex: `exchanges_wrapper.client.Client.cancel_all_orders()`: removed unnecessary status check after cancel request

## v1.3.3 2023-07-04
### Update
* UserWSSession moved to crypto-ws-api pkg 
* Refactoring logging
* CheckStream(): fix log spamming on passed check
* Up requirements for crypto-ws-api to 1.0.1

## v1.3.2 - 2023-06-29
### Added for new features
* Binance: ws_api package implemented, last version
[Websocket API](https://developers.binance.com/docs/binance-trading-api/websocket_api#general-api-information)
used for the most commonly used methods

In `exch_srv_cfg.toml` added:

```bazaar
[endpoint]
    [endpoint.binance]
        ...
        ws_api = 'wss://ws-api.binance.com:443/ws-api/v3'
        ws_api_test = 'wss://testnet.binance.vision/ws-api/v3'

```

## v1.3.1 - 2023-06-20
### Update
* Optimizing installation and initial settings

## v1.3.0-2 - 2023-06-19
### Update
* Binance: keepalive WSS

## v1.3.0 - 2023-06-01
### Fix
* exchanges_wrapper.client.Client.cancel_all_orders() set correct 'status' for cancelled orders

### Update
* protobuf format for CancelAllOrders() and OnOrderUpdate(). Now simple use ```result = eval(json.loads(res.result))```
for unpack incoming message. **Not compatible with earlier versions**
* dependencies

## v1.2.10-6-HotFix - 2023-04-12
### Fix
* Binance: REST API update for endpoint: GET /api/v3/exchangeInfo was changed MIN_NOTIONAL filter

## v1.2.10-5 - 2023-04-05
### Update
* Minor improvements

## v1.2.10-4 - 2023-03-04
### Fix
* OKX: intersection wss streams for several trades on one client (same account). WSS buffer moved from
client instance to EventsDataStream instance

## v1.2.10-3 - 2023-03-01
### Fix
* OKX: FetchOpenOrders(): getting orders list for all pair per account instead specific one pair

## v1.2.10-2 - 2023-02-26
### Added for new features
* CheckStream() method which request active WSS for trade_id

## v1.2.10 - 2023-02-22
### Added for new features
* Add method TransferToMaster():

>Send request to transfer asset from subaccount to main account  
Binance, OKX: not additional settings needed  
Bitfinex: for subaccount setting 2FA method, set WITHDRAWAL permission for API key,  
  in config for subaccount set 2FA key and master account EMail  
Huobi: in config for subaccount set master_name for Main account

### Update
* Up requirements aiohttp to 3.8.4
* Some minor improvements

## v1.2.9-2 - 2023-02-04
### Fixed
* Fix DogsTailFarmer/martin-binance#50

### Update
* Remove unnecessary shebang

## v1.2.9-1 - 2023-01-23
### Update
* Additional check for order status if its can't place during timeout period for avoid place duplicate order

## v1.2.9 - 2023-01-08
### Update
* Removing FTX smell

## v1.2.8 - 2023-01-01
### Added for new features
* Add connection to binance.us

## v1.2.7-7 2022-12-15
### Fixed
* DogsTailFarmer/martin-binance#42

## v1.2.7-6 2022-12-08
### Fixed
* Bitfinex: handling canceled TP order after it partially filled

### Update
* Binance: REST API: filter type "PERCENT_PRICE" to "PERCENT_PRICE_BY_SIDE"

## v1.2.7-5 2022-12-04
### Update
* FetchOpenOrders() add handler for errors.QueryCanceled, in case RateLimitReached was raised elsewhere
* Some minor improvements

## v1.2.7-4 2022-11-25
### Fixed
* Clearing cancel previous wss start() before restart from 1.2.7-3 was a bad idea. It's kill himself. Rollback.

## v1.2.7-3 2022-11-24
### Fixed
* Huobi: incorrect handling for incoming ping for private channel
* OKX: refactoring wss heartbeat
* Clearing cancel previous wss start() before restart

## v1.2.7-2 2022-11-23
### Update
* Bitfinex: add "receive_timeout=30" parameter in ws_connect(), this is a reliable solution for monitoring the presence
of a connection

## v1.2.7-1 2022-11-21
### Update
* Add OKX section in config file

## v1.2.7 2022-11-21
### Added for new features
* OKX exchange

## v1.2.6-1 2022-11-11
### Fixed
* FTX: OnFundsUpdate() did not return a result

### Added for new features
* OnBalanceUpdate() for autocorrect depo and initial balance

### Update
* refactoring http_client module for multi exchanges purposes
* added _percent_price filter dummy for all parsers

## v1.2.6 2022-10-13
### Fixed
* Huobi Restart WSS for PING timeout, 20s for market and 60s for user streams
* Removed unnecessary refine amount/price in create_order() for Bitfinex, FTX and Huobi

## v1.2.6b1 2022-10-12
### Added for new features
* Huobi exchange

## v1.2.5-3 2022-09-26
### Fixed
* #2 FTX WS market stream lies down quietly

### Update
* Slightly optimized process of docker container setup and start-up

## v1.2.5-2 2022-09-23
### Added for new features
* Published as Docker image

### Update
* README.md add info about Docker image use

## v1.2.5-1 2022-09-21
### Update
* Restoring the closed WSS for any reason other than forced explicit shutdown

## v1.2.5 2022-09-20
### Update
* Correct max size on queue() for book WSS

## v1.2.5b0 2022-09-18
### Fixed
* [Doesn't work on bitfinex: trading rules, step_size restriction not applicable, check](https://github.com/DogsTailFarmer/martin-binance/issues/28#issue-1366945816)
* [FTX WS market stream lies down quietly](https://github.com/DogsTailFarmer/exchanges-wrapper/issues/2#issue-1362214342) Refactoring WSS control
* Keep alive Binance combined market WSS, correct restart after stop pair

### Update
* FetchOrder for 'PARTIALLY_FILLED' event on 'binance' and 'ftx'
* User data and settings config are moved outside the package to simplify the upgrade
* Version accounting of the configuration file is given to the package

### Added for new features
* Published as Docker image
* On first run create catalog structure for user files at ```/home/user/.MartinBinance/```

## v1.2.4 2022-08-27
### Fixed
* [Incomplete account setup](DogsTailFarmer/martin-binance#17)
* 1.2.3-2 Fix wss market handler, was stopped after get int type message instead of dict
* 1.2.3-5 clear console output
* 1.2.3-6 Bitfinex WSServerHandshakeError handling
* refactoring web_socket.py for correct handling and restart wss

### Update
* up to Python 3.10.6 compatible
* reuse aiohttp.ClientSession().ws_connect() for client session

## v1.2.3 - 2022-08-14
### Fixed
* Bitfinex: restore active orders list after restart
* [exch_server not exiting if it can't obtain port](https://github.com/DogsTailFarmer/martin-binance/issues/12#issue-1328603498)

## v1.2.2 - 2022-08-06
### Fixed
* Incorrect handling fetch_open_orders response after reinit connection

## v1.2.1 - 2022-08-04
### Added for new features
* FTX: WSS 'orderbook' check status by provided checksum value

### Fixed
* FTX: WSS 'ticker' incorrect init
* Bitfinex: changed priority for order status, CANCELED priority raised


## v1.2.0 - 2022-06-30
### Added for new features
* Bitfinex REST API / WSS implemented

### Updated
* Optimized WSS processing methods to improve performance and fault tolerance
* Updated configuration file format for multi-exchange use
