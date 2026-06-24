from tradingai.config import StrategyConfig
from tradingai.features import MarketSnapshot, TimeframeFeatures
from tradingai.strategy import Direction, evaluate


def _tf(trend, rsi=55, macd=1.0, vol_z=0.5, ema_entry=100.0, atr=50.0, close=101.0):
    return TimeframeFeatures(
        closes_last=close, ema_fast=100, ema_slow=90, ema_entry=ema_entry,
        rsi=rsi, atr=atr, macd_hist=macd, volume_z=vol_z, trend=trend,
    )


def _snap(trend="up", **entry_kw):
    return MarketSnapshot(
        symbol="PF_XBTUSD",
        trend_tf=_tf(trend),
        entry_tf=_tf(trend, **entry_kw),
        funding_rate=0.0001,
        fear_greed=55,
    )


def test_chop_stands_aside():
    setup = evaluate(_snap(trend="chop"), StrategyConfig())
    assert setup.valid is False
    assert setup.direction == Direction.NONE


def test_valid_long_pullback():
    setup = evaluate(_snap(trend="up", rsi=55, macd=1.0, vol_z=0.5), StrategyConfig())
    assert setup.valid is True
    assert setup.direction == Direction.LONG
    assert setup.stop_distance == 50.0 * 1.5


def test_long_blocked_by_weak_momentum_and_volume():
    setup = evaluate(_snap(trend="up", rsi=45, macd=-1.0, vol_z=-1.0), StrategyConfig())
    assert setup.valid is False


def test_long_blocked_by_extreme_funding():
    snap = _snap(trend="up")
    snap.funding_rate = 0.001  # above default 0.0005 threshold
    setup = evaluate(snap, StrategyConfig())
    assert setup.valid is False
    assert any("funding" in r for r in setup.reasons)


def test_long_blocked_by_extreme_greed():
    snap = _snap(trend="up")
    snap.fear_greed = 90
    setup = evaluate(snap, StrategyConfig())
    assert setup.valid is False
    assert any("greed" in r for r in setup.reasons)


def test_valid_short_in_downtrend():
    setup = evaluate(_snap(trend="down", rsi=45, macd=-1.0, vol_z=0.5), StrategyConfig())
    assert setup.valid is True
    assert setup.direction == Direction.SHORT
