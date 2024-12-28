class ExchangePyError(Exception):
    pass


class UnknownEventType(ExchangePyError):
    message = "ExchangePy doesn't handle this event type"


class ExchangeError(ExchangePyError):
    pass


class QueryCanceled(ExchangePyError):
    message = "Rate limit reached, to avoid an IP ban, this query has been cancelled"


class HTTPError(ExchangePyError):
    code = 400
    message = "Malformed request"


class WAFLimitViolated(HTTPError):
    code = 403
    message = "The WAF Limit (Web Application Firewall) has been violated."


class RateLimitReached(HTTPError):
    code = 429
    message = "The rate limit has been reached."


class IPAddressBanned(HTTPError):
    code = 418
    message = "Your IP address has been auto-banned for continuing to send requests after receiving 429 codes."
