## v1.2.3 - 2022-08-14
### Fixed
* Bitfinex: restore active orders list after restart
* [exch_server not exiting if can't obtaint port](DogsTailFarmer/martin-binance#12)

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
