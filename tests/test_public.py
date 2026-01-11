from exchange_client.client import ExchangeClient
from exchange_client.errors import ExchangeAuthError, ExchangeHTTPError, ExchangeNetworkError


class FakeResponse:
    def __init__(self, json_data=None, text="", status_code=200, json_raises=False):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("Invalid JSON")
        return self._json_data


def test_get_time_success(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        assert url == "https://example.com/time"
        assert timeout == 10.0
        return FakeResponse(json_data={"serverTime": 123}, status_code=200)

    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 123


def test_auth_error(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(json_data=None, text="unauthorized", status_code=401)

    monkeypatch.setattr(client.session, "get", fake_get)

    try:
        client.get_time()
        assert False, "Expected ExchangeAuthError"
    except ExchangeAuthError:
        assert True


def test_http_error(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        return FakeResponse(json_data=None, text="server error", status_code=500)

    monkeypatch.setattr(client.session, "get", fake_get)

    try:
        client.get_time()
        assert False, "Expected ExchangeHTTPError"
    except ExchangeHTTPError as e:
        assert e.status_code == 500


def test_network_error_timeout(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        import requests
        raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(client.session, "get", fake_get)

    try:
        client.get_time()
        assert False, "Expected ExchangeNetworkError"
    except ExchangeNetworkError:
        assert True

def test_retry_success_after_transient_500(monkeypatch):
    # 2 failures (500) then success (200)
    client = ExchangeClient(base_url="https://example.com")

    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResponse(json_data=None, text="server down", status_code=500)
        return FakeResponse(json_data={"serverTime": 999}, status_code=200)

    # prevent real sleep during tests
    import exchange_client.client as client_module
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)

    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 999
    assert calls["n"] == 3


def test_retry_gives_up_after_max_retries(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    # make it faster for test
    from exchange_client.client import RetryConfig
    client.retry = RetryConfig(max_retries=2, backoff_base=0.0, backoff_max=0.0)

    def always_500(url, timeout):
        return FakeResponse(json_data=None, text="server down", status_code=500)

    import exchange_client.client as client_module
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)

    monkeypatch.setattr(client.session, "get", always_500)

    try:
        client.get_time()
        assert False, "Expected ExchangeHTTPError"
    except ExchangeHTTPError as e:
        assert e.status_code == 500
