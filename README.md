# TradingAI

Claude-driven automated crypto trading bot on **Bybit**, via the official Bybit **MCP** server and the **Claude Agent SDK**. **Testnet-first** — v1 refuses to trade real funds.

> Design docs: **[PLAN.md](./PLAN.md)** (architecture & safety) · **[SIGNALS.md](./SIGNALS.md)** (data & signals) · **[STRATEGY.md](./STRATEGY.md)** (the trading strategy).

## What it does

Each tick, the bot builds a compact market snapshot for the configured symbol (price/trend/momentum/volatility/volume from Bybit, plus funding/OI and a free Fear & Greed regime read), evaluates a deterministic **higher-timeframe trend-following** strategy, and asks **Claude** to confirm or veto the setup with a written rationale. A deterministic **Risk Layer** has final authority over sizing, leverage, and a kill switch — Claude can never exceed the limits.

```
snapshot (code) -> strategy rules (code) -> Claude confirm/veto -> Risk Layer -> Bybit testnet
```

## Status

| Component | State |
|---|---|
| Project scaffold, config, logging, state | ✅ done |
| Indicators (EMA/RSI/ATR/MACD/vol-z) | ✅ done + tested |
| Strategy rules (HTF trend-following) | ✅ done + tested |
| Risk Layer (caps, sizing, kill switch) | ✅ done + tested |
| Bybit MCP wiring + permission hook | ✅ scaffolded |
| Live agent tick (Claude + orders) | 🚧 Phase 3 |
| Scheduler / autonomous loop | 🚧 Phase 4 |

See the roadmap in [PLAN.md](./PLAN.md#6-phased-roadmap). **32 tests pass** for the deterministic core (no network/keys needed).

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'         # add ',agent' to install the Claude Agent SDK too
pytest -q                        # run the test suite

cp .env.example .env             # then fill in TESTNET keys; keep BYBIT_TESTNET=true
BYBIT_TESTNET=true tradingai check     # validate config + environment
tradingai status                       # print state report
tradingai tick                         # (Phase 3) one live testnet decision tick
```

## Configuration

Everything strategy- and risk-related lives in **[config/config.yaml](./config/config.yaml)** (validated by `src/tradingai/config.py`); the strategy prompt is **[config/strategies/default.md](./config/strategies/default.md)**. Secrets come only from `.env` / environment — never YAML. v1 defaults: BTCUSDT perp, 1% risk/trade, 3x leverage cap, 4h trend / 1h entry.

## Safety

- **Testnet-only in v1:** the runner refuses to run live unless `BYBIT_TESTNET=true`.
- **Programmatic guards, not prompt trust:** size/leverage/allowlist/rate/loss limits are enforced in `risk.py`; withdrawal/transfer tools are denied in `permissions.py`.
- **Kill switch + circuit breakers:** daily-loss and max-drawdown breakers halt new entries automatically.
- Secrets are gitignored; use a Bybit API key with no withdrawal rights and an IP allowlist.

> ⚠️ Not financial advice. Leveraged crypto trading can lose money quickly. Validate on testnet before risking any real capital.
