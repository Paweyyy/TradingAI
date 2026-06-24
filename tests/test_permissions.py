from tradingai.config import Config
from tradingai.permissions import make_permission_hook
from tradingai.planning import OrderPlan
from tradingai.risk import AccountState, RiskManager

SYMBOL = "PF_XBTUSD"
SEND = "kraken__send_order"   # matches the order-mutating hint "send_order"
READ = "kraken__get_tickers"  # read-only market tool


def _acct():
    return AccountState(equity=1000, peak_equity=1000, day_start_equity=1000,
                        open_positions=0, orders_this_tick=0, last_price=50000)


def _plan(qty=0.02, side="buy"):
    return OrderPlan(symbol=SYMBOL, side=side, qty=qty, entry_price=50000,
                     stop_price=49500, take_profit_price=50500, leverage=3, reasons=[])


def _hook(plan):
    risk = RiskManager(Config())
    return make_permission_hook(risk, _acct, SYMBOL, plan_provider=lambda: plan)


def _order(**over):
    base = {"symbol": SYMBOL, "side": "buy", "size": "0.02", "limitPrice": "50000"}
    base.update(over)
    return base


def test_denies_withdrawal_tools():
    res = _hook(_plan())("kraken__withdraw", {"currency": "USD", "amount": "1"})
    assert res["behavior"] == "deny"


def test_allows_read_tools():
    assert _hook(_plan())(READ, {"symbol": SYMBOL})["behavior"] == "allow"


def test_allows_order_matching_plan_and_injects_size():
    res = _hook(_plan(qty=0.02, side="buy"))(SEND, _order(size="0.02"))
    assert res["behavior"] == "allow"
    # Size is force-injected (Kraken 'size' field) so the order is exactly the plan.
    assert res["updatedInput"]["size"] == "0.02"
    assert res["updatedInput"]["side"] == "buy"


def test_wrong_qty_is_corrected_not_rejected():
    # 0.04 BTC @ 50000 = 2000 notional: within the 3x risk cap, double the planned
    # 0.02. Instead of rejecting, the hook injects the planned size.
    res = _hook(_plan(qty=0.02, side="buy"))(SEND, _order(size="0.04"))
    assert res["behavior"] == "allow"
    assert res["updatedInput"]["size"] == "0.02"


def test_dangerously_oversized_submission_is_denied():
    # 1 BTC = 50000 notional >> 3x*1000; safety net denies even with a matching plan.
    res = _hook(_plan(qty=0.02, side="buy"))(SEND, _order(size="1.0"))
    assert res["behavior"] == "deny"
    assert "RISK BLOCK" in res["message"]


def test_denies_order_with_wrong_side():
    res = _hook(_plan(qty=0.02, side="buy"))(SEND, _order(side="sell"))
    assert res["behavior"] == "deny"
    assert "PLAN MISMATCH" in res["message"]


def test_denies_opening_order_when_no_plan():
    res = _hook(None)(SEND, _order())
    assert res["behavior"] == "deny"
    assert "NO PLAN" in res["message"]


def test_allows_reduce_only_close_without_plan():
    res = _hook(None)(SEND, _order(side="sell", reduceOnly=True))
    assert res["behavior"] == "allow"


def test_order_still_blocked_by_risk_even_if_plan_matches():
    risk = RiskManager(Config())
    hook = make_permission_hook(risk, _acct, SYMBOL, plan_provider=lambda: _plan(qty=0.02))
    res = hook(SEND, _order(leverage="50"))
    assert res["behavior"] == "deny"
    assert "RISK BLOCK" in res["message"]
