from fastapi import HTTPException

class GatewayError(Exception):
    pass

class AuthenticationError(GatewayError):
    pass

class RateLimitExceeded(GatewayError):
    pass

class ProviderError(GatewayError):
    pass

def to_http_exception(exc: GatewayError) -> HTTPException:
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, RateLimitExceeded):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, ProviderError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail="internal server error")
