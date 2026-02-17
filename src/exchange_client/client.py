from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import time
import requests
from requests.exceptions import RequestException, Timeout

from .errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError, ExchangeRateLimitError

logger = logging.getLogger(__name__)


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
                logger.error("GET %s timed out (attempt %d/%d)", path, attempts + 1, self.retry.max_retries + 1)
                error: Exception = ExchangeNetworkError(f"Timeout calling {url}", cause=e)
            except RequestException as e:
                logger.error("GET %s network error (attempt %d/%d): %s", path, attempts + 1, self.retry.max_retries + 1, e)
                error = ExchangeNetworkError(f"Network error calling {url}: {e}", cause=e)
            else:
                # Auth errors: do NOT retry
                if response.status_code in (401, 403):
                    logger.error("GET %s auth error: HTTP %d", path, response.status_code)
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

                    logger.warning(
                        "GET %s rate limited (attempt %d/%d); Retry-After=%s",
                        path, attempts + 1, self.retry.max_retries + 1, parsed,
                    )
                    error = ExchangeRateLimitError(
                        retry_after=parsed,
                        method="GET",
                        path=path,
                        body=(response.text or "")[:300],
                    )

                # 5xx: retryable
                elif response.status_code >= 500:
                    logger.warning(
                        "GET %s server error HTTP %d (attempt %d/%d)",
                        path, response.status_code, attempts + 1, self.retry.max_retries + 1,
                    )
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
                    logger.error("GET %s client error HTTP %d", path, response.status_code)
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
                logger.info("GET %s sleeping %.2fs (Retry-After)", path, error.retry_after)
                time.sleep(error.retry_after)
            else:
                backoff = min(self.retry.backoff_base * (2**attempts), self.retry.backoff_max)
                logger.info("GET %s retrying in %.2fs (attempt %d/%d)", path, backoff, attempts + 1, self.retry.max_retries + 1)
                time.sleep(backoff)

            attempts += 1

    def get_time(self) -> dict[str, Any]:
        return self._get("/time")
