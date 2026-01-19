from __future__ import annotations
from typing import Any


class ExchangeClientError(Exception):
    """Base exception for all client errors."""

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class ExchangeHTTPError(ExchangeClientError):
    """HTTP-level errors returned by the exchange."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        method: str | None = None,
        path: str | None = None,
        body: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path
        self.body = body


class ExchangeAuthError(ExchangeHTTPError):
    """Authentication/authorization errors (401/403)."""


class ExchangeRateLimitError(ExchangeHTTPError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(status_code=429, message=message, **kwargs)
        self.retry_after = retry_after

class ExchangeNetworkError(ExchangeClientError):
    """Network/timeout/connection related errors."""
