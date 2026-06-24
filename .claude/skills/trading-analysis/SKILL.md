---
name: trading-analysis
description: Analyze the TradingAI bot on demand — current market setup/signals, backtests, performance reports, and recent decision history. Use when the user asks about the trading bot's view of the market ("what's the BTC setup", "should it be long?"), wants a backtest summarized, asks how the bot is doing / its PnL / win rate / go-live readiness, or wants to know why it made (or skipped) a trade. This is READ-ONLY analysis; it does not start the autonomous loop or place orders.
---

# TradingAI — Analysis Skill

This skill is the **interactive, read-only front door** to the TradingAI bot. It
shells into the existing, tested `tradingai` CLI so you can answer questions
about the strategy's current view, historical performance, and recent decisions.

It does **not** replace the autonomous engine (`tradingai run`) and must **never**
be used to place live orders. Order execution stays in the scheduled service with
its deterministic Risk Layer. See `STRATEGY.md`, `SIGNALS.md`, and `PLAN.md` in
the repo for the full design.

## How to run commands

Use the wrapper script (it locates the repo root, activates the venv if present,
sets `BYBIT_TESTNET=true`, and forwards to the CLI):

```bash
.claude/skills/trading-analysis/scripts/run.sh <command> [args]
```

If a command fails because dependencies aren't installed, run once:
`python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'`.

## What you can answer

| User asks | Command | Notes |
|---|---|---|
| "What's the current BTC setup / should it be long?" | `run.sh snapshot` | Keyless. Prints live testnet snapshot (trend, RSI, ATR, funding, F&G) + the deterministic rule evaluation. Summarize it; explain *why* valid/invalid from the `reasons`. |
| "Backtest the strategy on this data" | `run.sh backtest --data <path.csv> --equity 1000` | Needs a Bybit-format klines CSV. Report trades, return, win rate, avg R, max drawdown. |
| "How is the bot doing / is it ready for real money?" | `run.sh report` | Win rate, PnL, drawdown, and the go-live gate verdict. Needs keys for realized trades; otherwise summarizes the decision log. |
| "Show recent decisions / status" | `run.sh status` | Equity peaks, day counters, last decisions. |
| "Is my setup/config valid?" | `run.sh check` | Validates config + environment. |
| "Why did it hold / take that trade?" | `run.sh status` then read `state/state.json` | Decisions log each action + rationale. Quote and explain it. |

## Guardrails

- **Read-only.** Do not run `tradingai tick` or `tradingai run` from this skill —
  those drive the live agent and place orders. If the user wants to start the
  bot, point them to `RUNBOOK.md` instead.
- **Be honest about data availability.** `snapshot` needs network to Bybit;
  `report` needs API keys for realized PnL. If unavailable, say so and fall back
  to the decision log rather than inventing numbers.
- **Not financial advice.** When interpreting setups, describe what the rules say;
  don't make promises about outcomes.
