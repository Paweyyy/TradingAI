"""Pure technical-indicator functions.

Deterministic, dependency-free (no pandas/numpy) so they are trivially testable
and cheap. Each takes plain ``list[float]`` series and returns a value or series.
Claude never recomputes these — it consumes their outputs (see SIGNALS.md).
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last ``period`` values."""
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    """Exponential moving average series (seeded with an SMA)."""
    if period <= 0 or len(values) < period:
        return []
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(values: list[float], period: int) -> float | None:
    """Latest EMA value."""
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(values: list[float], period: int = 14) -> float | None:
    """Wilder's RSI of the latest bar. Returns 0..100."""
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    trs: list[float] = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))
    return trs


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Average True Range (Wilder smoothing) of the latest bar."""
    trs = true_ranges(highs, lows, closes)
    if len(trs) < period:
        return None
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


def macd_histogram(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float | None:
    """Latest MACD histogram value (macd_line - signal_line)."""
    fast_s = ema_series(values, fast)
    slow_s = ema_series(values, slow)
    if not fast_s or not slow_s:
        return None
    n = min(len(fast_s), len(slow_s))
    macd_line = [fast_s[-n + i] - slow_s[-n + i] for i in range(n)]
    signal_s = ema_series(macd_line, signal)
    if not signal_s:
        return None
    return macd_line[-1] - signal_s[-1]


def volume_zscore(volumes: list[float], period: int = 20) -> float | None:
    """How many std-devs the latest volume is above its rolling mean."""
    if len(volumes) < period + 1:
        return None
    window = volumes[-period - 1 : -1]  # exclude the latest bar from the baseline
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / period
    std = var ** 0.5
    if std == 0:
        return 0.0
    return (volumes[-1] - mean) / std
