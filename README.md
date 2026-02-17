[![CI](https://github.com/Amirhossein-Asadzadeh/exchange-api-client/actions/workflows/ci.yml/badge.svg)](https://github.com/Amirhossein-Asadzadeh/exchange-api-client/actions/workflows/ci.yml)


# Exchange API Client

Production-grade cryptocurrency exchange API client in Python, built with a `src/` layout, tests, linting, and CI.

## Why this exists
Most exchange integrations fail in production due to:
- missing timeouts
- weak error handling
- lack of tests
- no CI gates

This repo starts with a minimal client and grows into a reliable integration layer used by backend/platform services.

## Features (current)
- Reusable HTTP session (`requests.Session`)
- Request timeout
- `src/` layout (clean packaging)
- Unit tests with `pytest` (no real network calls)
- Linting with `ruff`
- GitHub Actions CI (lint + tests)

## Reliability: Retries & Rate Limiting

This client is built with production-grade reliability defaults:

- **Retries on transient failures (5xx)** with exponential backoff (bounded).
- **HTTP 429 (rate limit)** is handled explicitly:
  - Honors `Retry-After` when provided by the server.
  - Falls back to backoff when `Retry-After` is missing or invalid.
- **Structured exceptions** to support clear error handling:
  - `ExchangeAuthError` for 401/403 (no retries)
  - `ExchangeRateLimitError` for 429 (retryable with `Retry-After`)
  - `ExchangeHTTPError` for other HTTP failures
  - `ExchangeNetworkError` for network/timeout issues

All behaviors are covered by automated tests and executed in CI.

## Quick start

### Install (editable)
```bash
python -m pip install -e .
```

### Install with dev dependencies
```bash
python -m pip install -e ".[dev]"
```

---

## Usage Examples

### 1. Fetch public market data (tickers)

```python
from exchange_client.adapters.bitunix import BitunixFuturesClient

client = BitunixFuturesClient(api_key="", secret_key="")

# All tickers
tickers = client.get_tickers()
print(tickers)

# Single symbol
btc = client.get_tickers(symbols="BTCUSDT")
print(btc)
```

---

### 2. Enable logging

The library uses Python's standard `logging` module and emits no output by default.
Configure a handler to see what's happening at runtime:

```python
import logging
from exchange_client.adapters.bitunix import BitunixFuturesClient

# Show INFO and above (time sync, retries, rate limits)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# Use DEBUG to also see signature details and timestamps
# logging.basicConfig(level=logging.DEBUG, ...)

client = BitunixFuturesClient(api_key="your-key", secret_key="your-secret")
account = client.get_single_account(margin_coin="USDT")
print(account)
```

Example output:
```
2026-01-01 12:00:00,123 exchange_client.adapters.bitunix INFO Time sync complete: server=1735732800123 local=1735732800100 offset=+23 ms
```

---

### 3. Custom retry and timeout configuration

```python
from exchange_client.adapters.bitunix import BitunixFuturesClient
from exchange_client.client import RetryConfig

client = BitunixFuturesClient(
    api_key="your-key",
    secret_key="your-secret",
    timeout=5.0,          # 5-second request timeout
    retry=RetryConfig(
        max_retries=5,        # retry up to 5 times
        backoff_base=0.5,     # 0.5s, 1.0s, 2.0s, ...
        backoff_max=10.0,     # cap backoff at 10 seconds
    ),
)

pairs = client.get_trading_pairs()
print(pairs)
```

---

### 4. Error handling

```python
from exchange_client.adapters.bitunix import BitunixFuturesClient
from exchange_client.errors import (
    ExchangeAuthError,
    ExchangeRateLimitError,
    ExchangeHTTPError,
    ExchangeNetworkError,
    ExchangeClientError,
)

client = BitunixFuturesClient(api_key="your-key", secret_key="your-secret")

try:
    account = client.get_single_account(margin_coin="USDT")
    print(account)

except ExchangeAuthError as e:
    # 401 or 403 — bad API key or IP not whitelisted; never retried
    print(f"Auth failed (HTTP {e.status_code}): {e.message}")

except ExchangeRateLimitError as e:
    # 429 — all retries exhausted after honouring Retry-After
    retry_hint = f"{e.retry_after}s" if e.retry_after else "unknown"
    print(f"Rate limited. Server asked to wait {retry_hint}.")

except ExchangeHTTPError as e:
    # Any other HTTP error (4xx client errors, 5xx after retries exhausted)
    print(f"HTTP {e.status_code} on {e.method} {e.path}: {e.message}")
    print(f"Response body: {e.body}")

except ExchangeNetworkError as e:
    # Timeout or connection failure after all retries exhausted
    print(f"Network error: {e}")

except ExchangeClientError as e:
    # Catch-all for any other library error
    print(f"Unexpected client error: {e}")
```
