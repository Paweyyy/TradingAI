"""Permission hook bridging Claude's tool calls to the Risk Layer.

The Agent SDK invokes ``can_use_tool`` before executing any tool. We let market
and account *read* tools through, deny withdrawal/transfer tools outright, and
route every order-mutating tool through :class:`RiskManager` for approval.
"""

from __future__ import annotations

from typing import Any, Callable

from .mcp_bybit import is_denied, is_order_mutating
from .risk import AccountState, OrderIntent, RiskManager


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


def make_permission_hook(
    risk: RiskManager,
    account_provider: Callable[[], AccountState],
    symbol_default: str,
) -> Callable[[str, dict], dict]:
    """Create a ``can_use_tool``-style callback for the Agent SDK.

    Returns a dict with ``behavior``: "allow" or "deny" (and a reason).
    """

    def can_use_tool(tool_name: str, tool_input: dict, *_: Any) -> dict:
        if is_denied(tool_name):
            return {"behavior": "deny", "message": f"{tool_name} is denied (no withdrawals/transfers in v1)"}

        if not is_order_mutating(tool_name):
            return {"behavior": "allow"}  # read-only market/account tools

        intent = _intent_from_tool_input(symbol_default, tool_input)
        acct = account_provider()
        result = risk.validate_order(intent, acct)
        if result.approved:
            return {"behavior": "allow"}
        return {"behavior": "deny", "message": "RISK BLOCK: " + "; ".join(result.reasons)}

    return can_use_tool
