"""Permission hook bridging Claude's tool calls to the Risk Layer.

The Agent SDK invokes ``can_use_tool`` before executing any tool. We let market
and account *read* tools through, deny withdrawal/transfer tools outright, and
route every order-mutating tool through :class:`RiskManager`.

Sizing is authoritative and deterministic: for an opening order the hook
**overwrites** the submitted side/qty/leverage with the pre-computed
:class:`OrderPlan` via ``updatedInput`` — Claude cannot under/over-size. As a
safety net (in case a host ignores ``updatedInput``), the originally submitted
order must also independently pass the Risk Layer.
"""

from __future__ import annotations

from typing import Any, Callable

from .mcp_kraken import is_denied, is_order_mutating
from .planning import OrderPlan
from .risk import AccountState, OrderIntent, RiskManager


def _intent_from_tool_input(symbol_default: str, tool_input: dict) -> OrderIntent:
    """Best-effort mapping of a Kraken order tool input to an OrderIntent.

    Kraken uses ``size`` and ``limitPrice``; we also accept ``qty``/``price``.
    """
    return OrderIntent(
        symbol=tool_input.get("symbol", symbol_default),
        side=tool_input.get("side", "buy"),
        qty=float(tool_input.get("size", tool_input.get("qty", 0)) or 0),
        price=float(tool_input.get("limitPrice", tool_input.get("price", 0)) or 0),
        leverage=float(tool_input.get("leverage", 1) or 1),
        reduce_only=bool(tool_input.get("reduceOnly", False)),
    )


def _fmt_qty(qty: float) -> str:
    return f"{qty:.10f}".rstrip("0").rstrip(".")


def _planned_input(tool_input: dict, plan: OrderPlan) -> dict:
    """A copy of the tool input with size/side forced to the plan."""
    corrected = dict(tool_input)
    corrected["symbol"] = plan.symbol
    corrected["side"] = plan.side
    # Set Kraken's field name; mirror to qty if the host used that key.
    corrected["size"] = _fmt_qty(plan.qty)
    if "qty" in corrected:
        corrected["qty"] = _fmt_qty(plan.qty)
    return corrected


def _allow(updated: dict | None = None) -> dict:
    res: dict = {"behavior": "allow"}
    if updated is not None:
        # Provide both casings for cross-version SDK compatibility.
        res["updatedInput"] = updated
        res["updated_input"] = updated
    return res


def _deny(message: str) -> dict:
    return {"behavior": "deny", "message": message}


def make_permission_hook(
    risk: RiskManager,
    account_provider: Callable[[], AccountState],
    symbol_default: str,
    plan_provider: Callable[[], OrderPlan | None] | None = None,
) -> Callable[[str, dict], dict]:
    """Create a ``can_use_tool``-style callback for the Agent SDK."""

    def can_use_tool(tool_name: str, tool_input: dict, *_: Any) -> dict:
        if is_denied(tool_name):
            return _deny(f"{tool_name} is denied (no withdrawals/transfers in v1)")

        if not is_order_mutating(tool_name):
            return _allow()  # read-only market/account tools

        intent = _intent_from_tool_input(symbol_default, tool_input)
        acct = account_provider()

        # Closes / reduce-only orders are not pinned to an entry plan.
        if intent.reduce_only:
            res = risk.validate_order(intent, acct)
            return _allow() if res.approved else _deny("RISK BLOCK: " + "; ".join(res.reasons))

        # Opening orders require a valid setup -> a plan.
        plan = plan_provider() if plan_provider else None
        if plan is None:
            return _deny("NO PLAN: no valid setup for an opening order this tick")

        # Never silently flip direction relative to the deterministic setup.
        if intent.side.lower() != plan.side.lower():
            return _deny(f"PLAN MISMATCH: side {intent.side} != planned {plan.side}")

        # The authoritative (planned) order must pass risk.
        planned_intent = OrderIntent(
            symbol=plan.symbol, side=plan.side, qty=plan.qty,
            price=plan.entry_price, leverage=plan.leverage,
        )
        res = risk.validate_order(planned_intent, acct)
        if not res.approved:
            return _deny("RISK BLOCK: " + "; ".join(res.reasons))

        # Safety net: if the host ignores our size injection and runs the
        # submitted order as-is, that order must also be within limits.
        orig = risk.validate_order(intent, acct)
        if not orig.approved:
            return _deny("RISK BLOCK (submitted order): " + "; ".join(orig.reasons))

        # Force the exact planned size/side/leverage onto the executed order.
        return _allow(_planned_input(tool_input, plan))

    return can_use_tool
