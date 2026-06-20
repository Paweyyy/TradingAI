"""Order planning: turn a valid TradeSetup into a fully-sized, concrete order.

Sizing is done deterministically by the Risk Layer here, so Claude is handed an
exact order to confirm — it does not choose the quantity. The permission hook
then enforces that any submitted order matches this plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .risk import RiskManager
from .strategy import Direction, TradeSetup


@dataclass
class OrderPlan:
    symbol: str
    side: str            # "Buy" | "Sell"
    qty: float
    entry_price: float
    stop_price: float
    take_profit_price: float
    leverage: int
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entry_price": round(self.entry_price, 4),
            "stop_price": round(self.stop_price, 4),
            "take_profit_price": round(self.take_profit_price, 4),
            "leverage": self.leverage,
            "reasons": self.reasons,
        }


def build_order_plan(cfg: Config, risk: RiskManager, setup: TradeSetup,
                     equity: float, last_price: float) -> OrderPlan | None:
    """Compute the exact order for a valid setup, or None if not tradable."""
    if not setup.valid or not setup.stop_distance or last_price <= 0 or equity <= 0:
        return None
    sizing = risk.size_position(equity, last_price, setup.stop_distance)
    qty = round(sizing.qty, cfg.market.qty_decimals)
    if qty <= 0:
        return None

    long = setup.direction == Direction.LONG
    side = "Buy" if long else "Sell"
    sd = setup.stop_distance
    stop = last_price - sd if long else last_price + sd
    tp_dist = cfg.execution.tp1_r_multiple * sd
    tp = last_price + tp_dist if long else last_price - tp_dist
    return OrderPlan(
        symbol=setup.symbol, side=side, qty=qty,
        entry_price=last_price, stop_price=stop, take_profit_price=tp,
        leverage=cfg.risk.leverage_cap, reasons=sizing.reasons,
    )
