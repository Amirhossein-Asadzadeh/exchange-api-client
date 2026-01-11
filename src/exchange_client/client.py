from __future__ import annotations

from typing import Any, Dict

import requests
from requests.exceptions import RequestException, Timeout

from .errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError


class ExchangeClient:
    """
    Minimal exchange API client with clean errors.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"

        try:
            response = self.session.get(url, timeout=self.timeout)
        except Timeout as e:
            raise ExchangeNetworkError(f"Timeout calling {url}") from e
        except RequestException as e:
            raise ExchangeNetworkError(f"Network error calling {url}: {e}") from e

        if response.status_code in (401, 403):
            raise ExchangeAuthError(f"Auth failed for {url} (HTTP {response.status_code})")

        if not (200 <= response.status_code < 300):
            msg = (response.text or "").strip()
            raise ExchangeHTTPError(response.status_code, msg[:300] if msg else "Unknown error")

        try:
            return response.json()
        except ValueError as e:
            raise ExchangeHTTPError(response.status_code, "Invalid JSON in response") from e

    def get_time(self) -> Dict[str, Any]:
        return self._get("/time")
