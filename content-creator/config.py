import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = r"C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db"
DEFAULT_MAX_DAILY_SPEND_USD = 2.0
DEFAULT_BRAND_PACK = "marianabotelho-ig"


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, api_key, gemini_api_key, db_path, max_daily_spend_usd, brand_pack):
        self.api_key = api_key
        self.gemini_api_key = gemini_api_key
        self.db_path = db_path
        self.max_daily_spend_usd = max_daily_spend_usd
        self.brand_pack = brand_pack


def load_config(env=None):
    env = env if env is not None else os.environ
    api_key = env.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file before running the app."
        )
    gemini_api_key = env.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ConfigError(
            "GEMINI_API_KEY is not set. Add it to a .env file before running the app."
        )
    db_path = env.get("DB_PATH", DEFAULT_DB_PATH)
    max_daily_spend_usd = float(env.get("MAX_DAILY_SPEND_USD", DEFAULT_MAX_DAILY_SPEND_USD))
    brand_pack = env.get("BRAND_PACK", DEFAULT_BRAND_PACK)
    return Config(api_key, gemini_api_key, db_path, max_daily_spend_usd, brand_pack)
