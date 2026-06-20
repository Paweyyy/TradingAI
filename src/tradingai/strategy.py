"""Deterministic strategy rules (the part Claude does NOT decide).

Given a :class:`MarketSnapshot`, evaluate the higher-timeframe trend-following
rules from STRATEGY.md and emit a candidate setup. Claude later confirms or
vetoes this; the Risk Layer sizes and authorizes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import StrategyConfig
from .features import MarketSnapshot


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class TradeSetup:
    symbol: str
    direction: Direction
    valid: bool
    reasons: list[str]
    stop_distance: float | None = None  # price units, from ATR

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "valid": self.valid,
            "reasons": self.reasons,
            "stop_distance": round(self.stop_distance, 4) if self.stop_distance else None,
        }


def evaluate(snapshot: MarketSnapshot, cfg: StrategyConfig) -> TradeSetup:
    """Evaluate entry rules. Returns a setup with ``valid`` and the reasons."""
    reasons: list[str] = []
    trend = snapshot.trend_tf.trend

    # 1. Trend filter (4h) decides allowed direction.
    if trend == "up":
        direction = Direction.LONG
    elif trend == "down":
        direction = Direction.SHORT
    else:
        return TradeSetup(snapshot.symbol, Direction.NONE, False, ["4h trend is chop; stand aside"])

    e = snapshot.entry_tf
    if e.ema_entry is None or e.rsi is None or e.atr is None:
        return TradeSetup(snapshot.symbol, direction, False, ["insufficient entry-tf data"])

    long_side = direction == Direction.LONG

    # 2. Pullback that resumes: price near/through EMA20 with momentum turning in-trend.
    momentum_ok = (e.rsi > 50) if long_side else (e.rsi < 50)
    macd_ok = (e.macd_hist or 0) > 0 if long_side else (e.macd_hist or 0) < 0
    if not (momentum_ok or macd_ok):
        reasons.append("momentum not yet resuming in trend direction")

    # 3. Volume confirmation.
    volume_ok = (e.volume_z or 0) >= 0
    if not volume_ok:
        reasons.append("entry volume below average")

    # 4. Funding guard: do not enter same side as crowded funding.
    funding_block = False
    if snapshot.funding_rate is not None:
        fr = snapshot.funding_rate
        if long_side and fr > cfg.funding_extreme_abs:
            funding_block = True
            reasons.append(f"funding extremely positive ({fr:.4%}); skip long")
        if not long_side and fr < -cfg.funding_extreme_abs:
            funding_block = True
            reasons.append(f"funding extremely negative ({fr:.4%}); skip short")

    # 5. Sentiment guard at extremes.
    sentiment_block = False
    if cfg.sentiment_guard and snapshot.fear_greed is not None:
        fng = snapshot.fear_greed
        if long_side and fng >= cfg.fng_extreme_greed:
            sentiment_block = True
            reasons.append(f"extreme greed ({fng}); skip new long")
        if not long_side and fng <= cfg.fng_extreme_fear:
            sentiment_block = True
            reasons.append(f"extreme fear ({fng}); skip new short")

    valid = (momentum_ok or macd_ok) and volume_ok and not funding_block and not sentiment_block
    if valid:
        reasons.append(f"valid {direction.value} pullback in {trend}trend")

    stop_distance = e.atr * cfg.atr_stop_mult
    return TradeSetup(snapshot.symbol, direction, valid, reasons, stop_distance)
