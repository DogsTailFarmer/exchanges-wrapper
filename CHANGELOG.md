## v1.2.10 - 2023-02-xx
### Added for new features
* Add method TransferToMaster()

### Update
* Up requirements to last versions

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
OKX exchange

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
