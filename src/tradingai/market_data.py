"""Bybit V5 REST client (stdlib only).

Provides the deterministic market data used to build the snapshot, plus signed
account/position reads for the Risk Layer's AccountState. Market-data endpoints
need no API key; account endpoints are HMAC-signed.

Parsing and signing are factored into pure functions so they can be unit-tested
without network access.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .features import Kline

MAINNET = "https://api.bybit.com"
TESTNET = "https://api-testnet.bybit.com"
FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"


def base_url(testnet: bool) -> str:
    return TESTNET if testnet else MAINNET


# --- pure helpers (unit-tested) ------------------------------------------
def sign_request(secret: str, api_key: str, timestamp: str, recv_window: str, query: str) -> str:
    """Bybit V5 signature: HMAC_SHA256(secret, ts + api_key + recv_window + query)."""
    payload = f"{timestamp}{api_key}{recv_window}{query}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def parse_klines(result: dict) -> list[Kline]:
    """Bybit returns klines newest-first; we return them oldest-first."""
    rows = result.get("list", [])
    klines = [Kline.from_bybit(r) for r in rows]
    klines.reverse()
    return klines


def parse_ticker(result: dict) -> dict:
    rows = result.get("list", [])
    if not rows:
        return {}
    t = rows[0]
    return {
        "last_price": _f(t.get("lastPrice")),
        "funding_rate": _f(t.get("fundingRate")),
        "open_interest": _f(t.get("openInterest")),
    }


def parse_wallet_equity(result: dict) -> float | None:
    """Total equity from a UNIFIED wallet-balance response."""
    rows = result.get("list", [])
    if not rows:
        return None
    return _f(rows[0].get("totalEquity"))


def parse_closed_pnl(result: dict) -> list[dict]:
    """Realized trades from /v5/position/closed-pnl (newest-first -> oldest-first)."""
    out = []
    for r in result.get("list", []):
        out.append({
            "symbol": r.get("symbol"),
            "side": r.get("side"),
            "qty": _f(r.get("qty")),
            "avg_entry": _f(r.get("avgEntryPrice")),
            "avg_exit": _f(r.get("avgExitPrice")),
            "closed_pnl": _f(r.get("closedPnl")) or 0.0,
            "created_time": r.get("createdTime"),
        })
    out.reverse()
    return out


def parse_positions(result: dict) -> list[dict]:
    out = []
    for p in result.get("list", []):
        size = _f(p.get("size")) or 0.0
        if size > 0:
            out.append({
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "size": size,
                "unrealised_pnl": _f(p.get("unrealisedPnl")),
            })
    return out


def parse_fear_greed(payload: dict) -> tuple[int | None, str | None]:
    data = payload.get("data", [])
    if not data:
        return None, None
    return int(data[0]["value"]), data[0].get("value_classification")


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --- HTTP client ----------------------------------------------------------
class BybitClient:
    def __init__(self, testnet: bool, api_key: str = "", api_secret: str = "",
                 recv_window: str = "5000", timeout: int = 10) -> None:
        self.base = base_url(testnet)
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
        self.timeout = timeout

    def _get(self, path: str, params: dict, signed: bool = False) -> dict:
        query = urllib.parse.urlencode(params)
        url = f"{self.base}{path}?{query}" if query else f"{self.base}{path}"
        headers = {"Content-Type": "application/json"}
        if signed:
            if not (self.api_key and self.api_secret):
                raise RuntimeError("API key/secret required for signed endpoint")
            ts = str(int(time.time() * 1000))
            sig = sign_request(self.api_secret, self.api_key, ts, self.recv_window, query)
            headers.update({
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": self.recv_window,
                "X-BAPI-SIGN": sig,
            })
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode())
        if body.get("retCode", 0) != 0:
            raise RuntimeError(f"Bybit error {body.get('retCode')}: {body.get('retMsg')}")
        return body.get("result", {})

    # --- market data (keyless) ---
    def klines(self, category: str, symbol: str, interval: str, limit: int = 250) -> list[Kline]:
        result = self._get("/v5/market/kline",
                           {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
        return parse_klines(result)

    def ticker(self, category: str, symbol: str) -> dict:
        result = self._get("/v5/market/tickers", {"category": category, "symbol": symbol})
        return parse_ticker(result)

    # --- account data (signed) ---
    def equity(self, account_type: str = "UNIFIED") -> float | None:
        result = self._get("/v5/account/wallet-balance", {"accountType": account_type}, signed=True)
        return parse_wallet_equity(result)

    def positions(self, category: str, symbol: str) -> list[dict]:
        result = self._get("/v5/position/list", {"category": category, "symbol": symbol}, signed=True)
        return parse_positions(result)

    def closed_pnl(self, category: str, symbol: str, limit: int = 100) -> list[dict]:
        result = self._get("/v5/position/closed-pnl",
                           {"category": category, "symbol": symbol, "limit": limit}, signed=True)
        return parse_closed_pnl(result)


def fetch_fear_greed(timeout: int = 10) -> tuple[int | None, str | None]:
    """Free, keyless Fear & Greed Index. Fails soft (returns None,None)."""
    try:
        req = urllib.request.Request(FNG_URL, headers={"User-Agent": "tradingai"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return parse_fear_greed(json.loads(resp.read().decode()))
    except Exception:
        return None, None
