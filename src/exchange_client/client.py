from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import time
import requests
from requests.exceptions import RequestException, Timeout

from .errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError, ExchangeRateLimitError


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3          # number of retries (excluding the first attempt)
    backoff_base: float = 0.2     # seconds: 0.2, 0.4, 0.8, ...
    backoff_max: float = 2.0      # cap for backoff


class ExchangeClient:
    """Minimal exchange API client with clean errors."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        retry: RetryConfig = RetryConfig(),
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry = retry
        self.session = session or requests.Session()

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        attempts = 0
        while True:
            try:
                response = self.session.get(url, timeout=self.timeout)
            except Timeout as e:
                error: Exception = ExchangeNetworkError(f"Timeout calling {url}", cause=e)
            except RequestException as e:
                error = ExchangeNetworkError(f"Network error calling {url}: {e}", cause=e)
            else:
                # Auth errors: do NOT retry
                if response.status_code in (401, 403):
                    raise ExchangeAuthError(
                        status_code=response.status_code,
                        message=f"Auth failed for {url}",
                        method="GET",
                        path=path,
                        body=(response.text or "")[:300],
                    )

                # Success
                if 200 <= response.status_code < 300:
                    try:
                        data = response.json()
                    except ValueError as e:
                        raise ExchangeHTTPError(
                            status_code=response.status_code,
                            message="Invalid JSON in response",
                            method="GET",
                            path=path,
                            body=(response.text or "")[:300],
                        ) from e

                    if not isinstance(data, dict):
                        raise ExchangeHTTPError(
                            status_code=response.status_code,
                            message="Unexpected JSON type (expected object)",
                            method="GET",
                            path=path,
                            body=(response.text or "")[:300],
                        )

                    return data

                # Rate limit: retryable, prefer Retry-After
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    parsed: float | None = None
                    if retry_after is not None:
                        try:
                            parsed = float(retry_after)
                        except ValueError:
                            parsed = None

                    error = ExchangeRateLimitError(
                        retry_after=parsed,
                        method="GET",
                        path=path,
                        body=(response.text or "")[:300],
                    )

                # 5xx: retryable
                elif response.status_code >= 500:
                    error = ExchangeHTTPError(
                        status_code=response.status_code,
                        message="Server error",
                        method="GET",
                        path=path,
                        body=(response.text or "")[:300],
                    )

                # other 4xx: not retryable
                else:
                    msg = (response.text or "").strip()
                    raise ExchangeHTTPError(
                        status_code=response.status_code,
                        message=msg[:300] if msg else "Unknown error",
                        method="GET",
                        path=path,
                        body=(response.text or "")[:300],
                    )

            # retry logic
            if attempts >= self.retry.max_retries:
                raise error

            if isinstance(error, ExchangeRateLimitError) and error.retry_after is not None:
                time.sleep(error.retry_after)
            else:
                backoff = min(self.retry.backoff_base * (2**attempts), self.retry.backoff_max)
                time.sleep(backoff)

            attempts += 1

    def get_time(self) -> dict[str, Any]:
        return self._get("/time")
