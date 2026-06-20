from tradingai import indicators as ind


def test_sma_basic():
    assert ind.sma([1, 2, 3, 4], 2) == 3.5
    assert ind.sma([1, 2], 5) is None


def test_ema_trends_up():
    rising = list(range(1, 60))
    e = ind.ema(rising, 10)
    assert e is not None and e < rising[-1]  # EMA lags a rising series


def test_rsi_all_gains_is_100():
    assert ind.rsi(list(range(1, 30)), 14) == 100.0


def test_rsi_all_losses_is_low():
    val = ind.rsi(list(range(30, 0, -1)), 14)
    assert val is not None and val < 5


def test_rsi_insufficient_data():
    assert ind.rsi([1, 2, 3], 14) is None


def test_atr_positive():
    highs = [10 + i for i in range(20)]
    lows = [8 + i for i in range(20)]
    closes = [9 + i for i in range(20)]
    a = ind.atr(highs, lows, closes, 14)
    assert a is not None and a > 0


def test_volume_zscore_spike():
    # Baseline with mild variation around 100, then a large spike.
    vols = [100.0 + (i % 5) for i in range(20)] + [300.0]
    z = ind.volume_zscore(vols, 20)
    assert z is not None and z > 3


def test_volume_zscore_flat_baseline_is_zero():
    # Zero-variance baseline -> defined as 0.0 (no signal), not a divide error.
    assert ind.volume_zscore([100.0] * 20 + [300.0], 20) == 0.0


def test_macd_histogram_runs():
    vals = [float(i) for i in range(1, 80)]
    assert ind.macd_histogram(vals) is not None
