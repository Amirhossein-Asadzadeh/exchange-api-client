from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from requests.exceptions import RequestException, Timeout

from ..client import RetryConfig
from ..errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError, ExchangeRateLimitError


@dataclass(frozen=True)
class BitunixConfig:
    # Futures examples use fapi.bitunix.com
    base_url: str = "https://fapi.bitunix.com"
    # Docs: timestamp must be within 60 seconds of API time
    language: str = "en-US"
    # How long we trust the offset before refreshing (ms)
    time_sync_ttl_ms: int = 30_000
    # Server time endpoint (can be adjusted if Bitunix uses a different path)
    time_path: str = "/api/v1/futures/market/time"


class BitunixFuturesClient:
    """
    Bitunix Futures adapter.

    Signature:
      digest = SHA256(nonce + timestamp + apiKey + queryParams + body)
      sign   = SHA256(digest + secretKey)

    Headers:
      api-key, nonce, timestamp, sign, Content-Type: application/json
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        config: BitunixConfig = BitunixConfig(),
        timeout: float = 10.0,
        retry: RetryConfig = RetryConfig(),
        session: requests.Session | None = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.config = config
        self.timeout = timeout
        self.retry = retry
        self.session = session or requests.Session()

        # Clock drift handling
        self._time_offset_ms: int = 0
        self._time_offset_last_sync_ms: int | None = None

    # ---------- convenience private endpoints ----------
    def _private_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json_body=body, private=True)

    def place_order_demo(self, symbol: str, side: str, qty: str) -> dict[str, Any]:
        # مسیر را بعداً با endpoint واقعی سفارش جایگزین می‌کنیم
        return self._private_post(
            "/api/v1/futures/order/place",
            {"symbol": symbol, "side": side, "qty": qty},
        )

    # ---------- time sync (clock drift) ----------
    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def get_time(self) -> dict[str, Any]:
        # Public time endpoint (path configurable via BitunixConfig)
        return self._request("GET", self.config.time_path, private=False)

    def _server_time_ms_via_date_header(self) -> int | None:
        """
        Fallback when Bitunix time endpoint returns JSON error payload (e.g. code=2, "System error").
        Uses HTTP Date header which is usually still reliable.
        """
        url = f"{self.config.base_url}{self.config.time_path}"
        try:
            resp = self.session.get(
                url,
                headers={"language": self.config.language},
                timeout=self.timeout,
            )
            date_hdr = resp.headers.get("Date")
            if not date_hdr:
                return None

            dt = parsedate_to_datetime(date_hdr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return int(dt.timestamp() * 1000)
        except Exception:
            return None

    def sync_time_offset(self) -> None:
        """
        Refresh server-local clock offset.

        Primary source: Bitunix time endpoint (JSON).
        Fallback: HTTP Date header when time endpoint returns "System error" or malformed payload.
        """
        server_ms: int | None = None

        # 1) Primary: official time endpoint
        try:
            data = self.get_time()

            # Accept common shapes:
            # - {"serverTime": 123}
            # - {"code":0,"data":{"serverTime":123}, ...}
            # - {"code":0,"data":123, ...} (rare)
            if isinstance(data, dict):
                if data.get("serverTime") is not None:
                    server_ms = int(data["serverTime"])
                else:
                    inner = data.get("data")
                    if isinstance(inner, dict) and inner.get("serverTime") is not None:
                        server_ms = int(inner["serverTime"])
                    elif inner is not None:
                        # last resort if data is numeric timestamp
                        try:
                            server_ms = int(inner)
                        except (TypeError, ValueError):
                            server_ms = None
        except Exception:
            server_ms = None

        # 2) Fallback: Date header
        if server_ms is None:
            server_ms = self._server_time_ms_via_date_header()

        if server_ms is None:
            raise ExchangeHTTPError(
                status_code=200,
                message="Unable to obtain server time (time endpoint + Date header failed)",
                method="GET",
                path=self.config.time_path,
                body="",
            )

        local_ms = self._now_ms()
        self._time_offset_ms = server_ms - local_ms
        self._time_offset_last_sync_ms = local_ms

    def _ensure_time_synced(self) -> None:
        now = self._now_ms()
        if self._time_offset_last_sync_ms is None:
            self.sync_time_offset()
            return
        if (now - self._time_offset_last_sync_ms) > self.config.time_sync_ttl_ms:
            self.sync_time_offset()

    def _looks_like_timestamp_error(self, payload: dict[str, Any]) -> bool:
        msg = str(payload.get("msg") or payload.get("message") or "").lower()
        # conservative heuristics
        if "timestamp" in msg:
            return True
        if "time" in msg and ("expire" in msg or "expired" in msg):
            return True
        if "out of" in msg and "time" in msg:
            return True
        return False

    # ---------- canonicalization + signing ----------
    def _nonce(self) -> str:
        # 32 hex chars, good enough for "32-bit random string" requirement
        return uuid.uuid4().hex

    def _timestamp_ms(self) -> str:
        # For private calls we prefer server-synced time
        self._ensure_time_synced()
        return str(self._now_ms() + self._time_offset_ms)

    def _compact_json(self, body: dict[str, Any] | None) -> str:
        if not body:
            return ""
        # IMPORTANT: remove spaces; must match signature string
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    def _canonical_query(self, params: dict[str, Any] | None) -> str:
        if not params:
            return ""
        items = sorted(params.items(), key=lambda kv: kv[0])
        # IMPORTANT: Bitunix expects key+value concatenation, no '=' and no '&'
        return "".join(f"{k}{v}" for k, v in items)

    def _sha256_hex(self, s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _sign(self, nonce: str, timestamp: str, query_params: str, body: str) -> str:
        digest_input = f"{nonce}{timestamp}{self.api_key}{query_params}{body}"
        digest = self._sha256_hex(digest_input)
        sign_input = f"{digest}{self.secret_key}"
        return self._sha256_hex(sign_input)

    def _is_success_payload(self, data: dict[str, Any]) -> bool:
        return data.get("code") in (0, "0", None)

    # ---------- request core ----------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        private: bool = False,
    ) -> dict[str, Any]:
        method_u = method.upper()
        url = f"{self.config.base_url}{path}"

        attempts = 0
        while True:
            headers: dict[str, str] = {"Content-Type": "application/json", "language": self.config.language}

            req_params = params or {}
            body_str = self._compact_json(json_body)

            if private:
                nonce = self._nonce()
                timestamp = self._timestamp_ms()
                canonical_query = self._canonical_query(req_params)
                sig = self._sign(nonce, timestamp, canonical_query, body_str)

                headers.update(
                    {
                        "api-key": self.api_key,
                        "nonce": nonce,
                        "timestamp": timestamp,
                        "sign": sig,
                    }
                )

            try:
                if method_u == "GET":
                    resp = self.session.get(url, params=req_params, headers=headers, timeout=self.timeout)
                elif method_u == "POST":
                    resp = self.session.post(
                        url,
                        params=req_params,
                        json=json_body or {},
                        headers=headers,
                        timeout=self.timeout,
                    )
                else:
                    raise ValueError(f"Unsupported method: {method_u}")
            except Timeout as e:
                err: Exception = ExchangeNetworkError(f"Timeout calling {url}", cause=e)
            except RequestException as e:
                err = ExchangeNetworkError(f"Network error calling {url}: {e}", cause=e)
            else:
                # Auth failures
                if resp.status_code in (401, 403):
                    raise ExchangeAuthError(
                        status_code=resp.status_code,
                        message="Auth failed",
                        method=method_u,
                        path=path,
                        body=(resp.text or "")[:300],
                    )

                # OK
                if 200 <= resp.status_code < 300:
                    try:
                        data = resp.json()
                    except ValueError as e:
                        raise ExchangeHTTPError(
                            status_code=resp.status_code,
                            message="Invalid JSON",
                            method=method_u,
                            path=path,
                            body=(resp.text or "")[:300],
                        ) from e

                    if not isinstance(data, dict):
                        raise ExchangeHTTPError(
                            status_code=resp.status_code,
                            message="Unexpected JSON type (expected object)",
                            method=method_u,
                            path=path,
                            body=(resp.text or "")[:300],
                        )

                    # Bitunix-style API error payloads (even on HTTP 200)
                    if not self._is_success_payload(data):
                        # if looks like a timestamp issue, sync and retry once
                        if private and self._looks_like_timestamp_error(data) and attempts == 0:
                            self.sync_time_offset()
                            attempts += 1
                            continue

                        raise ExchangeHTTPError(
                            status_code=resp.status_code,
                            message=str(data.get("msg") or data.get("message") or "API error"),
                            method=method_u,
                            path=path,
                            body=(resp.text or "")[:300],
                        )

                    return data

                # Rate limit
                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    parsed: float | None = None
                    if ra is not None:
                        try:
                            parsed = float(ra)
                        except ValueError:
                            parsed = None

                    err = ExchangeRateLimitError(
                        retry_after=parsed,
                        method=method_u,
                        path=path,
                        body=(resp.text or "")[:300],
                    )

                # Retryable server errors
                elif resp.status_code >= 500:
                    err = ExchangeHTTPError(
                        status_code=resp.status_code,
                        message="Server error",
                        method=method_u,
                        path=path,
                        body=(resp.text or "")[:300],
                    )

                # Non-retryable client errors
                else:
                    msg = (resp.text or "").strip()
                    raise ExchangeHTTPError(
                        status_code=resp.status_code,
                        message=msg[:300] if msg else "Unknown error",
                        method=method_u,
                        path=path,
                        body=(resp.text or "")[:300],
                    )

            # retry logic (network / 5xx / rate-limit)
            if attempts >= self.retry.max_retries:
                raise err

            if isinstance(err, ExchangeRateLimitError) and err.retry_after is not None:
                time.sleep(err.retry_after)
            else:
                backoff = min(self.retry.backoff_base * (2**attempts), self.retry.backoff_max)
                time.sleep(backoff)

            attempts += 1

    # ---------- public endpoints ----------
    def get_tickers(self, symbols: str | None = None) -> dict[str, Any]:
        # GET /api/v1/futures/market/tickers
        params: dict[str, Any] = {}
        if symbols is not None:
            params["symbols"] = symbols
        return self._request("GET", "/api/v1/futures/market/tickers", params=params, private=False)

    def get_trading_pairs(self, symbols: str | None = None) -> dict[str, Any]:
        # GET /api/v1/futures/market/trading_pairs
        params: dict[str, Any] = {}
        if symbols is not None:
            params["symbols"] = symbols
        return self._request("GET", "/api/v1/futures/market/trading_pairs", params=params, private=False)

    # ---------- private endpoints ----------
    def get_single_account(self, margin_coin: str) -> dict[str, Any]:
        # GET /api/v1/futures/account?marginCoin=USDT
        return self._request(
            "GET",
            "/api/v1/futures/account",
            params={"marginCoin": margin_coin},
            private=True,
        )
