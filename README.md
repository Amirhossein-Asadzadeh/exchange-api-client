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

## Quick start

### Install (editable)
```bash
python -m pip install -e .
