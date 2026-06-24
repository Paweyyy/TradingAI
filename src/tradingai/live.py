"""Live tick orchestration (Phase 3).

One tick: build the snapshot from live demo data, build AccountState, run the
circuit breakers, evaluate the deterministic rules, then hand the decision to
Claude via the Kraken MCP. Every order Claude attempts is gated by the permission
hook -> Risk Layer. Requires the Claude Agent SDK, Kraken demo keys, network.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .agent import run_tick
from .config import Config
from .logging_setup import log_event, setup_logging
from .market_data import KrakenClient
from .planning import build_order_plan
from .risk import AccountState, RiskManager
from .snapshot import build_account_state, build_snapshot
from .state import StateStore
from .strategy import evaluate


async def run_live_tick(cfg: Config) -> int:
    logger = setup_logging(cfg.runtime.log_level)
    if not cfg.mode.demo:
        raise RuntimeError("run_live_tick refused: not demo")

    client = KrakenClient(
        demo=True,
        api_key=os.environ["KRAKEN_API_KEY"],
        api_secret=os.environ["KRAKEN_API_SECRET"],
    )
    state = StateStore(cfg.runtime.state_dir)
    risk = RiskManager(cfg)

    for symbol in cfg.market.symbols:
        snap = build_snapshot(cfg, client, symbol)
        last_price = snap.trend_tf.closes_last
        acct = build_account_state(cfg, client, state, symbol, last_price)

        # Circuit breakers first — may trip the kill switch.
        breaker = risk.check_breakers(acct)
        if not breaker.approved:
            log_event(logger, "WARNING", "breaker tripped; skipping new entries",
                      symbol=symbol, reasons=breaker.reasons)
            _record(state, symbol, "HALT", "; ".join(breaker.reasons))
            continue

        setup = evaluate(snap, cfg.strategy)
        plan = build_order_plan(cfg, risk, setup, acct.equity, last_price)
        log_event(logger, "INFO", "tick evaluated", symbol=symbol,
                  trend=snap.trend_tf.trend, setup_valid=setup.valid,
                  planned_qty=(plan.qty if plan else None), reasons=setup.reasons)

        # A mutable account holder so the permission hook re-reads current state
        # (including orders_this_tick) at order time.
        holder = {"acct": acct}

        def account_provider() -> AccountState:
            return holder["acct"]

        if cfg.mode.dry_run:
            detail = f"plan={plan.as_dict()}" if plan else "; ".join(setup.reasons)
            _record(state, symbol, "DRY_RUN", detail)
            continue

        rationale = await run_tick(cfg, risk, account_provider, snap, setup, plan)
        log_event(logger, "INFO", "claude decision", symbol=symbol, rationale=rationale[:500])
        _record(state, symbol, "DECIDED", rationale[:300])

    return 0


def _record(state: StateStore, symbol: str, action: str, rationale: str) -> None:
    state.record_decision({
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "action": action,
        "rationale": rationale,
    })
