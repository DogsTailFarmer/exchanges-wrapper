<h1 align="center"><img align="center" src="https://raw.githubusercontent.com/gist/DogsTailFarmer/167eaf65cebfe95d954082c7f181a2cc/raw/a67270de8663ad3de4733330ff64c9ba3153f87d/Logo%202v3.svg" width="75">Crypto exchanges API/WSS wrapper with grpc powered server</h1>

<h2 align="center">Binance, Bitfinex, Huobi, OKX,</h2>

<h3 align="center">For SPOT markets</h3>

***
<a href="https://pypi.org/project/exchanges-wrapper/"><img src="https://img.shields.io/pypi/v/exchanges-wrapper" alt="PyPI version"></a>
<a href="https://codeclimate.com/github/DogsTailFarmer/exchanges-wrapper/maintainability"><img src="https://api.codeclimate.com/v1/badges/f333ab9b1f3024699e09/maintainability" /></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/exchanges-wrapper/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/exchanges-wrapper.svg/?label=resolved+issues&token=XuG5PmzMiKlDL921-qREIuX_"/></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/exchanges-wrapper/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/exchanges-wrapper.svg/?label=active+issues&token=XuG5PmzMiKlDL921-qREIuX_"/></a>
<a href="https://sonarcloud.io/summary/new_code?id=DogsTailFarmer_exchanges-wrapper" target="_blank"><img alt="sonarcloud" title="sonarcloud" src="https://sonarcloud.io/api/project_badges/measure?project=DogsTailFarmer_exchanges-wrapper&metric=alert_status"/></a>
<a href="https://pepy.tech/project/exchanges-wrapper" target="_blank"><img alt="Downloads" title="Downloads" src="https://pepy.tech/badge/exchanges-wrapper/month"/></a>
***
From 1.3.2 update exch_srv_cfg.toml (see [CHANGELOG](https://github.com/DogsTailFarmer/exchanges-wrapper/blob/master/CHANGELOG.md#added-for-new-features) for details)
***

## exchanges-wrapper vs binance.py
The main difference is the development of the project for trading with many exchanges.

Next is adding a new module ```exchanges_wrapper/exch_srv.py``` as a multiplexer layer, providing simultaneous async interaction for many accounts
and many trading pairs through one connection. It's powered by [gRPC](https://grpc.io/about/)
Remote Procedure Call framework.

Warning. Coverage of overridden binance.py packages is significant but not complete.
Served methods describes into ```example/exch_client.py```

### Initial capabilities (inherited from binance.py)
- Covers general endpoints (test connectivity and get exchange information's)
- Covers market data endpoints
- Covers Account endpoints (create and manage orders)
- Covers user data stream (receive real time user updates)
- Covers web socket streams (receive real time market updates)
- Async support
- Auto reconnect after exchanges API or network failure
- Completely free and without limitations

### Added Features
- Multi exchanges support
- Adaptive algorithm to ensure maximum performance and avoid exceeding the rates limits
- Passthrough logging
- WSS keepalive
- Reuse session for new client sessions
- Utilizing Websocket API (bidirectional) for the most commonly used methods (Binance ws-api/v3, )

## Extra exchanges implementation features
- Binance REST API and WSS are accepted as basic, connection of other exchanges wrapped their API to Binance compatible
- For other, some data cannot be obtained by directly calling one method, it is generated by a synthetic or calculation
method
- Some exchanges have not any testing or "paper trading" features, therefore, application development and testing is possible only
at real bidding. First, run applications on the [Binance Spot Test Network](https://testnet.binance.vision/) or (Bitfinex, OKX) test account.

## Get started
### Prepare exchange account
* Create account on [Binance](https://accounts.binance.com/en/register?ref=QCS4OGWR) and get 10% discount on all trading fee
* Create account on [Bitfinex](https://www.bitfinex.com/sign-up?refcode=v_4az2nCP) and get 6% rebate fee
* Create account on [HUOBI](https://www.huobi.com/en-us/topic/double-reward/?invite_code=9uaw3223) and get 10% cashback
on all trading fee
* Create account on [OKX](https://www.okx.com/join/2607649) and get Mystery Boxes worth up to $10,000
* For test purpose log in at [Binance Spot Test Network](https://testnet.binance.vision/)
* Create API Key
* After install and create environment specify api_key and api_secret in ```/home/ubuntu/.MartinBinance/config/exch_srv_cfg.toml```

### Install use PIP
To install just run the following command:
```console
pip install exchanges-wrapper
```
After first install create environment by run ```exchanges-wrapper-init``` in terminal window.

The structure of the working directory will be created and the necessary files will be copied:
For Ubuntu it will be here: ```home/user/.MartinBinance/```

For upgrade to latest versions use:
```console
pip install -U exchanges-wrapper
```

#### Start server
* Run in terminal window
  ```
  exchanges-wrapper-srv
  ``` 
  
* Use an example to study
  + Copy [example/ms_cfg.toml](https://github.com/DogsTailFarmer/exchanges-wrapper/blob/master/example/ms_cfg.toml)
  to ```/home/ubuntu/.MartinBinance/config/``` and select (uncomment) desired exchange. Don't change exchange name.
  + Run [example/exch_client.py](https://github.com/DogsTailFarmer/exchanges-wrapper/blob/master/example/exch_client.py)
  in other terminal window

### Use Docker image
```console
docker pull ghcr.io/dogstailfarmer/exchanges-wrapper:latest
```
#### First run
The structure of the working directory will be created and the necessary files will be copied:
For Ubuntu it will be here: ```home/user/.MartinBinance/```
```console
docker run --rm --entrypoint /bin/sh exchanges-wrapper -c "cat ./exchanges_wrapper/__init__.py" > init.py && \
docker run --rm --entrypoint /bin/sh exchanges-wrapper -c "cat ./exchanges_wrapper/exch_srv_cfg.toml.template" > exch_srv_cfg.toml.template &&\
 python3 init.py && rm init.py && rm exch_srv_cfg.toml.template
```
#### Start server
```console
docker run -itP \
 --mount type=bind,source=/home/ubuntu/.MartinBinance,target=/home/appuser/.MartinBinance \
 --network=host \
 --restart=always \
 --name=exchanges-wrapper \
 exchanges-wrapper
```

### Documentations
* For [binance.py](https://th0rgal.gitbook.io/binance-py/) use original
* Served methods and examples of their use are described at ```example/exch_client.py```
* For [Protocol Buffers](https://developers.google.com/protocol-buffers/docs/overview) serializing structured data
see ```proto/exchanges_wrapper/api.proto```

## Donate
*BNB*, *BUSD*, *USDT* (BEP20) 0x5b52c6ba862b11318616ee6cef64388618318b92

*USDT* (TRC20) TP1Y43dpY7rrRyTSLaSKDZmFirqvRcpopC

## Powered by exchanges-wrapper
<a><img align="middle" src="https://github.com/DogsTailFarmer/martin-binance/raw/public/doc/Modified%20martingale.svg" width="50"></a>
[martin-binance](https://github.com/DogsTailFarmer/martin-binance)

Free trading system for crypto exchanges SPOT markets. Adaptive customizable reverse grid strategy based on martingale.
