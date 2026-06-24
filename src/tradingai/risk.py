"""Risk / Guard layer — the deterministic authority over every order.

No LLM here. Claude proposes; this validates and sizes. Every order intent must
pass :meth:`RiskManager.validate_order` before it can reach the exchange. The
kill switch and daily-loss / drawdown breakers also live here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass
class OrderIntent:
    symbol: str
    side: str          # "Buy" | "Sell"
    qty: float         # contracts / base units
    price: float       # intended entry (limit) or reference price
    leverage: float
    reduce_only: bool = False


@dataclass
class AccountState:
    equity: float
    peak_equity: float
    day_start_equity: float
    open_positions: int
    orders_this_tick: int = 0
    last_price: float | None = None


@dataclass
class GuardResult:
    approved: bool
    reasons: list[str]


@dataclass
class SizingResult:
    qty: float
    notional: float
    reasons: list[str]


class RiskManager:
    """Enforces hard limits independent of anything Claude says."""

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self._kill_switch = False

    # --- circuit breakers -------------------------------------------------
    def trip_kill_switch(self, reason: str = "manual") -> None:
        self._kill_switch = True
        self._kill_reason = reason

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def check_breakers(self, acct: AccountState) -> GuardResult:
        """Daily-loss and max-drawdown breakers. Trips the kill switch if hit."""
        reasons: list[str] = []
        r = self.cfg.risk
        if acct.day_start_equity > 0:
            day_pl_pct = (acct.equity - acct.day_start_equity) / acct.day_start_equity * 100
            if day_pl_pct <= -r.daily_loss_limit_pct:
                self.trip_kill_switch("daily_loss_limit")
                reasons.append(f"daily loss {day_pl_pct:.2f}% <= -{r.daily_loss_limit_pct}%")
        if acct.peak_equity > 0:
            dd_pct = (acct.equity - acct.peak_equity) / acct.peak_equity * 100
            if dd_pct <= -r.max_drawdown_pause_pct:
                self.trip_kill_switch("max_drawdown")
                reasons.append(f"drawdown {dd_pct:.2f}% <= -{r.max_drawdown_pause_pct}%")
        return GuardResult(not self._kill_switch, reasons)

    # --- position sizing --------------------------------------------------
    def size_position(self, equity: float, entry: float, stop_distance: float) -> SizingResult:
        """Fixed-fractional sizing from the stop, clamped by the leverage cap."""
        reasons: list[str] = []
        r = self.cfg.risk
        if stop_distance <= 0 or entry <= 0 or equity <= 0:
            return SizingResult(0.0, 0.0, ["invalid sizing inputs"])
        risk_amount = equity * (r.risk_per_trade_pct / 100)
        qty = risk_amount / stop_distance
        notional = qty * entry
        max_notional = r.leverage_cap * equity
        if notional > max_notional:
            qty = max_notional / entry
            notional = qty * entry
            reasons.append(f"clamped to leverage cap {r.leverage_cap}x")
        return SizingResult(qty, notional, reasons)

    # --- pre-trade validation --------------------------------------------
    def validate_order(self, intent: OrderIntent, acct: AccountState) -> GuardResult:
        """The gate every order passes through. Returns approval + reasons."""
        reasons: list[str] = []
        r = self.cfg.risk

        # Hard network guard: v1 must use the demo environment.
        if not self.cfg.mode.demo:
            return GuardResult(False, ["BLOCKED: not demo (v1 forbids live trading)"])

        if self._kill_switch:
            return GuardResult(False, ["BLOCKED: kill switch active"])

        if intent.leverage > r.leverage_cap:
            reasons.append(f"leverage {intent.leverage} > cap {r.leverage_cap}")

        if intent.qty <= 0:
            reasons.append("qty must be positive")

        if not intent.reduce_only and acct.open_positions >= r.max_positions:
            reasons.append(f"max positions {r.max_positions} reached")

        if acct.orders_this_tick >= r.max_orders_per_tick:
            reasons.append(f"order-rate limit {r.max_orders_per_tick}/tick reached")

        notional = intent.qty * intent.price
        if not intent.reduce_only and notional > r.leverage_cap * acct.equity:
            reasons.append(f"notional {notional:.2f} exceeds {r.leverage_cap}x equity")

        if acct.last_price:
            deviation = abs(intent.price - acct.last_price) / acct.last_price * 100
            if deviation > r.price_sanity_pct:
                reasons.append(f"price {deviation:.2f}% off last (>{r.price_sanity_pct}% fat-finger guard)")

        return GuardResult(len(reasons) == 0, reasons or ["ok"])
