from __future__ import annotations

from typing import Any, Dict

import requests
from requests.exceptions import RequestException, Timeout

from exchange_client.errors import ExchangeRateLimitError

from .errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3          # تعداد retry (غیر از تلاش اول)
    backoff_base: float = 0.2     # ثانیه: 0.2, 0.4, 0.8, ...
    backoff_max: float = 2.0      # سقف backoff


class ExchangeClient:
    """
    Minimal exchange API client with clean errors.
    """

    def __init__(self, base_url: str, timeout: float = 10.0, retry: RetryConfig = RetryConfig()):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry = retry
        self.session = requests.Session()

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"

        attempts = 0
        while True:
            try:
                response = self.session.get(url, timeout=self.timeout)
            except Timeout:
                error = ExchangeNetworkError(f"Timeout calling {url}")
            except RequestException as e:
                error = ExchangeNetworkError(f"Network error calling {url}: {e}")
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
                        return response.json()
                    except ValueError as e:
                        raise ExchangeHTTPError(
                            status_code=response.status_code,
                            message="Invalid JSON in response",
                            method="GET",
                            path=path,
                            body=(response.text or "")[:300],
                        ) from e

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

            # Prefer Retry-After for rate limits
            if isinstance(error, ExchangeRateLimitError) and error.retry_after is not None:
                time.sleep(error.retry_after)
            else:
                backoff = min(
                    self.retry.backoff_base * (2**attempts),
                    self.retry.backoff_max,
                )
                time.sleep(backoff)

            attempts += 1

        url = f"{self.base_url}{path}"

        attempts = 0
        while True:
            try:
                response = self.session.get(url, timeout=self.timeout)
            except Timeout:
                error = ExchangeNetworkError(f"Timeout calling {url}")
            except RequestException as e:
                error = ExchangeNetworkError(f"Network error calling {url}: {e}")
            else:
                if response.status_code in (401, 403):
                    raise ExchangeAuthError(
    status_code=response.status_code,
    message=f"Auth failed for {url}",
    method="GET",
    path=path,
)
                if 200 <= response.status_code < 300:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise ExchangeHTTPError(response.status_code, "Invalid JSON in response") from e

                # retryable HTTP errors
                if response.status_code >= 500:
                    error = ExchangeHTTPError(response.status_code, "Server error")
                else:
                    msg = (response.text or "").strip()
                    raise ExchangeHTTPError(response.status_code, msg[:300] if msg else "Unknown error")

            # retry logic
            if attempts >= self.retry.max_retries:
                raise error

            backoff = min(
                self.retry.backoff_base * (2 ** attempts),
                self.retry.backoff_max,
            )
            time.sleep(backoff)
            attempts += 1
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
