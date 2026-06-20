import hashlib
import hmac

from tradingai import market_data as md


def test_base_url_switch():
    assert md.base_url(True) == md.TESTNET
    assert md.base_url(False) == md.MAINNET


def test_sign_request_payload_order():
    # Signature must be HMAC over ts + api_key + recv_window + query, in that order.
    expected = hmac.new(b"secret", b"1700000000000KEY5000a=1&b=2", hashlib.sha256).hexdigest()
    got = md.sign_request("secret", "KEY", "1700000000000", "5000", "a=1&b=2")
    assert got == expected


def test_parse_klines_is_chronological():
    # Bybit returns newest-first; we must return oldest-first.
    result = {"list": [
        ["3", "3", "3", "3", "3", "30", "0"],
        ["2", "2", "2", "2", "2", "20", "0"],
        ["1", "1", "1", "1", "1", "10", "0"],
    ]}
    klines = md.parse_klines(result)
    assert [k.close for k in klines] == [1.0, 2.0, 3.0]


def test_parse_ticker():
    result = {"list": [{"lastPrice": "50000", "fundingRate": "0.0001", "openInterest": "1234"}]}
    t = md.parse_ticker(result)
    assert t["last_price"] == 50000.0
    assert t["funding_rate"] == 0.0001
    assert t["open_interest"] == 1234.0


def test_parse_ticker_empty():
    assert md.parse_ticker({"list": []}) == {}


def test_parse_wallet_equity():
    assert md.parse_wallet_equity({"list": [{"totalEquity": "1000.5"}]}) == 1000.5
    assert md.parse_wallet_equity({"list": []}) is None


def test_parse_positions_filters_flat():
    result = {"list": [
        {"symbol": "BTCUSDT", "side": "Buy", "size": "0.01", "unrealisedPnl": "5"},
        {"symbol": "ETHUSDT", "side": "None", "size": "0", "unrealisedPnl": "0"},
    ]}
    positions = md.parse_positions(result)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"


def test_parse_fear_greed():
    payload = {"data": [{"value": "72", "value_classification": "Greed"}]}
    val, label = md.parse_fear_greed(payload)
    assert val == 72 and label == "Greed"


def test_parse_fear_greed_empty():
    assert md.parse_fear_greed({"data": []}) == (None, None)


def test_float_coercion():
    assert md._f("1.5") == 1.5
    assert md._f("") is None
    assert md._f(None) is None
    assert md._f("abc") is None
