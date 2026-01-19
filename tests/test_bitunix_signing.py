from exchange_client.adapters.bitunix import BitunixFuturesClient

def test_signing_is_deterministic():
    c = BitunixFuturesClient(api_key="APIKEY", secret_key="SECRET")

    nonce = "n" * 32
    timestamp = "1700000000000"

    # ASCII-sorted => a then b
    query = c._canonical_query({"b": 2, "a": 1})
    assert query == "a=1b=2"

    body = c._compact_json({"x": 1, "y": 2})
    assert body == '{"x":1,"y":2}'

    s1 = c._sign(nonce, timestamp, query, body)
    s2 = c._sign(nonce, timestamp, query, body)
    assert s1 == s2
    assert len(s1) == 64
