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
