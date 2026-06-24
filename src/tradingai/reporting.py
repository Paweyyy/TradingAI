"""Human-readable status reporting."""

from __future__ import annotations

from .state import StateStore


def format_status(state: StateStore) -> str:
    data = state._data  # noqa: SLF001 - internal read for reporting
    lines = [
        "=== TradingAI status ===",
        f"Day:               {data.get('day') or '-'}",
        f"Peak equity:       {data.get('peak_equity', 0.0):.2f}",
        f"Day-start equity:  {data.get('day_start_equity', 0.0):.2f}",
        f"Orders recorded:   {len(data.get('seen_order_ids', []))}",
        "",
        "Recent decisions:",
    ]
    decisions = data.get("decisions", [])[-10:]
    if not decisions:
        lines.append("  (none yet)")
    for d in decisions:
        lines.append(f"  [{d.get('ts', '?')}] {d.get('symbol', '?')} -> {d.get('action', '?')}: {d.get('rationale', '')}")
    return "\n".join(lines)
