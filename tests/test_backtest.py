import math

from tradingai.backtest import Backtester, BacktestResult, _resample
from tradingai.config import Config
from tradingai.features import Kline


def _kline(close: float, spread: float = 5.0, vol: float = 100.0) -> Kline:
    return Kline(open=close, high=close + spread, low=close - spread, close=close, volume=vol)


def _uptrend(n: int = 400, start: float = 100.0, step: float = 0.5) -> list[Kline]:
    """A noisy but persistent uptrend so the trend filter and entries can fire."""
    out = []
    price = start
    for i in range(n):
        price += step + math.sin(i / 5) * step * 0.4  # drift up with wobble
        out.append(_kline(price, spread=step * 4, vol=100 + (i % 7) * 10))
    return out


def _flat(n: int = 400, level: float = 100.0) -> list[Kline]:
    out = []
    for i in range(n):
        price = level + math.sin(i / 4) * 2  # oscillate, no trend
        out.append(_kline(price, spread=3, vol=100 + (i % 5)))
    return out


def test_resample_factor():
    ks = [_kline(float(i)) for i in range(20)]
    r = _resample(ks, 4)
    assert len(r) == 5
    assert r[0].close == ks[3].close
    assert r[0].high == max(k.high for k in ks[:4])


def test_backtest_runs_and_returns_result():
    bt = Backtester(Config(), initial_equity=1000.0)
    res = bt.run(_uptrend())
    assert isinstance(res, BacktestResult)
    assert res.initial_equity == 1000.0
    assert len(res.equity_curve) > 0


def test_uptrend_produces_trades():
    bt = Backtester(Config(), initial_equity=1000.0)
    res = bt.run(_uptrend())
    assert res.n_trades > 0
    # All entries in an uptrend must be longs (trend filter).
    assert all(t.direction == "long" for t in res.trades)


def test_flat_market_trades_little_and_survives():
    bt = Backtester(Config(), initial_equity=1000.0)
    res = bt.run(_flat())
    # No persistent trend -> few/no trades; must not blow up the account.
    assert res.final_equity > 1000.0 * 0.5


def test_metrics_are_consistent():
    bt = Backtester(Config(), initial_equity=1000.0)
    res = bt.run(_uptrend())
    assert 0.0 <= res.win_rate <= 100.0
    assert res.max_drawdown_pct <= 0.0  # drawdown is negative-or-zero
    summary = res.summary()
    assert set(summary) >= {"trades", "total_return_pct", "win_rate_pct", "avg_r", "max_drawdown_pct"}


def test_risk_per_trade_respected_roughly():
    # With 1% risk on 1000, a single stop-out should lose on the order of ~1% (plus fees),
    # never a catastrophic fraction of equity.
    bt = Backtester(Config(), initial_equity=1000.0)
    res = bt.run(_uptrend())
    for t in res.trades:
        assert t.pnl > -100.0  # no single fill loses >10% of starting equity
