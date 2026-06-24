"""CLI entrypoint: validate config, print a status report, or run a tick.

    tradingai check    # validate config + environment (no network)
    tradingai status   # print state report
    tradingai tick     # run one live decision tick (needs SDK + keys + network)

v1 refuses to run live unless KRAKEN_DEMO=true.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import Config, load_config
from .logging_setup import log_event, setup_logging
from .reporting import format_status
from .state import StateStore


def _assert_demo(cfg: Config) -> None:
    env_demo = os.environ.get("KRAKEN_DEMO", "").lower() == "true"
    if not (cfg.mode.demo and env_demo):
        raise SystemExit(
            "REFUSING TO RUN: v1 is demo-only. Set KRAKEN_DEMO=true and mode.demo: true."
        )


def cmd_check(cfg: Config) -> int:
    logger = setup_logging(cfg.runtime.log_level)
    log_event(logger, "INFO", "config loaded",
              symbols=cfg.market.symbols, demo=cfg.mode.demo,
              risk_pct=cfg.risk.risk_per_trade_pct, leverage_cap=cfg.risk.leverage_cap)
    env_demo = os.environ.get("KRAKEN_DEMO", "").lower() == "true"
    has_keys = bool(os.environ.get("KRAKEN_API_KEY"))
    print("Config valid.")
    print(f"  demo (config): {cfg.mode.demo}")
    print(f"  KRAKEN_DEMO env: {env_demo}")
    print(f"  Kraken API key set: {has_keys} (not needed for market-data-only)")
    print(f"  symbols: {cfg.market.symbols}  cadence: {cfg.runtime.cadence_minutes}m")
    if not (cfg.mode.demo and env_demo):
        print("  WARNING: not in demo mode; live tick will be refused.")
    return 0


def cmd_status(cfg: Config) -> int:
    state = StateStore(cfg.runtime.state_dir)
    print(format_status(state))
    return 0


def cmd_snapshot(cfg: Config) -> int:
    """Fetch live demo market data and print snapshot + rule evaluation.

    Keyless (market data only) and SDK-free — for validating the data path.
    """
    import json
    import urllib.error

    from .market_data import KrakenClient
    from .snapshot import build_snapshot
    from .strategy import evaluate

    demo = cfg.mode.demo and os.environ.get("KRAKEN_DEMO", "").lower() == "true"
    client = KrakenClient(demo=demo,
                          api_key=os.environ.get("KRAKEN_API_KEY", ""),
                          api_secret=os.environ.get("KRAKEN_API_SECRET", ""))
    try:
        for symbol in cfg.market.symbols:
            snap = build_snapshot(cfg, client, symbol)
            setup = evaluate(snap, cfg.strategy)
            print(json.dumps({"snapshot": snap.as_dict(), "setup": setup.as_dict()}, indent=2))
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Could not reach Kraken ({base_url_hint(demo)}): {exc}")
        print("Run this from an environment with outbound access to Kraken Futures.")
        return 1
    return 0


def base_url_hint(demo: bool) -> str:
    from .market_data import base_url

    return base_url(demo)


def cmd_report(cfg: Config) -> int:
    """Evaluate realized demo performance + bot activity."""
    import urllib.error

    from .evaluation import evaluate, format_report
    from .market_data import KrakenClient
    from .state import StateStore

    state = StateStore(cfg.runtime.state_dir)
    decisions = state._data.get("decisions", [])  # noqa: SLF001
    initial_equity = state.day_start_equity or state.peak_equity or 1000.0

    closed: list[dict] = []
    if os.environ.get("KRAKEN_API_KEY"):
        demo = cfg.mode.demo and os.environ.get("KRAKEN_DEMO", "").lower() == "true"
        client = KrakenClient(demo=demo,
                              api_key=os.environ["KRAKEN_API_KEY"],
                              api_secret=os.environ.get("KRAKEN_API_SECRET", ""))
        try:
            for symbol in cfg.market.symbols:
                closed.extend(client.realized_pnl(symbol))
        except (urllib.error.URLError, RuntimeError) as exc:
            print(f"(could not fetch realized trades: {exc}; reporting from decision log only)")
    else:
        print("(no KRAKEN_API_KEY; reporting activity from decision log only)")

    print(format_report(evaluate(closed, decisions, initial_equity)))
    return 0


def cmd_run(cfg: Config) -> int:
    """Run the autonomous scheduler loop (demo-only)."""
    _assert_demo(cfg)
    if not os.environ.get("KRAKEN_API_KEY"):
        raise SystemExit("Scheduler needs KRAKEN_API_KEY/SECRET (demo) for account state and orders.")
    from .scheduler import run_forever

    return run_forever(cfg)


def cmd_tick(cfg: Config) -> int:
    import asyncio

    _assert_demo(cfg)
    if not os.environ.get("KRAKEN_API_KEY"):
        raise SystemExit("Live tick needs KRAKEN_API_KEY/SECRET (demo) for account state and orders.")
    try:
        from .live import run_live_tick
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    return asyncio.run(run_live_tick(cfg))


def cmd_backtest(cfg: Config, args) -> int:
    import json

    from .backtest import Backtester, load_klines_csv

    if not args.data:
        print("Provide historical 1h klines CSV via --data path.csv")
        print("Format: time,open,high,low,close,volume[,...] (OHLCV order)")
        return 2
    klines = load_klines_csv(args.data)
    bt = Backtester(cfg, initial_equity=args.equity)
    result = bt.run(klines)
    print(json.dumps(result.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradingai", description="Claude-driven Kraken Futures trading bot (demo-first)")
    parser.add_argument("command",
                        choices=["check", "status", "snapshot", "tick", "run", "backtest", "report"],
                        help="action to run")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--data", default=None, help="klines CSV for backtest")
    parser.add_argument("--equity", type=float, default=1000.0, help="starting equity for backtest")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.command == "backtest":
        return cmd_backtest(cfg, args)
    return {
        "check": cmd_check,
        "status": cmd_status,
        "snapshot": cmd_snapshot,
        "tick": cmd_tick,
        "run": cmd_run,
        "report": cmd_report,
    }[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
