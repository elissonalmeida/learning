from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_app_loads_without_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
