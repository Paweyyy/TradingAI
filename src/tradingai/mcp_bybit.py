"""Bybit MCP server wiring for the Claude Agent SDK.

Builds the ``mcp_servers`` config that launches the official Bybit MCP server
(``bybit-official-trading-server``) as a stdio subprocess, injecting testnet
credentials from the environment. Market-data tools work without a key.
"""

from __future__ import annotations

import os

# Order-mutating tool name fragments. Any tool whose name matches one of these
# is routed through the Risk Layer before execution (see permissions.py).
ORDER_MUTATING_HINTS = (
    "place_order", "create_order", "amend_order", "cancel_order",
    "create_batch", "set_leverage", "set_trading_stop", "switch_",
)

# Tools we never allow the agent to call (no withdrawals/transfers in v1).
DENIED_HINTS = ("withdraw", "transfer", "create_sub", "create_api_key")


def bybit_mcp_servers(testnet: bool) -> dict:
    """Return the Agent SDK ``mcp_servers`` mapping for the Bybit MCP server."""
    env = {
        "BYBIT_TESTNET": "true" if testnet else "false",
    }
    # Credentials are optional for read-only market data; pass through if set.
    for key in ("BYBIT_API_KEY", "BYBIT_API_SECRET", "BYBIT_API_PRIVATE_KEY_PATH"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return {
        "bybit": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "bybit-official-trading-server@latest"],
            "env": env,
        }
    }


def is_order_mutating(tool_name: str) -> bool:
    name = tool_name.lower()
    return any(h in name for h in ORDER_MUTATING_HINTS)


def is_denied(tool_name: str) -> bool:
    name = tool_name.lower()
    return any(h in name for h in DENIED_HINTS)
