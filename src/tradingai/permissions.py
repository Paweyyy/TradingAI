"""Permission hook bridging Claude's tool calls to the Risk Layer.

The Agent SDK invokes ``can_use_tool`` before executing any tool. We let market
and account *read* tools through, deny withdrawal/transfer tools outright, and
route every order-mutating tool through :class:`RiskManager` for approval.
"""

from __future__ import annotations

from typing import Any, Callable

from .mcp_bybit import is_denied, is_order_mutating
from .planning import OrderPlan
from .risk import AccountState, OrderIntent, RiskManager

# Allowed relative deviation between a submitted qty and the planned qty.
QTY_TOLERANCE = 0.02  # 2%


def _intent_from_tool_input(symbol_default: str, tool_input: dict) -> OrderIntent:
    """Best-effort mapping of a Bybit order tool input to an OrderIntent."""
    return OrderIntent(
        symbol=tool_input.get("symbol", symbol_default),
        side=tool_input.get("side", "Buy"),
        qty=float(tool_input.get("qty", 0) or 0),
        price=float(tool_input.get("price", 0) or 0),
        leverage=float(tool_input.get("leverage", 1) or 1),
        reduce_only=bool(tool_input.get("reduceOnly", False)),
    )


def _matches_plan(intent: OrderIntent, plan: OrderPlan) -> list[str]:
    """Return reasons the order deviates from the deterministic plan (empty = ok)."""
    problems: list[str] = []
    if intent.reduce_only:
        return problems  # closes/reduces are not size-pinned to an entry plan
    if intent.side != plan.side:
        problems.append(f"side {intent.side} != planned {plan.side}")
    if plan.qty > 0:
        deviation = abs(intent.qty - plan.qty) / plan.qty
        if deviation > QTY_TOLERANCE:
            problems.append(f"qty {intent.qty} != planned {plan.qty} (>{QTY_TOLERANCE:.0%})")
    return problems


def make_permission_hook(
    risk: RiskManager,
    account_provider: Callable[[], AccountState],
    symbol_default: str,
    plan_provider: Callable[[], OrderPlan | None] | None = None,
) -> Callable[[str, dict], dict]:
    """Create a ``can_use_tool``-style callback for the Agent SDK.

    Returns a dict with ``behavior``: "allow" or "deny" (and a reason). Opening
    orders must match the deterministic :class:`OrderPlan` (side + sized qty);
    Claude confirms the trade, it does not choose the size.
    """

    def can_use_tool(tool_name: str, tool_input: dict, *_: Any) -> dict:
        if is_denied(tool_name):
            return {"behavior": "deny", "message": f"{tool_name} is denied (no withdrawals/transfers in v1)"}

        if not is_order_mutating(tool_name):
            return {"behavior": "allow"}  # read-only market/account tools

        intent = _intent_from_tool_input(symbol_default, tool_input)
        acct = account_provider()
        result = risk.validate_order(intent, acct)
        if not result.approved:
            return {"behavior": "deny", "message": "RISK BLOCK: " + "; ".join(result.reasons)}

        plan = plan_provider() if plan_provider else None
        if plan is not None:
            deviations = _matches_plan(intent, plan)
            if deviations:
                return {"behavior": "deny", "message": "PLAN MISMATCH: " + "; ".join(deviations)}
        elif not intent.reduce_only:
            # No valid setup this tick -> no opening order should be attempted.
            return {"behavior": "deny", "message": "NO PLAN: no valid setup for an opening order this tick"}

        return {"behavior": "allow"}

    return can_use_tool
