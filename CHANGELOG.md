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
