import tomllib
from pathlib import Path
from unittest.mock import patch

import streamlit.config as st_config
from streamlit.testing.v1 import AppTest

import theme

CONFIG_PATH = Path(__file__).parent.parent / ".streamlit" / "config.toml"
APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_config_toml_sets_aura_palette_and_fonts():
    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    theme_cfg = config["theme"]
    assert theme_cfg["primaryColor"] == "#B85C5C"
    assert theme_cfg["backgroundColor"] == "#F5EFE2"
    assert theme_cfg["secondaryBackgroundColor"] == "#FFFDF8"
    assert theme_cfg["textColor"] == "#2C1A0E"
    assert theme_cfg["borderColor"] == "#D4C4A8"
    assert "DM Sans" in theme_cfg["font"]
    assert "Cormorant Garamond" in theme_cfg["headingFont"]
    assert theme_cfg["redColor"] == "#B85C5C"
    assert theme_cfg["orangeColor"] == "#C4922A"
    assert theme_cfg["greenColor"] == "#7A9E6F"
    assert theme_cfg["blueColor"] == "#185FA5"
    assert theme_cfg["violetColor"] == "#534AB7"
    assert theme_cfg["grayColor"] == "#8B6A4A"
    assert theme_cfg["yellowColor"] == "#C4922A"


def test_config_toml_hides_default_toolbar():
    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    assert config["client"]["toolbarMode"] == "minimal"


def test_config_toml_is_valid_for_the_installed_streamlit():
    """Loads config.toml through Streamlit's own config machinery (not just
    tomllib), so a key Streamlit rejects or ignores would be caught."""
    with open(CONFIG_PATH, "rb") as f:
        raw_theme = tomllib.load(f)["theme"]

    valid_options = st_config.get_config_options(force_reparse=True)
    for key in raw_theme:
        assert f"theme.{key}" in valid_options, f"theme.{key} is not a valid Streamlit config option"

    assert st_config.get_option("theme.yellowColor") == "#C4922A"
    assert st_config.get_where_defined("theme.yellowColor") == str(CONFIG_PATH)


def test_inject_theme_renders_header_css_with_unsafe_html():
    with patch("theme.st") as mock_st:
        theme.inject_theme()

    mock_st.markdown.assert_called_once()
    args, kwargs = mock_st.markdown.call_args
    assert "app-header" in args[0]
    assert kwargs["unsafe_allow_html"] is True


def test_render_header_includes_title_text_and_class():
    with patch("theme.st") as mock_st:
        theme.render_header("Content Creator — marianabotelho-ig")

    mock_st.markdown.assert_called_once()
    html_out = mock_st.markdown.call_args[0][0]
    assert "app-header-title" in html_out
    assert "Content Creator — marianabotelho-ig" in html_out


def test_render_header_escapes_html_in_title():
    with patch("theme.st") as mock_st:
        theme.render_header("<script>alert(1)</script>")

    html_out = mock_st.markdown.call_args[0][0]
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_app_renders_custom_header_instead_of_default_title(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
    assert not at.title
    header_blocks = [el.value for el in at.markdown if "app-header-title" in el.value]
    assert any("Content Creator" in block for block in header_blocks)
