"""Assemble a full MarketSnapshot from live Bybit data + free regime feeds.

This is the deterministic context-building step (PLAN.md §4 step 3): code fetches
data and computes indicators; Claude later consumes the result.
"""

from __future__ import annotations

from .config import Config
from .features import MarketSnapshot, build_timeframe_features
from .market_data import BybitClient, fetch_fear_greed
from .risk import AccountState
from .state import StateStore


def build_snapshot(cfg: Config, client: BybitClient, symbol: str) -> MarketSnapshot:
    """Fetch klines/ticker/regime for one symbol and compute features."""
    m, s = cfg.market, cfg.strategy
    trend_klines = client.klines(m.category, symbol, m.trend_timeframe, m.klines_limit)
    entry_klines = client.klines(m.category, symbol, m.entry_timeframe, m.klines_limit)
    trend_feats = build_timeframe_features(trend_klines, s)
    entry_feats = build_timeframe_features(entry_klines, s)

    ticker = client.ticker(m.category, symbol)
    fng, fng_label = fetch_fear_greed()

    snap = MarketSnapshot(
        symbol=symbol,
        trend_tf=trend_feats,
        entry_tf=entry_feats,
        funding_rate=ticker.get("funding_rate"),
        open_interest=ticker.get("open_interest"),
        fear_greed=fng,
        fear_greed_label=fng_label,
    )
    if ticker.get("last_price"):
        snap.notes.append(f"last_price={ticker['last_price']}")
    return snap


def build_account_state(cfg: Config, client: BybitClient, state: StateStore,
                        symbol: str, last_price: float | None) -> AccountState:
    """Build the Risk Layer's AccountState from wallet + positions + stored peaks."""
    equity = client.equity() or 0.0
    positions = client.positions(cfg.market.category, symbol)
    state.update_equity(equity)
    state.roll_day(equity)
    return AccountState(
        equity=equity,
        peak_equity=max(state.peak_equity, equity),
        day_start_equity=state.day_start_equity or equity,
        open_positions=len(positions),
        orders_this_tick=0,
        last_price=last_price,
    )
