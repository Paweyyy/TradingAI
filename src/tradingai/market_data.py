"""Kraken Futures REST client (stdlib only).

Provides the deterministic market data used to build the snapshot, plus signed
account/position/realized-PnL reads for the Risk Layer and evaluation. Market
data (charts, tickers) needs no key; account endpoints use Kraken's ``Authent``
signing.

Parsing and signing are pure functions, unit-tested without network access.

Kraken specifics:
- Perpetual symbols look like ``PF_XBTUSD`` (note: BTC is ``XBT`` on Kraken).
- Resolutions are strings: 1m, 5m, 15m, 30m, 1h, 4h, 12h, 1d, 1w.
- Demo/test environment: demo-futures.kraken.com (full sandbox).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .features import Kline

LIVE = "https://futures.kraken.com"
DEMO = "https://demo-futures.kraken.com"
FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"


def base_url(demo: bool) -> str:
    return DEMO if demo else LIVE


# --- pure helpers (unit-tested) ------------------------------------------
def sign_request(api_secret_b64: str, endpoint: str, nonce: str, post_data: str = "") -> str:
    """Kraken Futures ``Authent``:

    base64( HMAC-SHA512( base64decode(secret), SHA256(post_data + nonce + endpoint) ) )

    ``endpoint`` is the request path with any leading ``/derivatives`` removed.
    """
    sha = hashlib.sha256((post_data + nonce + endpoint).encode()).digest()
    mac = hmac.new(base64.b64decode(api_secret_b64), sha, hashlib.sha512).digest()
    return base64.b64encode(mac).decode()


def _sign_endpoint(path: str) -> str:
    prefix = "/derivatives"
    return path[len(prefix):] if path.startswith(prefix) else path


def parse_candles(payload: dict) -> list[Kline]:
    """Charts API candles -> oldest-first Klines."""
    rows = payload.get("candles", []) or []
    klines = [
        Kline(
            open=_f(c.get("open")) or 0.0,
            high=_f(c.get("high")) or 0.0,
            low=_f(c.get("low")) or 0.0,
            close=_f(c.get("close")) or 0.0,
            volume=_f(c.get("volume")) or 0.0,
        )
        for c in sorted(rows, key=lambda c: c.get("time", 0))
    ]
    return klines


def parse_ticker(payload: dict, symbol: str) -> dict:
    for t in payload.get("tickers", []) or []:
        if t.get("symbol", "").upper() == symbol.upper():
            # Kraken's `fundingRate` is absolute; `relativeFundingRate` is the
            # meaningful per-interval rate (~0.0001). Prefer the relative one.
            funding = t.get("relativeFundingRate")
            if funding is None:
                funding = t.get("fundingRate")
            return {
                "last_price": _f(t.get("last")) or _f(t.get("markPrice")),
                "funding_rate": _f(funding),
                "open_interest": _f(t.get("openInterest")),
            }
    return {}


def parse_accounts_equity(payload: dict) -> float | None:
    """Total equity from the multi-collateral 'flex' account."""
    flex = (payload.get("accounts", {}) or {}).get("flex", {}) or {}
    return _f(flex.get("portfolioValue")) or _f(flex.get("balanceValue"))


def parse_openpositions(payload: dict) -> list[dict]:
    out = []
    for p in payload.get("openPositions", []) or []:
        size = _f(p.get("size")) or 0.0
        if size > 0:
            out.append({
                "symbol": p.get("symbol"),
                "side": p.get("side"),       # "long" | "short"
                "size": size,
                "price": _f(p.get("price")),
            })
    return out


def parse_account_log_pnl(payload: dict) -> list[dict]:
    """Realized-PnL entries from the account log -> oldest-first trade records."""
    out = []
    for e in payload.get("logs", []) or []:
        pnl = _f(e.get("realized_pnl"))
        if pnl is None or pnl == 0.0:
            continue
        out.append({
            "symbol": e.get("contract") or e.get("asset"),
            "side": e.get("info"),
            "closed_pnl": pnl,
            "created_time": e.get("date"),
        })
    out.sort(key=lambda r: r.get("created_time") or "")
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
class KrakenClient:
    def __init__(self, demo: bool, api_key: str = "", api_secret: str = "",
                 timeout: int = 10, market_base: str | None = None) -> None:
        # Signed account/order calls go to the demo (or live) host.
        self.account_base = base_url(demo)
        # Public market data (charts/tickers) is served by the production host;
        # the demo host does not reliably serve it (returns 503). Demo prices
        # mirror live anyway. Overridable via KRAKEN_MARKET_BASE.
        self.market_base = market_base or os.environ.get("KRAKEN_MARKET_BASE", LIVE)
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._nonce = int(time.time() * 1000)

    def _next_nonce(self) -> str:
        self._nonce += 1
        return str(self._nonce)

    def _get(self, host: str, path: str, params: dict | None = None, signed: bool = False) -> dict:
        query = urllib.parse.urlencode(params or {})
        url = f"{host}{path}?{query}" if query else f"{host}{path}"
        headers = {"Accept": "application/json"}
        if signed:
            if not (self.api_key and self.api_secret):
                raise RuntimeError("API key/secret required for signed endpoint")
            nonce = self._next_nonce()
            authent = sign_request(self.api_secret, _sign_endpoint(path), nonce, query)
            headers.update({"APIKey": self.api_key, "Nonce": nonce, "Authent": authent})
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # surface status + which endpoint
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        if isinstance(body, dict) and body.get("result") == "error":
            raise RuntimeError(f"Kraken error from {url}: {body.get('error') or body.get('errors')}")
        return body

    # --- market data (keyless, production host) ---
    def klines(self, symbol: str, resolution: str, tick_type: str = "trade") -> list[Kline]:
        payload = self._get(self.market_base, f"/api/charts/v1/{tick_type}/{symbol}/{resolution}")
        return parse_candles(payload)

    def ticker(self, symbol: str) -> dict:
        payload = self._get(self.market_base, "/derivatives/api/v3/tickers")
        return parse_ticker(payload, symbol)

    # --- account data (signed, account host) ---
    def equity(self) -> float | None:
        return parse_accounts_equity(
            self._get(self.account_base, "/derivatives/api/v3/accounts", signed=True))

    def positions(self, symbol: str | None = None) -> list[dict]:
        payload = self._get(self.account_base, "/derivatives/api/v3/openpositions", signed=True)
        positions = parse_openpositions(payload)
        return [p for p in positions if symbol is None or p["symbol"] == symbol]

    def realized_pnl(self, symbol: str, limit: int = 100) -> list[dict]:
        payload = self._get(self.account_base, "/api/history/v3/account-log",
                            {"count": limit}, signed=True)
        trades = parse_account_log_pnl(payload)
        return [t for t in trades if t["symbol"] == symbol]


def fetch_fear_greed(timeout: int = 10) -> tuple[int | None, str | None]:
    """Free, keyless Fear & Greed Index. Fails soft (returns None, None)."""
    try:
        req = urllib.request.Request(FNG_URL, headers={"User-Agent": "tradingai"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return parse_fear_greed(json.loads(resp.read().decode()))
    except Exception:
        return None, None
