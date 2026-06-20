from dataclasses import dataclass

from tradingai import metrics


@dataclass
class T:
    pnl: float
    r_multiple: float | None = None


def test_win_rate():
    assert metrics.win_rate([T(10), T(-5), T(20), T(-1)]) == 50.0
    assert metrics.win_rate([]) == 0.0


def test_profit_factor():
    # gross profit 30, gross loss 10 -> 3.0
    assert metrics.profit_factor([T(20), T(10), T(-10)]) == 3.0


def test_profit_factor_no_losers_is_none():
    assert metrics.profit_factor([T(5), T(10)]) is None


def test_avg_r_uses_available():
    assert metrics.avg_r([T(10, 2.0), T(-5, -1.0)]) == 0.5
    assert metrics.avg_r([T(10), T(-5)]) is None  # no r data


def test_equity_curve_and_drawdown():
    trades = [T(100), T(-50), T(-30)]  # 1000 -> 1100 -> 1050 -> 1020
    curve = metrics.equity_curve(1000, trades)
    assert curve == [1000, 1100, 1050, 1020]
    # peak 1100, trough 1020 -> dd = (1020-1100)/1100*100
    assert round(metrics.max_drawdown_pct(curve), 4) == round((1020 - 1100) / 1100 * 100, 4)


def test_compute_full():
    trades = [T(100, 2.0), T(-50, -1.0)]
    m = metrics.compute(trades, initial_equity=1000)
    assert m.n_trades == 2
    assert m.wins == 1 and m.losses == 1
    assert m.total_pnl == 50
    assert m.final_equity == 1050
    assert m.total_return_pct == 5.0
    assert m.avg_r == 0.5
    d = m.as_dict()
    assert d["win_rate_pct"] == 50.0


def test_compute_empty():
    m = metrics.compute([], initial_equity=1000)
    assert m.n_trades == 0
    assert m.final_equity == 1000
    assert m.total_return_pct == 0.0
