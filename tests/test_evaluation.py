from tradingai import evaluation
from tradingai import market_data as md


def test_parse_closed_pnl_chronological():
    result = {"list": [
        {"symbol": "BTCUSDT", "side": "Sell", "qty": "0.01", "avgEntryPrice": "100",
         "avgExitPrice": "110", "closedPnl": "0.1", "createdTime": "2"},
        {"symbol": "BTCUSDT", "side": "Sell", "qty": "0.01", "avgEntryPrice": "100",
         "avgExitPrice": "90", "closedPnl": "-0.1", "createdTime": "1"},
    ]}
    trades = md.parse_closed_pnl(result)
    # reversed to oldest-first
    assert [t["created_time"] for t in trades] == ["1", "2"]
    assert trades[0]["closed_pnl"] == -0.1


def test_summarize_decisions():
    decisions = [
        {"action": "HOLD"}, {"action": "HOLD"}, {"action": "DECIDED"},
    ]
    s = evaluation.summarize_decisions(decisions)
    assert s["total_decisions"] == 3
    assert s["by_action"]["HOLD"] == 2
    assert s["by_action"]["DECIDED"] == 1


def test_evaluate_report_structure():
    closed = [
        {"symbol": "BTCUSDT", "side": "Buy", "closed_pnl": 12.0},
        {"symbol": "BTCUSDT", "side": "Buy", "closed_pnl": -4.0},
    ]
    decisions = [{"action": "DECIDED"}]
    report = evaluation.evaluate(closed, decisions, initial_equity=1000.0)
    assert report["performance"]["n_trades"] == 2
    assert report["performance"]["total_pnl"] == 8.0
    assert report["performance"]["final_equity"] == 1008.0
    assert "go_live_gate" in report
    assert report["go_live_gate"]["positive_expectancy"] is True
    # Only 2 trades -> not enough for the gate.
    assert report["go_live_gate"]["enough_trades (>=30)"] is False
    assert report["go_live_gate"]["PASS"] is False


def test_evaluate_empty_is_safe():
    report = evaluation.evaluate([], [], initial_equity=1000.0)
    assert report["performance"]["n_trades"] == 0
    assert report["go_live_gate"]["PASS"] is False
