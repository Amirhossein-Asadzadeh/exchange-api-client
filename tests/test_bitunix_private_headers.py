from exchange_client.adapters.bitunix import BitunixFuturesClient

class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text='{"code":0}', headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {"code": 0}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data

def test_private_request_sets_required_headers(monkeypatch):
    c = BitunixFuturesClient(api_key="APIKEY", secret_key="SECRET")

    monkeypatch.setattr(c, "_nonce", lambda: "n" * 32)
    monkeypatch.setattr(c, "_timestamp_ms", lambda: "1700000000000")

    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse(200, json_data={"code": 0, "data": [{"marginCoin": "USDT"}]}, text='{"code":0}')

    monkeypatch.setattr(c.session, "get", fake_get)

    out = c.get_single_account("USDT")
    assert out["code"] == 0

    h = captured["headers"]
    assert h["api-key"] == "APIKEY"
    assert h["nonce"] == "n" * 32
    assert h["timestamp"] == "1700000000000"
    assert "sign" in h
    assert h["Content-Type"] == "application/json"
