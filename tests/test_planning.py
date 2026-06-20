from tradingai.config import Config
from tradingai.planning import build_order_plan
from tradingai.risk import RiskManager
from tradingai.strategy import Direction, TradeSetup


def _rm():
    return RiskManager(Config())


def test_no_plan_for_invalid_setup():
    setup = TradeSetup("BTCUSDT", Direction.NONE, valid=False, reasons=["chop"])
    assert build_order_plan(Config(), _rm(), setup, 1000, 50000) is None


def test_long_plan_sizing_and_levels():
    cfg = Config()
    setup = TradeSetup("BTCUSDT", Direction.LONG, valid=True, reasons=["ok"], stop_distance=500)
    plan = build_order_plan(cfg, _rm(), setup, equity=1000, last_price=50000)
    assert plan is not None
    assert plan.side == "Buy"
    # risk 1% of 1000 = 10; stop 500 -> qty 0.02 (rounded to 3 dp)
    assert plan.qty == 0.02
    assert plan.stop_price == 49500       # entry - stop_distance
    assert plan.take_profit_price == 50500  # entry + 1R


def test_short_plan_levels_mirror():
    cfg = Config()
    setup = TradeSetup("BTCUSDT", Direction.SHORT, valid=True, reasons=["ok"], stop_distance=500)
    plan = build_order_plan(cfg, _rm(), setup, equity=1000, last_price=50000)
    assert plan.side == "Sell"
    assert plan.stop_price == 50500
    assert plan.take_profit_price == 49500


def test_plan_qty_rounds_to_step():
    cfg = Config()
    # stop distance that yields a non-round qty -> rounded to 3 decimals
    setup = TradeSetup("BTCUSDT", Direction.LONG, valid=True, reasons=["ok"], stop_distance=333)
    plan = build_order_plan(cfg, _rm(), setup, equity=1000, last_price=50000)
    assert plan.qty == round((1000 * 0.01 / 333), 3)
