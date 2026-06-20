"""Live performance evaluation (Phase 5).

Turns realized Bybit trades (closed-PnL) into the same performance metrics the
backtester reports, and summarizes bot activity from the decision log. This is
the evidence for the go-live gate in STRATEGY.md.

Note: closed-PnL has no per-trade R (we'd need the original stop), so ``avg_r``
is reported only when available; live eval is primarily PnL-based.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from . import metrics


@dataclass
class RealizedTrade:
    symbol: str
    side: str
    pnl: float
    r_multiple: float | None = None  # usually unavailable from closed-pnl

    @classmethod
    def from_closed_pnl(cls, rec: dict) -> "RealizedTrade":
        return cls(symbol=rec.get("symbol", "?"), side=rec.get("side", "?"),
                   pnl=float(rec.get("closed_pnl", 0.0)))


def summarize_decisions(decisions: list[dict]) -> dict:
    """Activity breakdown from the logged decisions."""
    actions = Counter(d.get("action", "?") for d in decisions)
    return {
        "total_decisions": len(decisions),
        "by_action": dict(actions),
        "last_decision": decisions[-1] if decisions else None,
    }


def evaluate(closed_pnl: list[dict], decisions: list[dict],
             initial_equity: float) -> dict:
    """Build the full evaluation report."""
    trades = [RealizedTrade.from_closed_pnl(r) for r in closed_pnl]
    curve = metrics.equity_curve(initial_equity, trades)
    perf = metrics.compute(trades, initial_equity=initial_equity, curve=curve)
    return {
        "performance": perf.as_dict(),
        "activity": summarize_decisions(decisions),
        "go_live_gate": _gate(perf),
    }


def _gate(perf: metrics.PerformanceMetrics) -> dict:
    """Evaluate the STRATEGY.md go-live criteria. Informational, not authoritative."""
    enough_trades = perf.n_trades >= 30
    positive_expectancy = perf.total_pnl > 0
    drawdown_ok = perf.max_drawdown_pct > -15.0
    passed = enough_trades and positive_expectancy and drawdown_ok
    return {
        "enough_trades (>=30)": enough_trades,
        "positive_expectancy": positive_expectancy,
        "drawdown_within_15pct": drawdown_ok,
        "PASS": passed,
        "note": "Informational. Real capital is a separate, deliberate decision.",
    }


def format_report(report: dict) -> str:
    import json

    return json.dumps(report, indent=2)
