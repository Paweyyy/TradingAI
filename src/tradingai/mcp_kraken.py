"""Kraken MCP server wiring for the Claude Agent SDK.

Launches the official Kraken CLI's built-in MCP server (``krakenfx/kraken-cli``)
as a stdio subprocess, injecting API credentials and the demo flag from the
environment. The Kraken CLI is a separate binary the user installs; the launch
command is configurable because exact invocation can vary by version.

Market-data tools need no key; order-mutating tools are routed through the Risk
Layer (see permissions.py), and withdrawal/transfer tools are denied outright.
"""

from __future__ import annotations

import os

# Order-mutating tool name fragments -> routed through the Risk Layer.
ORDER_MUTATING_HINTS = (
    "send_order", "sendorder", "add_order", "addorder", "place_order",
    "create_order", "amend_order", "edit_order", "editorder", "cancel_order",
    "cancelorder", "batch_order", "batchorder", "set_leverage", "leverage_pref",
)

# Tools the agent may never call (no withdrawals/transfers in v1).
DENIED_HINTS = ("withdraw", "transfer", "subaccount", "sub_account", "create_api_key")


def kraken_mcp_servers(demo: bool) -> dict:
    """Return the Agent SDK ``mcp_servers`` mapping for the Kraken CLI MCP server."""
    command = os.environ.get("KRAKEN_MCP_COMMAND", "kraken")
    args = os.environ.get("KRAKEN_MCP_ARGS", "mcp").split()

    env = {"KRAKEN_DEMO": "true" if demo else "false"}
    # Pass credentials through to the CLI subprocess if present (keyless for market data).
    for key in ("KRAKEN_API_KEY", "KRAKEN_API_SECRET"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return {
        "kraken": {
            "type": "stdio",
            "command": command,
            "args": args,
            "env": env,
        }
    }


def is_order_mutating(tool_name: str) -> bool:
    name = tool_name.lower()
    return any(h in name for h in ORDER_MUTATING_HINTS)


def is_denied(tool_name: str) -> bool:
    name = tool_name.lower()
    return any(h in name for h in DENIED_HINTS)
