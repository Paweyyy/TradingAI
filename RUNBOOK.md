# RUNBOOK — Running TradingAI on Bybit Testnet

Step-by-step to take the bot from zero to an autonomous testnet loop. Do these
in order; each step builds confidence before the next. **v1 is testnet-only** —
the bot refuses to run unless `BYBIT_TESTNET=true`.

> Companion docs: [README](./README.md) · [PLAN](./PLAN.md) · [STRATEGY](./STRATEGY.md) · [SIGNALS](./SIGNALS.md)

---

## Prerequisites (one-time)

1. **Python 3.11+** and **Node.js** — Node is required: the Bybit MCP server runs via `npx`.
2. **Bybit testnet account** — sign up at <https://testnet.bybit.com> (separate from any real account).
3. **Testnet API keys** — on testnet.bybit.com → **API Management** → create a key with
   **Read + Trade** for **Unified Trading / Derivatives**. **Do not** enable withdrawals.
4. **Anthropic API key** — from <https://console.anthropic.com> (for Claude's decisions).
5. **Fund the testnet account** — use the testnet **faucet / "request demo funds"** to get play USDT.

---

## Step 1 — Install

```bash
git clone -b claude/trading-bot-bybit-plan-u8mnlp https://github.com/Paweyyy/TradingAI.git
cd TradingAI
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[agent,dev]'      # 'agent' installs the Claude Agent SDK
pytest -q                           # sanity check: all tests should pass
```

## Step 2 — Validate the data path (no keys, zero risk)

Confirms market data + strategy rules work against live testnet data using only
keyless public endpoints:

```bash
BYBIT_TESTNET=true tradingai snapshot
```
Expect a JSON snapshot for BTCUSDT (trend, RSI, ATR, funding, Fear & Greed) plus
the rule evaluation. If this prints, your network + data pipeline is good.

## Step 3 — Add your keys

```bash
cp .env.example .env
# edit .env: set BYBIT_API_KEY, BYBIT_API_SECRET, ANTHROPIC_API_KEY; keep BYBIT_TESTNET=true
set -a; source .env; set +a        # load into the shell
tradingai check                    # should show testnet=True and API key set=True
```

## Step 4 — Dry run: watch it think *without trading* (recommended first)

In `config/config.yaml` set:
```yaml
mode:
  testnet: true
  dry_run: true        # evaluates + logs the sized order plan, places NO orders
```
Then:
```bash
tradingai run          # loops on the cadence; Ctrl-C stops gracefully
tradingai status       # review the logged decisions / planned orders
```
Let it run and confirm the decisions and planned sizes look sane.

## Step 5 — Live on testnet (real testnet orders)

Set `dry_run: false` in `config/config.yaml`, then:
```bash
tradingai run
```
Each tick: snapshot → circuit breakers → strategy rules → **pre-sized order plan**
→ Claude confirms/vetoes → orders placed via the Bybit MCP, every one clamped by
the Risk Layer (Claude cannot change the size or trade off-plan).

## Step 6 — Evaluate

```bash
tradingai report       # win rate, PnL, drawdown + the go-live gate verdict
```

---

## Tuning knobs (`config/config.yaml`)

| Knob | Default | Effect |
|---|---|---|
| `market.symbols` | `[BTCUSDT]` | Which pairs to trade |
| `runtime.cadence_minutes` | `60` | How often it evaluates. Lower (e.g. `5`) to gather data faster while testing — note it changes the strategy's character |
| `risk.risk_per_trade_pct` | `1.0` | % of equity risked per trade |
| `risk.leverage_cap` | `3` | Hard leverage ceiling (1–5) |
| `risk.daily_loss_limit_pct` | `3.0` | Halts new entries for the day past this |
| `risk.max_drawdown_pause_pct` | `15.0` | Pauses the bot past this peak-to-trough drop |
| `runtime.model` | `claude-opus-4-8` | Decision model |

---

## Safety reminders

- Keep `BYBIT_TESTNET=true`. The runner refuses to run live trading otherwise.
- Use an API key **without withdrawal rights** and, ideally, an **IP allowlist**.
- `.env` is gitignored — never commit keys.
- This is **not financial advice**. Validate on testnet (the go-live gate wants
  ≥30–50 trades with positive expectancy and drawdown < 15%) before discussing
  any real capital — and that is a separate, deliberate decision.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `REFUSING TO RUN: v1 is testnet-only` | Set `BYBIT_TESTNET=true` **and** `mode.testnet: true` |
| `Could not reach Bybit ... 403` | Your network blocks Bybit egress; run from a machine with outbound access |
| `claude-agent-sdk not installed` | `pip install -e '.[agent]'` |
| `Scheduler needs BYBIT_API_KEY/SECRET` | Export your testnet keys (Step 3) |
| `RISK BLOCK` / `PLAN MISMATCH` / `NO PLAN` in logs | The guard working as intended — a limit was breached, the direction was wrong, or there was no valid setup. Note: a wrongly-*sized* opening order is silently corrected to the planned size, not rejected |
| `npx` errors launching the MCP server | Install Node.js; ensure `npx` is on PATH |
