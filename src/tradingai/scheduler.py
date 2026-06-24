"""Autonomous scheduler (Phase 4).

Runs the live tick on a fixed cadence, aligned to candle boundaries, isolating
per-tick errors so one failure never kills the loop, with graceful shutdown.
The timing helpers are pure and unit-tested; the loop takes injectable tick /
sleep / clock callables so it can be tested without real time or network.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from .config import Config
from .logging_setup import log_event, setup_logging


def next_tick_delay(now_ts: float, cadence_seconds: int) -> float:
    """Seconds until the next cadence boundary (e.g. top of the hour).

    Always returns a strictly positive delay so we never busy-loop.
    """
    if cadence_seconds <= 0:
        return 0.0
    remainder = now_ts % cadence_seconds
    delay = cadence_seconds - remainder
    if delay < 1e-6:
        delay = float(cadence_seconds)
    return delay


async def run_loop(
    cfg: Config,
    tick: Callable[[Config], Awaitable[int]],
    *,
    max_iterations: int | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.time,
    stop_event: asyncio.Event | None = None,
    logger=None,
) -> int:
    """Run ``tick`` repeatedly on the configured cadence. Returns iterations run."""
    logger = logger or setup_logging(cfg.runtime.log_level)
    cadence = cfg.runtime.cadence_minutes * 60
    iterations = 0
    consecutive_errors = 0

    while not (stop_event and stop_event.is_set()):
        try:
            await tick(cfg)
            consecutive_errors = 0
        except Exception as exc:  # one bad tick must not kill the loop
            consecutive_errors += 1
            log_event(logger, "ERROR", "tick failed",
                      error=repr(exc), consecutive_errors=consecutive_errors)

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break

        # Back off on repeated failures, otherwise align to the next candle.
        if consecutive_errors > 0:
            delay = min(cadence, 30 * consecutive_errors)
        else:
            delay = next_tick_delay(clock(), cadence)
        log_event(logger, "INFO", "sleeping until next tick", seconds=round(delay, 1))
        await sleep(delay)

    log_event(logger, "INFO", "loop stopped", iterations=iterations)
    return iterations


def run_forever(cfg: Config) -> int:
    """Entry point for the CLI: wire signals + the live tick into run_loop."""
    from .live import run_live_tick

    async def _main() -> int:
        logger = setup_logging(cfg.runtime.log_level)
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        try:
            import signal

            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):  # e.g. Windows / non-main thread
            pass
        log_event(logger, "INFO", "scheduler started",
                  cadence_minutes=cfg.runtime.cadence_minutes, symbols=cfg.market.symbols)
        return await run_loop(cfg, run_live_tick, stop_event=stop_event, logger=logger)

    return asyncio.run(_main())
