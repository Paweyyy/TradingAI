"""CLI entrypoint: validate config, print a status report, or run a tick.

    tradingai check    # validate config + environment (no network)
    tradingai status   # print state report
    tradingai tick     # run one live decision tick (needs SDK + keys + network)

v1 refuses to run live unless BYBIT_TESTNET=true.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import Config, load_config
from .logging_setup import log_event, setup_logging
from .reporting import format_status
from .state import StateStore


def _assert_testnet(cfg: Config) -> None:
    env_testnet = os.environ.get("BYBIT_TESTNET", "").lower() == "true"
    if not (cfg.mode.testnet and env_testnet):
        raise SystemExit(
            "REFUSING TO RUN: v1 is testnet-only. Set BYBIT_TESTNET=true and mode.testnet: true."
        )


def cmd_check(cfg: Config) -> int:
    logger = setup_logging(cfg.runtime.log_level)
    log_event(logger, "INFO", "config loaded",
              symbols=cfg.market.symbols, testnet=cfg.mode.testnet,
              risk_pct=cfg.risk.risk_per_trade_pct, leverage_cap=cfg.risk.leverage_cap)
    env_testnet = os.environ.get("BYBIT_TESTNET", "").lower() == "true"
    has_keys = bool(os.environ.get("BYBIT_API_KEY"))
    print("Config valid.")
    print(f"  testnet (config): {cfg.mode.testnet}")
    print(f"  BYBIT_TESTNET env: {env_testnet}")
    print(f"  Bybit API key set: {has_keys} (not needed for market-data-only)")
    print(f"  symbols: {cfg.market.symbols}  cadence: {cfg.runtime.cadence_minutes}m")
    if not (cfg.mode.testnet and env_testnet):
        print("  WARNING: not in testnet mode; live tick will be refused.")
    return 0


def cmd_status(cfg: Config) -> int:
    state = StateStore(cfg.runtime.state_dir)
    print(format_status(state))
    return 0


def cmd_snapshot(cfg: Config) -> int:
    """Fetch live testnet market data and print snapshot + rule evaluation.

    Keyless (market data only) and SDK-free — for validating the data path.
    """
    import json

    from .market_data import BybitClient
    from .snapshot import build_snapshot
    from .strategy import evaluate

    import urllib.error

    testnet = cfg.mode.testnet and os.environ.get("BYBIT_TESTNET", "").lower() == "true"
    client = BybitClient(testnet=testnet,
                         api_key=os.environ.get("BYBIT_API_KEY", ""),
                         api_secret=os.environ.get("BYBIT_API_SECRET", ""))
    try:
        for symbol in cfg.market.symbols:
            snap = build_snapshot(cfg, client, symbol)
            setup = evaluate(snap, cfg.strategy)
            print(json.dumps({"snapshot": snap.as_dict(), "setup": setup.as_dict()}, indent=2))
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Could not reach Bybit ({base_url_hint(testnet)}): {exc}")
        print("Run this from an environment with outbound access to Bybit.")
        return 1
    return 0


def base_url_hint(testnet: bool) -> str:
    from .market_data import base_url

    return base_url(testnet)


def cmd_report(cfg: Config) -> int:
    """Evaluate realized testnet performance + bot activity."""
    import urllib.error

    from .evaluation import evaluate, format_report
    from .market_data import BybitClient
    from .state import StateStore

    state = StateStore(cfg.runtime.state_dir)
    decisions = state._data.get("decisions", [])  # noqa: SLF001
    initial_equity = state.day_start_equity or state.peak_equity or 1000.0

    closed: list[dict] = []
    if os.environ.get("BYBIT_API_KEY"):
        testnet = cfg.mode.testnet and os.environ.get("BYBIT_TESTNET", "").lower() == "true"
        client = BybitClient(testnet=testnet,
                             api_key=os.environ["BYBIT_API_KEY"],
                             api_secret=os.environ.get("BYBIT_API_SECRET", ""))
        try:
            for symbol in cfg.market.symbols:
                closed.extend(client.closed_pnl(cfg.market.category, symbol))
        except (urllib.error.URLError, RuntimeError) as exc:
            print(f"(could not fetch realized trades: {exc}; reporting from decision log only)")
    else:
        print("(no BYBIT_API_KEY; reporting activity from decision log only)")

    print(format_report(evaluate(closed, decisions, initial_equity)))
    return 0


def cmd_run(cfg: Config) -> int:
    """Run the autonomous scheduler loop (testnet-only)."""
    _assert_testnet(cfg)
    if not os.environ.get("BYBIT_API_KEY"):
        raise SystemExit("Scheduler needs BYBIT_API_KEY/SECRET (testnet) for account state and orders.")
    from .scheduler import run_forever

    return run_forever(cfg)


def cmd_tick(cfg: Config) -> int:
    import asyncio

    _assert_testnet(cfg)
    if not os.environ.get("BYBIT_API_KEY"):
        raise SystemExit("Live tick needs BYBIT_API_KEY/SECRET (testnet) for account state and orders.")
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
        print("Format: start,open,high,low,close,volume[,turnover] (Bybit V5 kline order)")
        return 2
    klines = load_klines_csv(args.data)
    bt = Backtester(cfg, initial_equity=args.equity)
    result = bt.run(klines)
    print(json.dumps(result.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradingai", description="Claude-driven Bybit trading bot (testnet-first)")
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
