# RUNBOOK — Running TradingAI on the Kraken Futures Demo

Step-by-step to take the bot from zero to an autonomous demo loop. Do these in
order; each step builds confidence before the next. **v1 is demo-only** — the
bot refuses to run unless `KRAKEN_DEMO=true`.

> Companion docs: [README](./README.md) · [PLAN](./PLAN.md) · [STRATEGY](./STRATEGY.md) · [SIGNALS](./SIGNALS.md)

---

## Prerequisites (one-time)

1. **Python 3.11+** (macOS ships 3.9 — install 3.11/3.12 via Homebrew or python.org).
2. **Kraken CLI** — the official `krakenfx/kraken-cli` binary provides the MCP server
   that places orders. Install it (Homebrew / cargo / GitHub release) so `kraken` is on your PATH.
3. **Kraken Futures demo account** — sign up at <https://demo-futures.kraken.com> (separate
   sandbox; it comes pre-funded with demo collateral).
4. **Demo API keys** — on demo-futures.kraken.com → **Settings → API Keys** → create a key
   with trading permission. **Do not** enable withdrawals.
5. **Anthropic API key** — from <https://console.anthropic.com> (for Claude's decisions).

---

## Step 1 — Install

```bash
git clone https://github.com/Paweyyy/TradingAI.git
cd TradingAI
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e '.[agent,dev]'      # 'agent' installs the Claude Agent SDK
pytest -q                           # sanity check: all tests should pass
```

## Step 2 — Validate the data path (no keys, zero risk)

Confirms market data + strategy rules work against live Kraken demo data using
only keyless public endpoints:

```bash
KRAKEN_DEMO=true tradingai snapshot
```
Expect a JSON snapshot for PF_XBTUSD (trend, RSI, ATR, funding, Fear & Greed)
plus the rule evaluation. If this prints, your network + data pipeline is good.

## Step 3 — Add your keys

```bash
cp .env.example .env
# edit .env: set KRAKEN_API_KEY, KRAKEN_API_SECRET, ANTHROPIC_API_KEY; keep KRAKEN_DEMO=true
# (optional) set KRAKEN_MCP_COMMAND / KRAKEN_MCP_ARGS if your Kraken CLI invocation differs
set -a; source .env; set +a        # load into the shell
tradingai check                    # should show demo=True and API key set=True
```

## Step 4 — Dry run: watch it think *without trading* (recommended first)

In `config/config.yaml` set:
```yaml
mode:
  demo: true
  dry_run: true        # evaluates + logs the sized order plan, places NO orders
```
Then:
```bash
tradingai run          # loops on the cadence; Ctrl-C stops gracefully
tradingai status       # review the logged decisions / planned orders
```
Let it run and confirm the decisions and planned sizes look sane.

## Step 5 — Live on the demo (real demo orders)

Set `dry_run: false` in `config/config.yaml`, then:
```bash
tradingai run
```
Each tick: snapshot → circuit breakers → strategy rules → **pre-sized order plan**
→ Claude confirms/vetoes → orders placed via the Kraken MCP, every one clamped by
the Risk Layer (Claude cannot change the size or trade off-plan).

## Step 6 — Evaluate

```bash
tradingai report       # win rate, PnL, drawdown + the go-live gate verdict
```

---

## Tuning knobs (`config/config.yaml`)

| Knob | Default | Effect |
|---|---|---|
| `market.symbols` | `[PF_XBTUSD]` | Which Kraken perpetuals to trade (BTC is `XBT`) |
| `runtime.cadence_minutes` | `60` | How often it evaluates. Lower (e.g. `5`) to gather data faster while testing — note it changes the strategy's character |
| `risk.risk_per_trade_pct` | `1.0` | % of equity risked per trade |
| `risk.leverage_cap` | `3` | Hard leverage ceiling (1–5) |
| `risk.daily_loss_limit_pct` | `3.0` | Halts new entries for the day past this |
| `risk.max_drawdown_pause_pct` | `15.0` | Pauses the bot past this peak-to-trough drop |
| `runtime.model` | `claude-opus-4-8` | Decision model |

---

## Safety reminders

- Keep `KRAKEN_DEMO=true`. The runner refuses to run live trading otherwise.
- Use an API key **without withdrawal rights** and, ideally, an **IP allowlist**.
- `.env` is gitignored — never commit keys.
- This is **not financial advice**. Validate on the demo (the go-live gate wants
  ≥30–50 trades with positive expectancy and drawdown < 15%) before discussing
  any real capital — and that is a separate, deliberate decision.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `REFUSING TO RUN: v1 is demo-only` | Set `KRAKEN_DEMO=true` **and** `mode.demo: true` |
| `Could not fetch Kraken market data ... 403` | Your network blocks Kraken egress; run from a machine with outbound access |
| `HTTP 503` from `demo-futures.kraken.com` for market data | Expected — the demo host doesn't serve the public charts API. The bot now reads market data from the production host (`futures.kraken.com`); pull the latest. Override with `KRAKEN_MARKET_BASE` if needed |
| `claude-agent-sdk not installed` | `pip install -e '.[agent]'` |
| `Scheduler needs KRAKEN_API_KEY/SECRET` | Export your demo keys (Step 3) |
| Orders rejected with `RISK BLOCK` / `PLAN MISMATCH` / `NO PLAN` in logs | The guard working as intended — limit breached, wrong direction, or no valid setup. A wrongly-*sized* opening order is corrected to the planned size, not rejected |
| Kraken CLI MCP server fails to launch | Ensure the `kraken` binary is installed and on PATH; adjust `KRAKEN_MCP_COMMAND`/`KRAKEN_MCP_ARGS` |
