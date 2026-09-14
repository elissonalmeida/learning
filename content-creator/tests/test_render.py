import base64
import pytest
import render


def test_load_palette_parses_hex_colors():
    palette = render.load_palette("marianabotelho-ig")
    assert palette["Fundo (pergaminho)"] == "#efe4d0"
    assert palette["Moldura/estrutura"] == "#83ae37"


def test_contrast_ratio_black_on_white_is_maximal():
    assert render.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)


def test_check_contrast_raises_when_colors_are_too_similar():
    with pytest.raises(render.LowContrastError):
        render.check_contrast("body", "#efe4d0", "#e7d1a8")  # both light tan, low contrast


def test_check_contrast_passes_for_dark_text_on_light_background():
    render.check_contrast("body", "#2C1A0E", "#efe4d0")  # should not raise


def test_build_slide_html_hero_embeds_image_and_text():
    image_bytes = b"\x89PNG-fake"
    html = render.build_slide_html("Ritual matinal", image_bytes, "marianabotelho-ig", "hero")
    assert "Ritual matinal" in html
    assert base64.b64encode(image_bytes).decode() in html


def test_build_slide_html_card_uses_brand_frame_color():
    html = render.build_slide_html("3 passos", b"\x89PNG-fake", "marianabotelho-ig", "card")
    assert "#83ae37" in html


def test_build_slide_html_respects_minimum_body_font_size():
    html = render.build_slide_html("texto", b"\x89PNG-fake", "marianabotelho-ig", "card")
    expected_px = render.MIN_FONT_PX["body"] / render.DEVICE_SCALE_FACTOR
    assert f"{expected_px}px" in html
