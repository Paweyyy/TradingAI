"""Lightweight JSON state store: equity tracking, daily counters, idempotency."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class StateStore:
    def __init__(self, state_dir: str | Path) -> None:
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "state.json"
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "peak_equity": 0.0,
            "day_start_equity": 0.0,
            "day": "",
            "seen_order_ids": [],
            "decisions": [],
        }

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, default=str))

    def roll_day(self, equity: float) -> None:
        """Reset daily counters at the start of a new UTC day."""
        today = date.today().isoformat()
        if self._data.get("day") != today:
            self._data["day"] = today
            self._data["day_start_equity"] = equity
        self.save()

    def update_equity(self, equity: float) -> None:
        self._data["peak_equity"] = max(self._data.get("peak_equity", 0.0), equity)
        self.save()

    @property
    def peak_equity(self) -> float:
        return self._data.get("peak_equity", 0.0)

    @property
    def day_start_equity(self) -> float:
        return self._data.get("day_start_equity", 0.0)

    def is_duplicate(self, order_id: str) -> bool:
        return order_id in self._data.get("seen_order_ids", [])

    def record_order(self, order_id: str) -> None:
        self._data.setdefault("seen_order_ids", []).append(order_id)
        self.save()

    def record_decision(self, decision: dict) -> None:
        self._data.setdefault("decisions", []).append(decision)
        self._data["decisions"] = self._data["decisions"][-200:]
        self.save()
