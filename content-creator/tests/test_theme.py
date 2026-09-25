import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / ".streamlit" / "config.toml"


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


def test_config_toml_hides_default_toolbar():
    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    assert config["client"]["toolbarMode"] == "minimal"
