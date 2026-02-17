from exchange_client.adapters.bitunix import BitunixFuturesClient

class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text='{"code":0}', headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {"code": 0}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data

def test_private_post_signature_depends_on_compact_body(monkeypatch):
    c = BitunixFuturesClient(api_key="APIKEY", secret_key="SECRET")

    # Fix nonce/timestamp for the test
    monkeypatch.setattr(c, "_nonce", lambda: "n" * 32)
    monkeypatch.setattr(c, "_timestamp_ms", lambda: "1700000000000")

    captured = {}

    def fake_post(url, params=None, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        captured["json"] = json
        return DummyResponse(200, json_data={"code": 0})

    monkeypatch.setattr(c.session, "post", fake_post)

    # Body
    body = {"b": 2, "a": 1}
    c._private_post("/api/v1/futures/order/place", body)

    # Expected signature = over compact body
    canonical_query = ""  # For POST we have no query params
    compact = c._compact_json(body)  # {"b":2,"a":1} (no spaces)
    expected = c._sign("n" * 32, "1700000000000", canonical_query, compact)

    assert captured["headers"]["sign"] == expected
    assert captured["headers"]["api-key"] == "APIKEY"
    assert captured["headers"]["nonce"] == "n" * 32
    assert captured["headers"]["timestamp"] == "1700000000000"
