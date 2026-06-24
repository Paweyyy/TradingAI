# TradingAI — Trading Strategy v1: Higher-Timeframe Trend-Following

> **Companion to [`PLAN.md`](./PLAN.md) and [`SIGNALS.md`](./SIGNALS.md).** This is the concrete, rule-based strategy the bot executes first.
> **Profile:** Perpetuals (USDT-margined), **low leverage 2–5x**, **higher-timeframe trend-following**, majors only.
> **Capital:** Validate on **demo** first, sized to a **~€1000 account** so risk math is realistic. Live only after go-live criteria are met.
> **Last updated:** 2026-06-20
>
> ⚠️ **Not financial advice.** Trading leveraged crypto can lose money fast. This documents a *risk-managed process*, not a promise of profit. Expect drawdowns and losing streaks.

---

## 0. Reality check on capital (read this first)

- **€10 is too small to trade by the book.** Risking 1% = €0.10/trade, which is smaller than the round-trip fee + minimum order size. You can't place a sane stop. A €10 live account is a *symbolic learning stake*, not a growth vehicle.
- **€1000 is where the rules below actually work.** 1% risk = €10/trade — enough room for a real ATR stop after fees. We use this size for demo validation.
- **The strategy is identical at any size.** What changes with more capital is only that position sizing and stops become *feasible*, and fees become a smaller % drag. So: prove it on the demo at €1000-equivalent → then decide real capital deliberately.
- **"Trade my way up" honestly:** trend-following compounds slowly and unevenly. A *good* year might be tens of percent, with double-digit drawdowns along the way. There is no reliable fast path from tiny capital to wealth that doesn't rely on leverage gambling (which usually ends in liquidation). We optimize for **survival + positive expectancy**, and let compounding do its slow work.

---

## 1. Strategy in one paragraph

Trade **with the dominant higher-timeframe trend** on major perpetuals. Use the **4h chart for trend bias** and the **1h chart to time entries on pullbacks**. Risk a **fixed 1% of equity per trade** with an **ATR-based stop**, size the position from that stop (never from max leverage), take **partial profit at +1R and trail the rest**, and **stop trading for the day after a defined loss**. Few trades, low fees, defined risk.

---

## 2. Universe & timeframes

| Setting | v1 default | Notes |
|---|---|---|
| Instruments | **PF_XBTUSD** (perp) first; add **PF_ETHUSD** once stable | Majors = deepest liquidity, lowest spread, cleanest trends |
| Margin | USDT-margined perpetuals, **Isolated margin** | Isolated caps loss to the position's margin |
| Leverage cap | **3x** (range 2–5x allowed) | A hard ceiling, *not* a target; real exposure comes from risk sizing |
| Trend timeframe | **4h** (optional Daily confluence) | Defines long-only vs short-only bias |
| Entry timeframe | **1h** | Times pullback entries |
| Evaluation cadence | On each **1h close** (~24/day) | Re-checks 4h bias too; few actual trades result |
| Max concurrent positions | **1** (later 2 across BTC+ETH) | Keep it simple; avoid correlated double-risk |

---

## 3. The rules (deterministic — computed in code, see SIGNALS.md)

### 3.1 Trend filter (4h) → sets allowed direction
- **Uptrend (longs only):** `EMA50 > EMA200` **and** price > EMA50.
- **Downtrend (shorts only):** `EMA50 < EMA200` **and** price < EMA50.
- **No-trade regime:** EMAs entangled / price chopping around EMA50 → stand aside.

### 3.2 Entry trigger (1h, in the direction the 4h allows)
Enter on a **pullback that resumes**, not a chase:
- Price pulls back toward **EMA20 (1h)** (or mid-Bollinger), then
- **Momentum resumes:** RSI(14) crosses back **above 50** (long) / below 50 (short), **or** MACD histogram turns up (long) / down (short), and
- **Volume confirm:** entry candle volume ≥ its 20-period average.

### 3.3 Filters (avoid bad entries) — uses derivatives + regime signals
- **Funding guard:** skip **longs** when funding is **extremely positive** (crowded longs → squeeze risk); skip **shorts** when funding is **extremely negative**. (Threshold configurable.)
- **OI sanity:** prefer entries where open interest is *rising with* price in trend direction (real participation).
- **Sentiment guard (optional):** skip new **longs** when Fear & Greed is in **extreme greed (>85)**; skip new **shorts** in **extreme fear (<15)** — fade-the-crowd at extremes.

### 3.4 Exit & trade management
- **Initial stop:** `entry − 1.5×ATR(14, 1h)` for longs (mirror for shorts). This defines **R** (risk per unit).
- **Take-profit:** scale out **50% at +1R**, then **move stop to breakeven**.
- **Trail the rest:** trailing stop at **EMA20 (4h)** or a **2×ATR chandelier**; exit the remainder when it trails out or the **4h trend flips** (EMA50/200 cross back).
- **Hard time/invalidate exit:** if 4h bias flips against the position, exit regardless.

---

## 4. Position sizing & risk (the part that keeps you alive)

```
risk_per_trade   = 1% of current equity        # €10 on a €1000 account
stop_distance    = entry_price − stop_price     # from 1.5×ATR
position_size    = risk_per_trade / stop_distance
# then clamp:
#   notional = position_size × entry_price  ≤  leverage_cap × equity
#   notional ≥ exchange minimum, else SKIP the trade (too small to size properly)
```

- **Fixed-fractional 1% risk.** Account grows → position grows; account shrinks → position shrinks. Built-in compounding + capital protection.
- **Leverage is a clamp, not a dial.** Sizing comes from the stop; the 3x cap only prevents an oversized notional.
- **Daily loss limit (kill switch):** stop opening new trades for the day after **−3% equity** (≈ 3 losing trades). Enforced by the Risk Layer in PLAN.md, not by the prompt.
- **Max drawdown circuit breaker:** pause the bot entirely if equity draws down **−15% from peak**; require manual review/re-enable.
- **One open risk at a time** in v1 (no pyramiding, no averaging down — ever).

---

## 5. Costs you must respect (small edges die here)

- **Fees:** prefer **maker (limit) entries** (~0.02%) over taker (~0.055%). Round-trip taker ≈ 0.11% — at this is meaningful versus a 1–2R move, so **don't overtrade**.
- **Funding:** perps pay/receive funding every 8h. HTF holds cross funding windows — the funding guard (§3.3) also keeps us from holding the wrong side of expensive funding.
- **Slippage:** majors only + limit orders keeps this small; never market into thin books.
- **Implication:** the 1h/4h cadence (few trades) is itself a cost-control decision.

---

## 6. Default parameters (all config-driven — tune, don't hardcode)

| Param | Default | Param | Default |
|---|---|---|---|
| `trend_tf` | 4h | `risk_per_trade` | 1.0% |
| `entry_tf` | 1h | `atr_period` | 14 |
| `ema_fast / slow` | 50 / 200 | `atr_stop_mult` | 1.5 |
| `ema_entry` | 20 | `tp1_R` | 1.0 (50% out) |
| `rsi_period` | 14 | `trail` | EMA20(4h) / 2×ATR |
| `leverage_cap` | 3x | `daily_loss_limit` | 3% |
| `max_positions` | 1 | `max_drawdown_pause` | 15% |
| `funding_extreme` | configurable | `sentiment_guard` | on (extremes only) |

---

## 7. How Claude fits in

The rules above are **deterministic and code-computed** — Claude does **not** re-derive indicators. Per tick, Claude receives the structured snapshot (trend state, entry trigger status, filters, funding/OI, regime) and:
1. **Confirms or vetoes** a setup the rules flagged, with a written rationale (e.g., "4h uptrend intact, but OI falling and funding spiking — pass").
2. **Never overrides risk limits** — the Risk Layer has final authority on size, leverage, and the kill switch.
3. Its rationale is **logged for evaluation**, so we can see *why* each trade was taken and improve the strategy prompt over time.

This keeps arithmetic deterministic and uses Claude for judgment on conflicting/ambiguous signals — its actual strength.

---

## 8. Validation before any real money (go-live gate)

1. **Backtest** the rules on historical 1h/4h klines → check expectancy, win rate, avg R, max drawdown.
2. **Forward-test on the demo** (€1000-equivalent) for **≥ 30–50 trades** or a fixed time window.
3. **Go-live criteria (all must hold):** positive expectancy over the sample, max drawdown within tolerance (e.g. < 15%), no risk-limit breaches, behavior matches the logged rationale.
4. Only then consider real capital — and **start at the size you validated**, not €10. If you insist on €10 live, treat it explicitly as paying tuition to learn execution & psychology, knowing the sizing math is degraded.

---

## 9. Expectancy & expectations (be honest with yourself)

- Trend-following typically wins **~35–45%** of trades but with **avg win > avg loss** (the 1R scale-out + trailing aims for >1R average). Edge comes from **cutting losers fast and letting winners run** — emotionally hard, which is exactly why we automate it.
- **Expect losing streaks** of 5–8 trades. The daily/drawdown limits exist to survive them.
- **No leverage hero runs.** The 3x cap and 1% risk are deliberate. The goal is to still be trading next year.

---

## 10. Open questions to finalize

1. **Confluence:** require Daily-trend agreement with 4h, or 4h alone?
2. **Entry style:** pullback-to-EMA (above) vs breakout-of-range — start with pullback?
3. **Exact funding/sentiment thresholds** for the guards.
4. **Scale-out vs single TP:** 50%@1R + trail (above) vs fixed 2R exit — which to test first?
5. **Add ETH from day one** on the demo, or BTC-only until stable?

---

### References
- Strategy uses the signal stack defined in [`SIGNALS.md`](./SIGNALS.md) and the safety model in [`PLAN.md`](./PLAN.md).
- Kraken Futures perpetual contract specs (min order size, funding, leverage) — exposed via the Kraken Futures `instruments` endpoint and the [Kraken CLI](https://github.com/krakenfx/kraken-cli) MCP tools.
