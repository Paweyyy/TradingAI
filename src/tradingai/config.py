"""Typed configuration loader.

Loads ``config/config.yaml`` (path overridable via ``TRADINGAI_CONFIG``) and
validates it with pydantic. Secrets come from environment variables, never YAML.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class ModeConfig(BaseModel):
    testnet: bool = True
    dry_run: bool = False


class MarketConfig(BaseModel):
    category: str = "linear"
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    trend_timeframe: str = "240"
    entry_timeframe: str = "60"
    klines_limit: int = 250
    qty_decimals: int = 3  # order qty rounding (BTC perp step is 0.001)


class StrategyConfig(BaseModel):
    name: str = "htf_trend_following"
    prompt_file: str = "config/strategies/default.md"
    ema_fast: int = 50
    ema_slow: int = 200
    ema_entry: int = 20
    rsi_period: int = 14
    atr_period: int = 14
    atr_stop_mult: float = 1.5
    volume_ma_period: int = 20
    entry_style: str = "pullback"
    funding_extreme_abs: float = 0.0005
    sentiment_guard: bool = True
    fng_extreme_greed: int = 85
    fng_extreme_fear: int = 15


class RiskConfig(BaseModel):
    risk_per_trade_pct: float = 1.0
    leverage_cap: int = 3
    max_positions: int = 1
    daily_loss_limit_pct: float = 3.0
    max_drawdown_pause_pct: float = 15.0
    max_orders_per_tick: int = 2
    price_sanity_pct: float = 5.0

    @field_validator("leverage_cap")
    @classmethod
    def _leverage_sane(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("leverage_cap must be between 1 and 5 in v1")
        return v


class ExecutionConfig(BaseModel):
    prefer_maker: bool = True
    tp1_r_multiple: float = 1.0
    tp1_size_pct: float = 50.0
    trail: str = "ema20_4h"


class RuntimeConfig(BaseModel):
    cadence_minutes: int = 60
    model: str = "claude-opus-4-8"
    state_dir: str = "state"
    log_level: str = "INFO"


class Config(BaseModel):
    mode: ModeConfig = Field(default_factory=ModeConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


def default_config_path() -> Path:
    return Path(os.environ.get("TRADINGAI_CONFIG", "config/config.yaml"))


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate configuration from YAML."""
    cfg_path = Path(path) if path is not None else default_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    data = yaml.safe_load(cfg_path.read_text()) or {}
    return Config(**data)
