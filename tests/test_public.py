import pytest

from exchange_client.client import ExchangeClient
from exchange_client.errors import (
    ExchangeAuthError,
    ExchangeHTTPError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
)


class FakeResponse:
    def __init__(
        self,
        json_data=None,
        text="",
        status_code=200,
        json_raises=False,
        headers=None,
    ):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code
        self._json_raises = json_raises
        self.headers = headers or {}

    def json(self):
        if self._json_raises:
            raise ValueError("Invalid JSON")
        if self._json_data is None:
            raise ValueError("No JSON")
        return self._json_data


def test_get_time_success(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        assert url == "https://example.com/time"
        return FakeResponse(json_data={"serverTime": 123}, status_code=200)

    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 123


def test_auth_error(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(text="unauthorized", status_code=401)

    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(ExchangeAuthError):
        client.get_time()


def test_http_error(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(text="server error", status_code=500)

    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(ExchangeHTTPError):
        client.get_time()


def test_invalid_json(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(status_code=200, json_raises=True)

    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(ExchangeHTTPError):
        client.get_time()


def test_network_timeout(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        import requests

        raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(ExchangeNetworkError):
        client.get_time()


def test_retry_success_after_transient_500(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResponse(text="server down", status_code=500)
        return FakeResponse(json_data={"serverTime": 999}, status_code=200)

    import exchange_client.client as client_module

    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 999
    assert calls["n"] == 3


def test_rate_limit_retry_after_success(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(
                text="rate limited",
                status_code=429,
                headers={"Retry-After": "0.1"},
            )
        return FakeResponse(json_data={"serverTime": 123}, status_code=200)

    import exchange_client.client as client_module

    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 123
    assert calls["n"] == 2


def test_rate_limit_gives_up(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(
            text="rate limited",
            status_code=429,
            headers={"Retry-After": "0"},
        )

    import exchange_client.client as client_module

    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(ExchangeRateLimitError):
        client.get_time()
