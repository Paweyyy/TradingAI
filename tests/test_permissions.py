from tradingai.config import Config
from tradingai.permissions import make_permission_hook
from tradingai.planning import OrderPlan
from tradingai.risk import AccountState, RiskManager


def _acct():
    return AccountState(equity=1000, peak_equity=1000, day_start_equity=1000,
                        open_positions=0, orders_this_tick=0, last_price=50000)


def _plan(qty=0.02, side="Buy"):
    return OrderPlan(symbol="BTCUSDT", side=side, qty=qty, entry_price=50000,
                     stop_price=49500, take_profit_price=50500, leverage=3, reasons=[])


def _hook(plan):
    risk = RiskManager(Config())
    return make_permission_hook(risk, _acct, "BTCUSDT", plan_provider=lambda: plan)


def test_denies_withdrawal_tools():
    hook = _hook(_plan())
    res = hook("mcp__bybit__withdraw", {"coin": "USDT", "amount": "1"})
    assert res["behavior"] == "deny"


def test_allows_read_tools():
    hook = _hook(_plan())
    res = hook("mcp__bybit__get_kline", {"symbol": "BTCUSDT"})
    assert res["behavior"] == "allow"


def test_allows_order_matching_plan():
    hook = _hook(_plan(qty=0.02, side="Buy"))
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.02", "price": "50000", "leverage": "3"})
    assert res["behavior"] == "allow"


def test_denies_order_with_wrong_qty():
    # 0.04 BTC @ 50000 = 2000 notional: passes the 3x risk cap (<3000) but is
    # double the planned 0.02, so the plan check (not risk) must reject it.
    hook = _hook(_plan(qty=0.02, side="Buy"))
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.04", "price": "50000", "leverage": "3"})
    assert res["behavior"] == "deny"
    assert "PLAN MISMATCH" in res["message"]


def test_denies_order_with_wrong_side():
    hook = _hook(_plan(qty=0.02, side="Buy"))
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Sell", "qty": "0.02", "price": "50000", "leverage": "3"})
    assert res["behavior"] == "deny"
    assert "PLAN MISMATCH" in res["message"]


def test_denies_opening_order_when_no_plan():
    hook = _hook(None)  # no valid setup this tick
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.02", "price": "50000", "leverage": "3"})
    assert res["behavior"] == "deny"
    assert "NO PLAN" in res["message"]


def test_allows_reduce_only_close_without_plan():
    hook = _hook(None)
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Sell", "qty": "0.02", "price": "50000",
                "leverage": "3", "reduceOnly": True})
    assert res["behavior"] == "allow"


def test_order_still_blocked_by_risk_even_if_plan_matches():
    # Over-leverage must be caught by the Risk Layer before the plan check.
    risk = RiskManager(Config())
    hook = make_permission_hook(risk, _acct, "BTCUSDT", plan_provider=lambda: _plan(qty=0.02))
    res = hook("mcp__bybit__place_order",
               {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.02", "price": "50000", "leverage": "50"})
    assert res["behavior"] == "deny"
    assert "RISK BLOCK" in res["message"]
