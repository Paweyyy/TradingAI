"""Shared performance metrics.

Pure functions used by both the backtester and the live evaluator so the two
report the *same* numbers. Operates on any record exposing ``.pnl`` (float) and,
optionally, ``.r_multiple`` (float).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class TradeLike(Protocol):
    pnl: float


@dataclass
class PerformanceMetrics:
    n_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float | None
    avg_r: float | None
    max_drawdown_pct: float
    total_return_pct: float | None
    final_equity: float | None

    def as_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate_pct": round(self.win_rate_pct, 1),
            "total_pnl": round(self.total_pnl, 2),
            "avg_pnl": round(self.avg_pnl, 4),
            "profit_factor": round(self.profit_factor, 3) if self.profit_factor is not None else None,
            "avg_r": round(self.avg_r, 3) if self.avg_r is not None else None,
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "total_return_pct": round(self.total_return_pct, 2) if self.total_return_pct is not None else None,
            "final_equity": round(self.final_equity, 2) if self.final_equity is not None else None,
        }


def win_rate(trades: Sequence[TradeLike]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t.pnl > 0) / len(trades) * 100


def profit_factor(trades: Sequence[TradeLike]) -> float | None:
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss == 0:
        return None  # undefined (no losers)
    return gross_profit / gross_loss


def avg_r(trades: Sequence) -> float | None:
    rs = [t.r_multiple for t in trades if getattr(t, "r_multiple", None) is not None]
    if not rs:
        return None
    return sum(rs) / len(rs)


def equity_curve(initial_equity: float, trades: Sequence[TradeLike]) -> list[float]:
    """Cumulative equity after each trade's pnl."""
    curve = [initial_equity]
    eq = initial_equity
    for t in trades:
        eq += t.pnl
        curve.append(eq)
    return curve


def max_drawdown_pct(curve: Sequence[float]) -> float:
    """Largest peak-to-trough drop, as a non-positive percentage."""
    peak = curve[0] if curve else 0.0
    worst = 0.0
    for eq in curve:
        peak = max(peak, eq)
        if peak > 0:
            worst = min(worst, (eq - peak) / peak * 100)
    return worst


def compute(trades: Sequence, initial_equity: float | None = None,
            curve: Sequence[float] | None = None) -> PerformanceMetrics:
    """Compute the full metric set. Provide ``curve`` to reuse a precomputed one."""
    n = len(trades)
    total_pnl = sum(t.pnl for t in trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    if curve is None and initial_equity is not None:
        curve = equity_curve(initial_equity, trades)
    final_equity = curve[-1] if curve else None
    return PerformanceMetrics(
        n_trades=n,
        wins=wins,
        losses=n - wins,
        win_rate_pct=win_rate(trades),
        total_pnl=total_pnl,
        avg_pnl=total_pnl / n if n else 0.0,
        profit_factor=profit_factor(trades),
        avg_r=avg_r(trades),
        max_drawdown_pct=max_drawdown_pct(curve) if curve else 0.0,
        total_return_pct=((final_equity - initial_equity) / initial_equity * 100)
        if (initial_equity and final_equity is not None) else None,
        final_equity=final_equity,
    )
