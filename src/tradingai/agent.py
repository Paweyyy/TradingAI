"""Claude Agent SDK integration.

Builds the agent options (Bybit MCP server + permission hook + strategy prompt)
and runs a single decision tick. The SDK import is guarded so the deterministic
core and its tests do not require the SDK to be installed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import Config
from .features import MarketSnapshot
from .mcp_bybit import bybit_mcp_servers
from .permissions import make_permission_hook
from .risk import AccountState, RiskManager
from .strategy import TradeSetup


def load_strategy_prompt(cfg: Config) -> str:
    path = Path(cfg.strategy.prompt_file)
    return path.read_text() if path.exists() else "You are a cautious trend-following trading assistant."


def build_tick_prompt(snapshot: MarketSnapshot, setup: TradeSetup) -> str:
    """Compose the user prompt for one decision tick."""
    return (
        "Market snapshot (indicators already computed — do not recompute):\n"
        f"{json.dumps(snapshot.as_dict(), indent=2)}\n\n"
        "Deterministic rule evaluation:\n"
        f"{json.dumps(setup.as_dict(), indent=2)}\n\n"
        "Decide one of HOLD / OPEN_LONG / OPEN_SHORT / CLOSE / ADJUST. "
        "If you open, you may call the Bybit order tools; the Risk Layer will size "
        "and authorize. Give a 1-3 sentence rationale citing snapshot fields. "
        "When in doubt, HOLD."
    )


def build_agent_options(
    cfg: Config,
    risk: RiskManager,
    account_provider: Callable[[], AccountState],
):
    """Construct ClaudeAgentOptions. Raises if the SDK is not installed."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only with extras
        raise RuntimeError(
            "claude-agent-sdk not installed. Install with: pip install '.[agent]'"
        ) from exc

    symbol_default = cfg.market.symbols[0]
    hook = make_permission_hook(risk, account_provider, symbol_default)
    return ClaudeAgentOptions(
        model=cfg.runtime.model,
        system_prompt=load_strategy_prompt(cfg),
        mcp_servers=bybit_mcp_servers(cfg.mode.testnet),
        can_use_tool=hook,
    )


async def run_tick(
    cfg: Config,
    risk: RiskManager,
    account_provider: Callable[[], AccountState],
    snapshot: MarketSnapshot,
    setup: TradeSetup,
) -> str:
    """Run one Claude decision tick. Returns the textual rationale/result."""
    from claude_agent_sdk import query  # type: ignore

    options = build_agent_options(cfg, risk, account_provider)
    prompt = build_tick_prompt(snapshot, setup)
    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        text = getattr(message, "text", None) or getattr(message, "content", None)
        if text:
            chunks.append(str(text))
    return "\n".join(chunks)
