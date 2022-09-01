## v1.2.5 2022-09-01
### Update
* FetchOrder for 'PARTIALLY_FILLED' event on 'binance' and 'ftx'

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
