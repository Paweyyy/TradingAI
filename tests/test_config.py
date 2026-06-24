import pytest

from tradingai.config import Config, RiskConfig, load_config


def test_loads_repo_config():
    cfg = load_config("config/config.yaml")
    assert cfg.mode.demo is True
    assert "PF_XBTUSD" in cfg.market.symbols
    assert cfg.risk.leverage_cap <= 5


def test_defaults_are_demo():
    assert Config().mode.demo is True


def test_leverage_cap_validation():
    with pytest.raises(ValueError):
        RiskConfig(leverage_cap=20)


def test_missing_config_raises():
    with pytest.raises(FileNotFoundError):
        load_config("does/not/exist.yaml")
