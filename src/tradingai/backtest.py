"""Backtester for the deterministic strategy.

Replays historical 1h klines, deriving the 4h trend by resampling, and simulates
the STRATEGY.md rules: fixed-fractional sizing, ATR stop, scale-out at +1R with
breakeven, and an ATR chandelier trail. Fees are modelled per fill.

Scope note: a backtest evaluates the **deterministic** strategy only. In live
trading Claude adds a *veto* on top of these rules (it can pass on a valid setup
but never invents one), so live activity is a subset of backtest entries. This
gives a conservative baseline for the go-live gate in STRATEGY.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import indicators as ind
from .config import Config
from .features import Kline, build_timeframe_features, MarketSnapshot
from .strategy import Direction, evaluate


@dataclass
class Trade:
    direction: str
    entry_price: float
    exit_price: float
    qty: float
    r_value: float          # price distance of initial stop (1R)
    pnl: float              # net of fees, in quote currency
    r_multiple: float       # pnl expressed in R
    bars_held: int
    exit_reason: str


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def total_return_pct(self) -> float:
        if self.initial_equity == 0:
            return 0.0
        return (self.final_equity - self.initial_equity) / self.initial_equity * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades) * 100

    @property
    def avg_r(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.r_multiple for t in self.trades) / len(self.trades)

    @property
    def expectancy_r(self) -> float:
        """Average R per trade — the headline edge metric."""
        return self.avg_r

    @property
    def max_drawdown_pct(self) -> float:
        peak = self.initial_equity
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = min(max_dd, (eq - peak) / peak * 100)
        return max_dd

    def summary(self) -> dict:
        return {
            "trades": self.n_trades,
            "total_return_pct": round(self.total_return_pct, 2),
            "win_rate_pct": round(self.win_rate, 1),
            "avg_r": round(self.avg_r, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "final_equity": round(self.final_equity, 2),
        }


def _resample(klines: list[Kline], factor: int) -> list[Kline]:
    """Aggregate `factor` consecutive candles into one (1h -> 4h with factor=4)."""
    out: list[Kline] = []
    for i in range(0, len(klines) - len(klines) % factor, factor):
        bucket = klines[i : i + factor]
        out.append(
            Kline(
                open=bucket[0].open,
                high=max(b.high for b in bucket),
                low=min(b.low for b in bucket),
                close=bucket[-1].close,
                volume=sum(b.volume for b in bucket),
            )
        )
    return out


@dataclass
class _Position:
    direction: Direction
    entry: float
    qty: float
    stop: float
    r_value: float
    scaled: bool = False
    bars: int = 0


class Backtester:
    def __init__(self, config: Config, initial_equity: float = 1000.0,
                 fee_rate: float = 0.00055, resample_factor: int = 4) -> None:
        self.cfg = config
        self.initial_equity = initial_equity
        self.fee_rate = fee_rate
        self.resample_factor = resample_factor

    def run(self, klines: list[Kline]) -> BacktestResult:
        s = self.cfg.strategy
        warmup = max(s.ema_slow + 5, s.atr_period + 5)
        equity = self.initial_equity
        result = BacktestResult(self.initial_equity, equity, equity_curve=[equity])
        pos: _Position | None = None

        for i in range(warmup, len(klines)):
            window = klines[: i + 1]
            bar = klines[i]

            # --- manage an open position on this bar ---
            if pos is not None:
                pos.bars += 1
                closed = self._manage(pos, bar, window, equity, result)
                if closed is not None:
                    equity += closed
                    pos = None
                result.equity_curve.append(equity)
                if pos is not None:
                    continue  # one action per bar while in a position

            # --- look for a new entry ---
            if pos is None:
                snap = self._snapshot(window)
                setup = evaluate(snap, s)
                if setup.valid and setup.stop_distance:
                    qty = self._size(equity, bar.close, setup.stop_distance)
                    if qty > 0:
                        equity -= qty * bar.close * self.fee_rate  # entry fee
                        stop = (bar.close - setup.stop_distance
                                if setup.direction == Direction.LONG
                                else bar.close + setup.stop_distance)
                        pos = _Position(setup.direction, bar.close, qty, stop, setup.stop_distance)
                result.equity_curve.append(equity)

        # close any residual position at the last close
        if pos is not None:
            equity += self._close(pos, klines[-1].close, pos.qty, result, "end_of_data")
        result.final_equity = equity
        return result

    # --- helpers ----------------------------------------------------------
    def _snapshot(self, window: list[Kline]) -> MarketSnapshot:
        s = self.cfg.strategy
        entry_feats = build_timeframe_features(window, s)
        trend_klines = _resample(window, self.resample_factor)
        trend_feats = build_timeframe_features(trend_klines, s) if len(trend_klines) > s.ema_slow else entry_feats
        # Funding/sentiment unavailable in backtest -> left None so guards are skipped.
        return MarketSnapshot(symbol="BACKTEST", trend_tf=trend_feats, entry_tf=entry_feats)

    def _size(self, equity: float, entry: float, stop_distance: float) -> float:
        r = self.cfg.risk
        risk_amount = equity * (r.risk_per_trade_pct / 100)
        qty = risk_amount / stop_distance
        notional = qty * entry
        if notional > r.leverage_cap * equity:
            qty = (r.leverage_cap * equity) / entry
        return qty

    def _manage(self, pos: _Position, bar: Kline, window: list[Kline],
                equity: float, result: BacktestResult) -> float | None:
        long = pos.direction == Direction.LONG
        # 1. Stop hit?
        if (long and bar.low <= pos.stop) or (not long and bar.high >= pos.stop):
            return self._close(pos, pos.stop, pos.qty, result, "stop")
        # 2. Scale out at +1R, move to breakeven.
        tp1 = (pos.entry + self.cfg.execution.tp1_r_multiple * pos.r_value if long
               else pos.entry - self.cfg.execution.tp1_r_multiple * pos.r_value)
        if not pos.scaled and ((long and bar.high >= tp1) or (not long and bar.low <= tp1)):
            scale_qty = pos.qty * (self.cfg.execution.tp1_size_pct / 100)
            partial = self._realize(pos, tp1, scale_qty, result, "tp1_scale")
            pos.qty -= scale_qty
            pos.scaled = True
            pos.stop = pos.entry  # breakeven
            return None if pos.qty > 0 else partial
        # 3. ATR chandelier trail.
        closes = [k.close for k in window]
        highs = [k.high for k in window]
        lows = [k.low for k in window]
        atr = ind.atr(highs, lows, closes, self.cfg.strategy.atr_period)
        if atr:
            mult = self.cfg.strategy.atr_stop_mult
            if long:
                pos.stop = max(pos.stop, bar.close - atr * mult)
            else:
                pos.stop = min(pos.stop, bar.close + atr * mult)
        return None

    def _pnl(self, pos: _Position, exit_price: float, qty: float) -> float:
        gross = (exit_price - pos.entry) * qty if pos.direction == Direction.LONG \
            else (pos.entry - exit_price) * qty
        fee = exit_price * qty * self.fee_rate
        return gross - fee

    def _realize(self, pos: _Position, exit_price: float, qty: float,
                 result: BacktestResult, reason: str) -> float:
        """Record a partial close; returns realized pnl (net of exit fee)."""
        pnl = self._pnl(pos, exit_price, qty)
        result.trades.append(Trade(
            direction=pos.direction.value, entry_price=pos.entry, exit_price=exit_price,
            qty=qty, r_value=pos.r_value, pnl=pnl,
            r_multiple=pnl / (pos.r_value * qty) if pos.r_value and qty else 0.0,
            bars_held=pos.bars, exit_reason=reason,
        ))
        return pnl

    def _close(self, pos: _Position, exit_price: float, qty: float,
               result: BacktestResult, reason: str) -> float:
        return self._realize(pos, exit_price, qty, result, reason)


def load_klines_csv(path: str) -> list[Kline]:
    """Load Bybit-style kline rows from CSV: start,open,high,low,close,volume[,turnover]."""
    import csv

    out: list[Kline] = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].lower() in ("start", "timestamp", "time"):
                continue  # header
            out.append(Kline.from_bybit(row))
    return out
