from __future__ import annotations

from typing import Any, Dict
import requests


class ExchangeClient:
    """
    Minimal exchange API client.

    This is the base layer that handles:
    - HTTP session
    - timeouts
    - base URL management
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_time(self) -> Dict[str, Any]:
        """
        Public endpoint example.
        """
        return self._get("/time")
