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


def cmd_tick(cfg: Config) -> int:
    _assert_testnet(cfg)
    print("Live tick requires the Agent SDK, Bybit testnet keys, and network access.")
    print("Wire-up is in src/tradingai/agent.py (run_tick). Phase 3 enables order execution.")
    return 0


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
    parser.add_argument("command", choices=["check", "status", "tick", "backtest"], help="action to run")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--data", default=None, help="klines CSV for backtest")
    parser.add_argument("--equity", type=float, default=1000.0, help="starting equity for backtest")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.command == "backtest":
        return cmd_backtest(cfg, args)
    return {"check": cmd_check, "status": cmd_status, "tick": cmd_tick}[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
