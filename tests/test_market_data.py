import base64
import hashlib
import hmac

from tradingai import market_data as md


def test_base_url_switch():
    assert md.base_url(True) == md.DEMO
    assert md.base_url(False) == md.LIVE


def test_sign_request_matches_reference():
    # Authent = base64(HMAC-SHA512(base64decode(secret), SHA256(post+nonce+endpoint)))
    secret_b64 = base64.b64encode(b"super-secret-key").decode()
    post, nonce, endpoint = "count=10", "1700000000001", "/api/v3/accounts"
    sha = hashlib.sha256((post + nonce + endpoint).encode()).digest()
    expected = base64.b64encode(
        hmac.new(base64.b64decode(secret_b64), sha, hashlib.sha512).digest()
    ).decode()
    assert md.sign_request(secret_b64, endpoint, nonce, post) == expected


def test_sign_endpoint_strips_derivatives():
    assert md._sign_endpoint("/derivatives/api/v3/accounts") == "/api/v3/accounts"
    assert md._sign_endpoint("/api/history/v3/account-log") == "/api/history/v3/account-log"


def test_parse_candles_is_chronological():
    payload = {"candles": [
        {"time": 3, "open": "3", "high": "3", "low": "3", "close": "3", "volume": "30"},
        {"time": 1, "open": "1", "high": "1", "low": "1", "close": "1", "volume": "10"},
        {"time": 2, "open": "2", "high": "2", "low": "2", "close": "2", "volume": "20"},
    ]}
    klines = md.parse_candles(payload)
    assert [k.close for k in klines] == [1.0, 2.0, 3.0]


def test_parse_ticker_finds_symbol():
    payload = {"tickers": [
        {"symbol": "PF_ETHUSD", "last": 3000, "fundingRate": 0.0, "openInterest": 1},
        {"symbol": "PF_XBTUSD", "last": 50000, "fundingRate": 0.0001, "openInterest": 1234},
    ]}
    t = md.parse_ticker(payload, "PF_XBTUSD")
    assert t["last_price"] == 50000.0
    assert t["funding_rate"] == 0.0001
    assert t["open_interest"] == 1234.0


def test_parse_ticker_missing_symbol():
    assert md.parse_ticker({"tickers": []}, "PF_XBTUSD") == {}


def test_parse_accounts_equity():
    payload = {"accounts": {"flex": {"portfolioValue": "1000.5", "balanceValue": "990"}}}
    assert md.parse_accounts_equity(payload) == 1000.5
    assert md.parse_accounts_equity({"accounts": {}}) is None


def test_parse_openpositions_filters_flat():
    payload = {"openPositions": [
        {"symbol": "PF_XBTUSD", "side": "long", "size": "0.01", "price": "50000"},
        {"symbol": "PF_ETHUSD", "side": "long", "size": "0", "price": "3000"},
    ]}
    positions = md.parse_openpositions(payload)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "PF_XBTUSD"


def test_parse_account_log_pnl_chronological():
    payload = {"logs": [
        {"contract": "PF_XBTUSD", "realized_pnl": "0.1", "date": "2", "info": "sell"},
        {"contract": "PF_XBTUSD", "realized_pnl": None, "date": "1.5"},  # skipped
        {"contract": "PF_XBTUSD", "realized_pnl": "-0.1", "date": "1", "info": "sell"},
    ]}
    trades = md.parse_account_log_pnl(payload)
    assert [t["created_time"] for t in trades] == ["1", "2"]
    assert trades[0]["closed_pnl"] == -0.1


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
