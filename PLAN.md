# TradingAI — Claude-Driven Automated Trading Bot (Kraken MCP)

> **Status:** Planning doc (v1). No bot code yet.
> **Scope of v1:** Demo/paper only · Claude Agent SDK (Python) · configurable framework (no fixed strategy baked in).
> **Last updated:** 2026-06-20

---

## 1. Goal

Build an automated trading bot where **Claude makes the trading decisions** by reasoning over live market data and account state, and a **Kraken MCP server** gives Claude the tools to read markets and place/manage orders.

The first version is a **general, configurable framework** that runs entirely on **Kraken demo** (`KRAKEN_DEMO=true`, no real funds). Pairs, cadence, and risk limits are configuration — not hardcoded strategy. The same codebase can later be pointed at mainnet by flipping config, but only after the safety layer and evaluation are proven on the demo.

### Non-goals for v1
- Live mainnet trading with real funds.
- A specific "winning" strategy. We build the harness; strategies are pluggable prompts/configs.
- High-frequency / sub-second trading (the agent loop is minutes-scale, not microseconds).
- A custom UI. Observability is via structured logs + a simple status report.

---

## 2. High-Level Architecture

```
                         ┌─────────────────────────────────────────┐
                         │          Scheduler / Runner              │
                         │   (loop every N min, or one-shot tick)   │
                         └───────────────────┬─────────────────────┘
                                             │ tick
                                             ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │                        Trading Agent (Python)                          │
   │                       Claude Agent SDK loop                            │
   │                                                                        │
   │   1. Build context  ──► market snapshot + positions + risk budget      │
   │   2. Claude reasons ──► decides: hold / open / close / adjust          │
   │   3. Proposes orders (as MCP tool calls)                               │
   │                                                                        │
   └───────┬───────────────────────────────────┬───────────────────────────┘
           │ market/account reads               │ order intents
           │ (via MCP tools)                    │ (intercepted)
           ▼                                    ▼
   ┌──────────────────┐               ┌───────────────────────────┐
   │  Kraken MCP      │               │   Risk / Guard Layer       │
   │  Server (stdio)  │◄──────────────│  (pre-trade validation,    │
   │  demo            │  approved     │   hard caps, kill switch)  │
   │  (Kraken CLI)    │  orders only  │                            │
   └────────┬─────────┘               └───────────────────────────┘
            │ Kraken Futures REST                                   
            ▼
   ┌──────────────────┐
   │  Kraken demo     │
   └──────────────────┘

   Cross-cutting:  Config · Structured Logging · State Store · Reporting
```

**Key design principle: separation of *reasoning* from *authority*.** Claude proposes; the deterministic Risk/Guard Layer disposes. Claude never has unmediated authority to move size — every order intent passes through programmatic guards (caps, allowlists, kill switch) before it reaches the exchange. This is enforced via the Agent SDK **permission / tool-callback hooks**, not by trusting the prompt.

---

## 3. Building Blocks

### 3.1 Kraken MCP Server (the tools)
- **Server:** official Kraken CLI (`krakenfx/kraken-cli`) with its built-in **MCP server over stdio**, launched as a subprocess of our Python agent. Command/args configurable via `KRAKEN_MCP_COMMAND`/`KRAKEN_MCP_ARGS`.
- **Coverage:** ~134 CLI commands across spot, futures, staking, and WebSocket streaming, exposed as MCP tools.
- **Auth & env:**
  - `KRAKEN_API_KEY` + `KRAKEN_API_SECRET` — demo keys from demo-futures.kraken.com.
  - `KRAKEN_DEMO=true` — **hard requirement for v1**.
  - Read-only market data (charts/tickers) works with no key (useful for early dev).
- **Why the Kraken CLI:** official, AI-native (built for Claude Code/agents), built-in MCP server, ships a local paper-trading engine, and Kraken Futures has a full demo environment.
- **Note:** for deterministic indicators, our code also reads market data directly from the Kraken Futures REST API (`market_data.py`); order *execution* goes through the MCP under Claude, gated by the Risk Layer.

### 3.2 Claude Agent SDK (the brain)
- **Library:** `claude-agent-sdk` (Python). Drives the same agent loop as Claude Code — tool execution, context management, permission hooks — from our own process.
- **Model:** default to the latest capable Claude (e.g. an Opus-class model) for decision quality; configurable. A cheaper model can be used for routine "nothing to do" ticks to save cost.
- **MCP wiring:** register the Kraken CLI MCP server in `ClaudeAgentOptions.mcp_servers` as a `stdio` server with `env` injecting the demo keys + `KRAKEN_DEMO=true`.
- **Tool gating:** use `allowed_tools` + a **permission/pre-tool-use callback** so that any `Trade`/`Position` (order-mutating) tool call is routed through the Risk Layer for approval before execution. Market/account *read* tools pass through freely.

### 3.3 Risk / Guard Layer (the authority) — the most important component
Deterministic Python, no LLM. Validates every order intent before it can reach Kraken:
- **Network guard:** refuse to run if not demo (assert `KRAKEN_DEMO=true`) in v1.
- **Symbol allowlist:** only configured pairs may be traded.
- **Size caps:** max order qty, max notional per order, max total position per symbol, max gross exposure.
- **Leverage cap:** never exceed configured max leverage.
- **Order-rate limit:** max N orders per tick / per hour (anti-runaway).
- **Loss limits / kill switch:** if realized+unrealized drawdown for the day exceeds threshold → block all new opening orders, optionally flatten, halt the bot.
- **Sanity checks:** price within X% of last trade (no fat-finger), reduce-only flags honored, no duplicate intents.
- Every decision (approve/reject + reason) is logged.

### 3.4 Cross-cutting
- **Config:** single typed config (env + `config.yaml`/`.env`), validated on startup. Holds: mode (demo), symbols, cadence, risk limits, model, prompt/strategy selection.
- **State store:** lightweight (JSON/SQLite) for open intents, last decisions, daily PnL counters, idempotency keys.
- **Logging:** structured JSON logs — every tick, context sent, Claude's rationale, tool calls, guard decisions, fills.
- **Reporting:** a `status` command that prints positions, today's PnL, recent decisions, guard rejections.

---

## 4. The Agent Loop (one "tick")

1. **Trigger** — scheduler fires (every N minutes) or manual one-shot.
2. **Pre-flight** — assert demo; check kill switch / daily limits; load state.
3. **Build context** — gather via MCP read tools: tickers/klines/orderbook for allowed symbols, wallet balance, open positions, open orders, remaining risk budget. Summarize into a compact, structured prompt.
4. **Reason (Claude)** — Claude receives context + the strategy prompt and the risk constraints. It decides: hold / open / close / adjust, and proposes concrete orders as MCP tool calls with rationale.
5. **Guard** — each order intent is intercepted by the permission hook → Risk Layer validates → approve or reject (with reason fed back to Claude).
6. **Execute** — approved orders go to Kraken demo via the MCP Trade tools; idempotency keys prevent duplicates.
7. **Record** — persist decisions, intents, fills, PnL; emit structured logs.
8. **Sleep** — wait for next tick.

The strategy is expressed primarily as a **system/strategy prompt + config knobs**, so swapping strategies = swapping a prompt file and parameters, not rewriting the engine.

---

## 5. Proposed Project Structure

```
TradingAI/
├── PLAN.md                     # this document
├── README.md                   # quickstart (demo setup, run, status)
├── pyproject.toml              # deps: claude-agent-sdk, pydantic, etc.
├── .env.example                # KRAKEN_API_KEY/SECRET, KRAKEN_DEMO=true, ANTHROPIC_API_KEY
├── config/
│   ├── config.yaml             # symbols, cadence, risk limits, model
│   └── strategies/
│       └── default.md          # the strategy/system prompt
├── src/tradingai/
│   ├── runner.py               # scheduler / loop entrypoint
│   ├── agent.py                # Claude Agent SDK setup + tick logic
│   ├── mcp_kraken.py            # MCP server config (stdio, env, demo)
│   ├── context.py              # build market+account snapshot
│   ├── risk.py                 # Risk/Guard layer (caps, kill switch)
│   ├── permissions.py          # pre-tool-use hook → risk.validate()
│   ├── state.py                # state store (SQLite/JSON)
│   ├── config.py               # typed config loader + validation
│   ├── logging_setup.py        # structured logging
│   └── reporting.py            # status report
└── tests/
    ├── test_risk.py            # guard caps, kill switch (no network)
    ├── test_context.py         # snapshot shaping
    └── test_permissions.py     # order intents blocked/allowed correctly
```

---

## 6. Phased Roadmap

| Phase | Goal | Key deliverables | Exit criteria |
|------|------|------------------|---------------|
| **0. Scaffold** | Project skeleton | repo layout, config loader, `.env.example`, logging, CI lint/test | `pytest` runs green on empty suite; config validates |
| **1. Read-only MCP** | Prove Claude ↔ Kraken MCP | wire MCP server (no key), Claude fetches & summarizes market data | Claude returns a market snapshot for configured symbols on the demo |
| **2. Risk layer** | Build the authority | `risk.py` + `permissions.py` + tests; kill switch; caps | unit tests prove over-size/over-leverage/off-allowlist intents are rejected |
| **3. Demo trading** | Close the loop | demo keys, order-mutating tools gated by guards, one full tick opens/closes a tiny position | a guarded order fills on the demo; duplicates prevented |
| **4. Strategy & loop** | Make it autonomous | scheduler, strategy prompt(s), state/PnL tracking, daily limits | bot runs unattended on the demo for a session, respects all limits |
| **5. Eval & reporting** | Trust before scale | `status` report, decision logs, simple backtest/replay of decisions, paper-PnL summary | can review what it did and why; metrics on win/loss, guard rejections |
| **6. (Gated) Mainnet readiness** | Optional, explicit opt-in | mainnet config behind extra confirmation, tighter caps, dry-run mode | **separate sign-off required — not part of v1** |

---

## 7. Safety, Security & Risk Controls (must-haves)

- **Demo assertion in v1:** the runner refuses to start unless `KRAKEN_DEMO=true`. Mainnet is a deliberate, separate, gated step.
- **Programmatic guards, not prompt trust:** all size/leverage/allowlist/rate/loss limits are enforced in code via the permission hook. A jailbroken or confused prompt still cannot exceed caps.
- **Kill switch:** a file flag / env / config that halts new opening orders immediately; daily drawdown auto-trips it.
- **Secrets hygiene:** API keys only in env / `.env` (gitignored). `.env.example` ships placeholders. Recommend a Kraken API key with **minimal permissions + IP allowlist**, no withdrawal rights.
- **Least privilege tools:** `allowed_tools` restricts the agent to the tool set it needs; withdrawal/transfer/sub-account tools are **denied**.
- **Idempotency:** client order IDs prevent duplicate submission on retries.
- **Auditability:** every tick, rationale, tool call, and guard decision is logged in structured form.
- **Cost controls:** cap tokens/turns per tick; optionally a cheaper model for idle ticks.

---

## 8. Dependencies & Prerequisites

- Python 3.11+, `claude-agent-sdk`, `pydantic`, `pyyaml`, a scheduler (built-in loop or APScheduler), `pytest`.
- The **Kraken CLI** (`krakenfx/kraken-cli`) installed on PATH — provides the MCP server.
- `ANTHROPIC_API_KEY` (or subscription Agent SDK credits) for Claude.
- A **Kraken Futures demo account** + demo API key/secret (from demo-futures.kraken.com); the demo comes pre-funded with demo collateral.

---

## 9. Open Questions (to resolve before/while implementing)

1. **Cadence:** what tick interval (e.g. 5m / 15m / 1h)? Affects cost and responsiveness.
2. **Instruments:** perpetuals (USDT-margined) vs spot for v1? Perps add leverage/funding complexity.
3. **Default symbols & caps:** starting allowlist (e.g. PF_XBTUSD) and concrete size/leverage/loss numbers.
4. **Strategy prompt:** how prescriptive should the first strategy be (e.g. trend-following with explicit rules) vs open-ended ("trade profitably within these constraints")?
5. **Model choice & budget:** which Claude model per tick, and a monthly cost ceiling.
6. **Scheduling host:** where does the loop run (local, a small VM, a container, GitHub Actions cron)?

---

## 10. Immediate Next Steps

Once this plan is approved, the natural first implementation slice is **Phase 0 + Phase 1**:
1. Scaffold the repo (structure in §5), config loader, logging, `.env.example`, CI.
2. Wire the Kraken MCP server read-only and have Claude produce a market snapshot for a configured symbol on the demo.
3. Then build the Risk Layer (Phase 2) before any order-mutating tools are enabled.

---

### References
- Kraken CLI (built-in MCP server) — [github.com/krakenfx/kraken-cli](https://github.com/krakenfx/kraken-cli)
- Kraken Futures REST API (charts, tickers, accounts, sendOrder) — [docs.kraken.com/api](https://docs.kraken.com/api/docs/guides/futures-rest/)
- Kraken Futures demo environment — [demo-futures.kraken.com](https://demo-futures.kraken.com)
- Claude Agent SDK (Python) — [github.com/anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) · [MCP in the SDK docs](https://docs.claude.com/en/docs/agent-sdk/mcp)
