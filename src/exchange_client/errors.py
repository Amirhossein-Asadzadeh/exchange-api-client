from __future__ import annotations


class ExchangeClientError(Exception):
    """Base exception for all client errors."""


class ExchangeHTTPError(ExchangeClientError):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class ExchangeNetworkError(ExchangeClientError):
    """Network/timeout/connection related errors."""


class ExchangeAuthError(ExchangeClientError):
    """Authentication/authorization errors (401/403)."""
