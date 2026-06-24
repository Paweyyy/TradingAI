import asyncio

import pytest

from tradingai.config import Config
from tradingai.scheduler import next_tick_delay, run_loop


def test_next_tick_delay_aligns_to_boundary():
    # 3600s cadence, 100s past the hour -> 3500s until next boundary.
    assert next_tick_delay(100.0, 3600) == 3500.0


def test_next_tick_delay_on_boundary_returns_full_cadence():
    # Exactly on a boundary -> wait a full cadence, never 0 (no busy loop).
    assert next_tick_delay(7200.0, 3600) == 3600.0


def test_next_tick_delay_zero_cadence():
    assert next_tick_delay(123.0, 0) == 0.0


def _run(coro):
    return asyncio.run(coro)


def test_run_loop_runs_n_times():
    cfg = Config()
    calls = {"n": 0}

    async def tick(_cfg):
        calls["n"] += 1
        return 0

    async def fake_sleep(_seconds):
        return None

    iterations = _run(run_loop(cfg, tick, max_iterations=3, sleep=fake_sleep))
    assert iterations == 3
    assert calls["n"] == 3


def test_run_loop_survives_tick_errors():
    cfg = Config()
    calls = {"n": 0}

    async def flaky_tick(_cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return 0

    async def fake_sleep(_seconds):
        return None

    iterations = _run(run_loop(cfg, flaky_tick, max_iterations=2, sleep=fake_sleep))
    assert iterations == 2  # loop kept going past the error
    assert calls["n"] == 2


def test_run_loop_stops_on_event():
    cfg = Config()
    stop = None

    async def driver():
        nonlocal stop
        stop = asyncio.Event()

        async def tick(_cfg):
            stop.set()  # request stop after first tick
            return 0

        async def fake_sleep(_seconds):
            return None

        return await run_loop(cfg, tick, sleep=fake_sleep, stop_event=stop)

    iterations = _run(driver())
    assert iterations == 1


def test_run_loop_backs_off_on_consecutive_errors():
    cfg = Config()
    delays: list[float] = []

    async def always_fails(_cfg):
        raise RuntimeError("nope")

    async def record_sleep(seconds):
        delays.append(seconds)

    _run(run_loop(cfg, always_fails, max_iterations=2, sleep=record_sleep))
    # First (and only recorded) backoff should be the 30s * 1 error backoff, not full cadence.
    assert delays and delays[0] == 30
