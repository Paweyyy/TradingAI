"""Build the compact, structured market snapshot fed to Claude.

Indicators are computed deterministically here (see ``indicators.py``); Claude
consumes the resulting feature dict and never recomputes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import indicators as ind
from .config import StrategyConfig


@dataclass
class Kline:
    """One OHLCV candle. Mirrors Bybit V5 kline fields we care about."""

    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_bybit(cls, row: list) -> "Kline":
        # Bybit V5 kline row: [start, open, high, low, close, volume, turnover]
        return cls(
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )


@dataclass
class TimeframeFeatures:
    closes_last: float
    ema_fast: float | None
    ema_slow: float | None
    ema_entry: float | None
    rsi: float | None
    atr: float | None
    macd_hist: float | None
    volume_z: float | None
    trend: str  # "up" | "down" | "chop"

    def as_dict(self) -> dict:
        return {
            "close": round(self.closes_last, 4),
            "ema_fast": _r(self.ema_fast),
            "ema_slow": _r(self.ema_slow),
            "ema_entry": _r(self.ema_entry),
            "rsi": _r(self.rsi, 2),
            "atr": _r(self.atr),
            "macd_hist": _r(self.macd_hist, 4),
            "volume_z": _r(self.volume_z, 2),
            "trend": self.trend,
        }


@dataclass
class MarketSnapshot:
    symbol: str
    trend_tf: TimeframeFeatures
    entry_tf: TimeframeFeatures
    funding_rate: float | None = None
    open_interest: float | None = None
    open_interest_change: float | None = None
    long_short_ratio: float | None = None
    fear_greed: int | None = None
    fear_greed_label: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "trend_tf": self.trend_tf.as_dict(),
            "entry_tf": self.entry_tf.as_dict(),
            "derivatives": {
                "funding_rate": _r(self.funding_rate, 6),
                "open_interest": _r(self.open_interest),
                "open_interest_change": _r(self.open_interest_change, 4),
                "long_short_ratio": _r(self.long_short_ratio, 3),
            },
            "regime": {
                "fear_greed": self.fear_greed,
                "fear_greed_label": self.fear_greed_label,
            },
            "notes": self.notes,
        }


def _r(v: float | None, ndigits: int = 2) -> float | None:
    return round(v, ndigits) if v is not None else None


def _classify_trend(closes: list[float], cfg: StrategyConfig) -> tuple[str, TimeframeFeatures]:
    ema_fast = ind.ema(closes, cfg.ema_fast)
    ema_slow = ind.ema(closes, cfg.ema_slow)
    last = closes[-1]
    trend = "chop"
    if ema_fast is not None and ema_slow is not None:
        if ema_fast > ema_slow and last > ema_fast:
            trend = "up"
        elif ema_fast < ema_slow and last < ema_fast:
            trend = "down"
    return trend, TimeframeFeatures(
        closes_last=last,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        ema_entry=ind.ema(closes, cfg.ema_entry),
        rsi=ind.rsi(closes, cfg.rsi_period),
        atr=None,  # filled by caller (needs HLC)
        macd_hist=ind.macd_histogram(closes),
        volume_z=None,  # filled by caller (needs volume)
        trend=trend,
    )


def build_timeframe_features(klines: list[Kline], cfg: StrategyConfig) -> TimeframeFeatures:
    """Compute the per-timeframe feature block from OHLCV candles."""
    closes = [k.close for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    volumes = [k.volume for k in klines]
    _, feats = _classify_trend(closes, cfg)
    feats.atr = ind.atr(highs, lows, closes, cfg.atr_period)
    feats.volume_z = ind.volume_zscore(volumes, cfg.volume_ma_period)
    return feats
