import pytest
from config import load_config, ConfigError, DEFAULT_DB_PATH, DEFAULT_MAX_DAILY_SPEND_USD, DEFAULT_BRAND_PACK

def test_raises_when_api_key_missing():
    with pytest.raises(ConfigError):
        load_config(env={})

def test_applies_defaults_when_only_api_key_set():
    cfg = load_config(env={"ANTHROPIC_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.db_path == DEFAULT_DB_PATH
    assert cfg.max_daily_spend_usd == DEFAULT_MAX_DAILY_SPEND_USD
    assert cfg.brand_pack == DEFAULT_BRAND_PACK

def test_overrides_are_respected():
    cfg = load_config(env={
        "ANTHROPIC_API_KEY": "sk-test",
        "DB_PATH": "C:\\custom\\path.db",
        "MAX_DAILY_SPEND_USD": "5.5",
        "BRAND_PACK": "other-brand",
    })
    assert cfg.db_path == "C:\\custom\\path.db"
    assert cfg.max_daily_spend_usd == 5.5
    assert cfg.brand_pack == "other-brand"
