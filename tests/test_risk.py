import pytest

from tradingai.config import Config
from tradingai.risk import AccountState, OrderIntent, RiskManager


@pytest.fixture
def rm() -> RiskManager:
    return RiskManager(Config())  # demo defaults


@pytest.fixture
def acct() -> AccountState:
    return AccountState(equity=1000, peak_equity=1000, day_start_equity=1000,
                        open_positions=0, orders_this_tick=0, last_price=50000)


def test_blocks_when_not_demo(acct):
    cfg = Config()
    cfg.mode.demo = False
    rm = RiskManager(cfg)
    intent = OrderIntent("PF_XBTUSD", "buy", qty=0.001, price=50000, leverage=2)
    assert rm.validate_order(intent, acct).approved is False


def test_allows_sane_order(rm, acct):
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=50000, leverage=2)
    assert rm.validate_order(intent, acct).approved is True


def test_rejects_over_leverage(rm, acct):
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=50000, leverage=10)
    assert rm.validate_order(intent, acct).approved is False


def test_rejects_over_notional(rm, acct):
    # 1 BTC * 50000 = 50000 notional >> 3x * 1000 equity
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=1.0, price=50000, leverage=3)
    assert rm.validate_order(intent, acct).approved is False


def test_rejects_when_max_positions_reached(rm, acct):
    acct.open_positions = 1
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=50000, leverage=2)
    assert rm.validate_order(intent, acct).approved is False


def test_fat_finger_price_guard(rm, acct):
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=60000, leverage=2)  # 20% off
    assert rm.validate_order(intent, acct).approved is False


def test_order_rate_limit(rm, acct):
    acct.orders_this_tick = 2  # default cap is 2
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=50000, leverage=2)
    assert rm.validate_order(intent, acct).approved is False


def test_kill_switch_blocks(rm, acct):
    rm.trip_kill_switch("test")
    intent = OrderIntent("PF_XBTUSD", "Buy", qty=0.001, price=50000, leverage=2)
    assert rm.validate_order(intent, acct).approved is False


def test_daily_loss_breaker_trips(rm):
    acct = AccountState(equity=960, peak_equity=1000, day_start_equity=1000, open_positions=0)
    res = rm.check_breakers(acct)  # -4% < -3% limit
    assert res.approved is False
    assert rm.kill_switch_active is True


def test_drawdown_breaker_trips(rm):
    acct = AccountState(equity=840, peak_equity=1000, day_start_equity=900, open_positions=0)
    rm.check_breakers(acct)  # -16% drawdown < -15%
    assert rm.kill_switch_active is True


def test_sizing_fixed_fractional(rm):
    # risk 1% of 1000 = 10; stop distance 500 -> qty 0.02
    s = rm.size_position(equity=1000, entry=50000, stop_distance=500)
    assert round(s.qty, 5) == 0.02


def test_sizing_clamped_by_leverage(rm):
    # tiny stop would imply huge qty; must clamp to 3x * 1000 = 3000 notional
    s = rm.size_position(equity=1000, entry=50000, stop_distance=1)
    assert s.notional <= 3000 + 1e-6
    assert any("clamp" in r for r in s.reasons)


def test_reduce_only_bypasses_position_cap(rm, acct):
    acct.open_positions = 1
    intent = OrderIntent("PF_XBTUSD", "Sell", qty=0.001, price=50000, leverage=2, reduce_only=True)
    assert rm.validate_order(intent, acct).approved is True
