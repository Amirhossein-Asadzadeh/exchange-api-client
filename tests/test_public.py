from exchange_client.client import ExchangeClient


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def test_get_time_success(monkeypatch):
    client = ExchangeClient(base_url="https://example.com")

    def fake_get(url, timeout):
        assert url == "https://example.com/time"
        assert timeout == 10.0
        return FakeResponse({"serverTime": 123})

    monkeypatch.setattr(client.session, "get", fake_get)

    out = client.get_time()
    assert out["serverTime"] == 123
