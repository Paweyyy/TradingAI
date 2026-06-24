# TradingAI — Signals & Data Sources Plan

> **Companion to [`PLAN.md`](./PLAN.md).** This doc answers: *what signals do we trade on, where do they come from, and how do they reach Claude* — optimized for **reduced complexity + high value**, using **MCP and free/public/keyless APIs only**.
> **Last updated:** 2026-06-20

---

## 1. The short answer

**Yes to chart analysis. Yes to *light* sentiment. No to heavy/expensive inputs in v1.**

Most of the high-value signal is **already inside the Kraken MCP we're using** — price (OHLCV), order book, funding rate, open interest, and long/short ratio. We add **two free, keyless market-sentiment feeds** (Fear & Greed Index, BTC dominance) for cheap context. Everything else (news NLP, on-chain, social) is deferred to later phases and only added if it earns its complexity.

**Division of labor:**
- **Code computes deterministic features** (EMA cross, RSI, ATR, volume z-score, funding/OI deltas). LLMs are bad calculators; don't make Claude eyeball candles.
- **Claude synthesizes** those structured features + market context into a decision and rationale. Claude's edge is weighing many weak/conflicting signals and explaining itself — not arithmetic.
- **The Risk Layer (see PLAN.md) still has final authority** over any resulting order.

---

## 2. Signal taxonomy

Each category rated for **Value** (edge potential) and **Complexity** (effort + moving parts). We front-load high-value / low-complexity.

### Tier A — Core (v1). Free, mostly already in Kraken MCP.

| Signal group | Concrete signals | Source | Cost / Key | Value | Complexity |
|---|---|---|---|---|---|
| **Trend** | EMA/SMA cross (e.g. 20/50/200), price vs MA, higher-highs/lows | Kraken MCP klines → compute in code | Free, no key | High | Low |
| **Momentum** | RSI, MACD, rate-of-change | Kraken MCP klines → compute | Free, no key | High | Low |
| **Volatility** | ATR, Bollinger width, realized vol | Kraken MCP klines → compute | Free, no key | High | Low |
| **Volume / liquidity** | Volume z-score, volume trend, order-book imbalance/spread | Kraken MCP klines + orderbook | Free, no key | Med-High | Low |
| **Derivatives positioning** | **Funding rate**, **open interest** (Δ), **long/short ratio** | Kraken MCP (market tools) | Free | High | Low |
| **Multi-timeframe** | Align signals across e.g. 15m / 1h / 4h | Kraken MCP klines (per TF) | Free | High | Low-Med |

> Derivatives positioning (funding/OI/L-S ratio) is the cheapest *unique* edge here: it's not classic chart TA, it's already in the MCP, and it tells you about crowd leverage and squeeze risk.

### Tier B — Market context (v1, light). Free, keyless public APIs.

| Signal | What it adds | Source | Cost / Key | Value | Complexity |
|---|---|---|---|---|---|
| **Fear & Greed Index** | Aggregate market sentiment regime (risk-on/off) | Alternative.me F&G API | Free, **no key** | Med | Low |
| **BTC dominance + total mkt cap** | Regime / alt-vs-BTC rotation context | CoinGecko free/Demo | Free (keyless or Demo key) | Med | Low |

### Tier C — Deferred (Phase 2+). Add only if it earns its keep.

| Signal | Why deferred | Source (free options) |
|---|---|---|
| **News / narrative NLP** | Parsing + dedup + relevance is real work; risk of noise/hallucination. Phase 2 with Claude summarizing a curated feed. | CryptoCompare News, CoinGecko news endpoints |
| **Social / search trends** | Noisy, easy to overfit; many good sources are paid. | (often paid) CFGI components, Google Trends |
| **On-chain / DEX flow** | Mostly relevant for small-caps/DeFi, not BTC/ETH perps. | DexScreener (keyless), public RPCs |
| **Whale / liquidation feeds** | High value but data quality + cost vary; revisit after core works. | Coinglass-style (often rate-limited/paid) |

---

## 3. Recommended v1 signal set (the actual build)

Trade decisions for the configured symbol(s) on the demo are formed from a **structured feature snapshot** containing:

1. **Price action** — last price, % change (1h/24h), distance to recent high/low.
2. **Trend** — EMA(20/50/200) values + cross state + slope; multi-timeframe agreement.
3. **Momentum** — RSI(14), MACD histogram sign/slope.
4. **Volatility** — ATR(14), Bollinger band width percentile.
5. **Volume/liquidity** — volume z-score, order-book top-of-book spread + imbalance.
6. **Derivatives** — current funding rate (and trend), open-interest 24h Δ, long/short ratio.
7. **Market regime** — Fear & Greed value + label, BTC dominance.

All of (1)–(6) come from the **Kraken MCP** (klines / tickers / orderbook / funding / OI). Item (7) comes from **two free keyless calls**. That's the whole v1 data surface — deliberately small.

---

## 4. How signals reach Claude (feature engineering, not raw dumps)

```
Kraken MCP (klines/orderbook/funding/OI) ─┐
                                         ├─► feature builder (code) ─► compact JSON snapshot ─► Claude
Free APIs (F&G, BTC dominance) ──────────┘        (indicators)          (per symbol/TF)        (reasons + proposes)
```

Principles:
- **Pre-compute indicators in deterministic Python** (e.g. `pandas`/`pandas-ta` or hand-rolled). Feed Claude *numbers and states* ("RSI 1h = 62, rising; EMA20>EMA50>EMA200; funding +0.012%/8h rising; F&G = 72 Greed"), not 200 raw candles.
- **Compact, labeled snapshot** keeps token cost low and decisions reproducible/auditable.
- **Claude's job:** weigh the (often conflicting) signals into hold/open/close/adjust + size suggestion + a written rationale. The rationale is logged for evaluation.
- **Config-driven weighting/strategy:** which indicators, TFs, and thresholds matter is set in the strategy prompt + config — so we can A/B strategies without engine changes (matches the framework approach in PLAN.md).

---

## 5. Connector summary

| Connector | Type | Auth | Used for | Phase |
|---|---|---|---|---|
| **Kraken** (CLI MCP + REST) | MCP (stdio) + REST | Demo key (market data needs none) | OHLCV (charts), tickers, funding, OI, **order execution** | v1 |
| **Alternative.me Fear & Greed** | REST | **None** | Market sentiment regime | v1 |
| **CoinGecko** (keyless / free Demo) | REST | None or free Demo key | BTC dominance, total mkt cap, broad price sanity | v1 |
| CryptoCompare News | REST | Free key | News headlines for NLP | Phase 2 |
| DexScreener | REST | **None** | On-chain/DEX pairs (small-caps) | Phase 3 (if needed) |

> Free APIs are wrapped behind a small internal interface (cache + rate-limit + graceful-fail) so a flaky free endpoint never blocks a trading tick — if F&G is down, the tick proceeds without it and notes the gap.

---

## 6. Phased rollout (signals)

| Phase | Adds | Rationale |
|---|---|---|
| **S1 — Core TA** | Tier A price/trend/momentum/volatility/volume from Kraken MCP | Highest value, lowest complexity, no extra deps |
| **S2 — Derivatives** | Funding, OI, long/short ratio | Cheap unique edge, same MCP |
| **S3 — Regime context** | Fear & Greed + BTC dominance | Two free keyless calls, better risk-on/off framing |
| **S4 — News NLP (opt-in)** | Claude-summarized curated headlines | Only if S1–S3 show the bot needs catalyst awareness |
| **S5 — On-chain (opt-in)** | DexScreener for alt/DeFi names | Only if trading beyond major perps |

S1–S3 are all v1 and require **no paid services and (mostly) no API keys** beyond the Kraken demo credential.

---

## 7. Complexity guardrails (so this stays "high value, low complexity")

- **One source of truth per signal.** Don't pull price from three places; Kraken MCP is canonical for traded instruments.
- **No signal without a use.** Every feature in the snapshot must be referenced by the strategy prompt; unused features get cut.
- **Free-first.** Add a paid source only when a measured gap justifies it.
- **Fail open on context, fail closed on execution.** Missing sentiment → trade anyway with a note. Missing/contradictory risk data → block the order (Risk Layer).
- **Deterministic where possible.** Indicators in code, judgment in Claude — never the reverse.

---

## 8. Open questions

1. **Timeframes:** which set for v1 (e.g. 15m + 1h + 4h)? Affects feature builder + cadence.
2. **Indicator list/params:** lock the exact Tier-A indicators and lookbacks for the snapshot.
3. **Symbols:** majors-only (BTC/ETH perps) keeps Tier C unnecessary; broader alts would pull DexScreener forward.
4. **News in or out for v1?** Default recommendation: **out** until core is validated.
5. **CoinGecko keyless vs Demo key:** keyless is simplest; Demo key raises limits — decide based on call volume.

---

### References
- Kraken CLI (MCP server) — [github.com/krakenfx/kraken-cli](https://github.com/krakenfx/kraken-cli) · Kraken Futures REST — [docs.kraken.com/api](https://docs.kraken.com/api/docs/guides/futures-rest/)
- Fear & Greed Index API (free, keyless) — [alternative.me/crypto/fear-and-greed-index](https://alternative.me/crypto/fear-and-greed-index/)
- Best free crypto APIs (keyless / free tiers) — [CoinGecko: Best Free Crypto APIs 2026](https://www.coingecko.com/learn/best-free-crypto-api)
- DexScreener public API (keyless on-chain) — referenced in [CoinGecko: Best Cryptocurrency APIs 2026](https://www.coingecko.com/learn/best-cryptocurrency-apis)
- Crypto news APIs — [CoinGecko: Best Crypto News APIs 2026](https://www.coingecko.com/learn/best-crypto-news-api)
