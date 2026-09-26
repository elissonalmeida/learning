import base64
import io
from pathlib import Path

import pytest
from PIL import Image

import render

BRAND = "marianabotelho-ig"
FAKE_IMAGE = b"\x89PNG-fake"

SATURNO_LONG = (
    "SATURNO — CHUMBO — BAÇO\n\n"
    "O peso do tempo. Na alquimia antiga, Saturno regia o chumbo e o baço, o órgão que "
    "guarda o que ainda não conseguimos digerir. Quando o corpo carrega tristezas antigas, "
    "o baço sente. O chumbo não é castigo: é a matéria densa que pede paciência, silêncio "
    "e tempo para se transformar. Cuidar do baço é aprender a soltar devagar, sem pressa, "
    "o que já não nos serve — e deixar que o tempo faça a sua parte."
)


def _real_png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 80), "#7a8f5a").save(buffer, format="PNG")
    return buffer.getvalue()


def test_load_palette_parses_hex_colors():
    palette = render.load_palette(BRAND)
    assert palette["Fundo (pergaminho)"] == "#efe4d0"
    assert palette["Moldura/estrutura"] == "#83ae37"


def test_load_palette_reads_dark_frame_text_colour_and_handle():
    palette = render.load_palette(BRAND)
    assert palette["Moldura escura"].startswith("#")
    assert palette["Texto escuro"].startswith("#")
    assert palette["Handle"] == "@marianabotelho.pt"


def test_contrast_ratio_black_on_white_is_maximal():
    assert render.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)


def test_check_contrast_raises_when_colors_are_too_similar():
    with pytest.raises(render.LowContrastError):
        render.check_contrast("body", "#efe4d0", "#e7d1a8")  # both light tan, low contrast


def test_check_contrast_passes_for_dark_text_on_light_background():
    render.check_contrast("body", "#2C1A0E", "#efe4d0")  # should not raise


def test_brand_card_text_colour_passes_contrast_on_parchment():
    palette = render.load_palette(BRAND)
    render.check_contrast("body", palette["Texto escuro"], palette["Fundo (pergaminho)"])


# --- heading / body split -------------------------------------------------

def test_split_heading_uses_short_first_paragraph_as_heading():
    heading, body = render.split_heading("SATURNO — CHUMBO — BAÇO\n\nO peso do tempo.")
    assert heading == "SATURNO — CHUMBO — BAÇO"
    assert body == "O peso do tempo."


def test_split_heading_handles_windows_newlines_and_extra_blank_lines():
    heading, body = render.split_heading("Título\r\n\r\n\r\nCorpo do texto.\r\nSegunda linha.")
    assert heading == "Título"
    assert body == "Corpo do texto.\nSegunda linha."


def test_split_heading_without_blank_line_has_no_heading():
    assert render.split_heading("Uma frase só.\nOutra linha.") == (None, "Uma frase só.\nOutra linha.")


def test_split_heading_long_first_paragraph_is_not_a_heading():
    first = "a" * 81
    assert render.split_heading(f"{first}\n\nresto") == (None, f"{first}\n\nresto")


def test_split_heading_first_paragraph_of_exactly_80_chars_is_a_heading():
    first = "a" * 80
    assert render.split_heading(f"{first}\n\nresto") == (first, "resto")


# --- card structure -------------------------------------------------------

def test_card_uses_dark_frame_parchment_panel_and_gold_medallion_from_palette(monkeypatch):
    monkeypatch.setattr(render, "load_palette", lambda brand_pack: {
        "Fundo (pergaminho)": "#fafafa", "Moldura escura": "#123456",
        "Acento dourado": "#abcdef", "Texto escuro": "#010203", "Handle": "@x",
    })
    html = render.build_slide_html("Título\n\nCorpo", FAKE_IMAGE, BRAND, "card")
    assert "background:#123456" in html
    assert "background:#fafafa" in html
    assert 'id="medallion"' in html
    assert "solid #abcdef" in html
    assert "color:#010203" in html
    assert base64.b64encode(FAKE_IMAGE).decode() in html


def test_card_splits_heading_and_body_into_separate_elements():
    html = render.build_slide_html(
        "SATURNO — CHUMBO — BAÇO\n\nO peso do tempo.", FAKE_IMAGE, BRAND, "card",
    )
    assert '<h1 id="heading"' in html
    assert ">SATURNO — CHUMBO — BAÇO</h1>" in html
    assert ">O peso do tempo.</p>" in html
    assert "Lora" in html and "Cormorant Garamond" in html


def test_card_without_heading_has_no_heading_element():
    html = render.build_slide_html("Só corpo, sem título.", FAKE_IMAGE, BRAND, "card")
    assert 'id="heading"' not in html
    assert ">Só corpo, sem título.</p>" in html


def test_card_escapes_text():
    html = render.build_slide_html("<b>oi</b>", FAKE_IMAGE, BRAND, "card")
    assert "<b>oi</b>" not in html
    assert "&lt;b&gt;oi&lt;/b&gt;" in html


def test_card_shows_arrow_unless_it_is_the_last_slide():
    assert 'id="arrow"' in render.build_slide_html("t", FAKE_IMAGE, BRAND, "card", is_last=False)
    assert 'id="arrow"' not in render.build_slide_html("t", FAKE_IMAGE, BRAND, "card", is_last=True)


# --- hero structure -------------------------------------------------------

def test_hero_embeds_image_and_uppercase_title_at_top():
    html = render.build_slide_html("Ritual matinal", FAKE_IMAGE, BRAND, "hero")
    assert "Ritual matinal" in html
    assert base64.b64encode(FAKE_IMAGE).decode() in html
    assert "text-transform:uppercase" in html
    assert "linear-gradient(to bottom" in html  # top scrim for contrast


def test_hero_handle_comes_from_the_brand_pack(monkeypatch):
    palette = render.load_palette(BRAND)
    monkeypatch.setattr(render, "load_palette", lambda brand_pack: {**palette, "Handle": "@outra.marca"})
    html = render.build_slide_html("Título", FAKE_IMAGE, BRAND, "hero")
    assert "@outra.marca" in html
    assert "@marianabotelho.pt" not in html


def test_hero_shows_subtitle_paragraph():
    html = render.build_slide_html(
        "Elixir Limpeza\n\nO que é. Para que serve. Como usar.", FAKE_IMAGE, BRAND, "hero",
    )
    assert ">Elixir Limpeza</h1>" in html
    assert ">O que é. Para que serve. Como usar.</p>" in html


def test_hero_has_no_arrow():
    assert 'id="arrow"' not in render.build_slide_html("Título", FAKE_IMAGE, BRAND, "hero")


# --- auto-fit, measured in a real browser ---------------------------------

def _render(text, role, is_last=False):
    fit = {}
    png = render.render_png(render.build_slide_html(text, _real_png_bytes(), BRAND, role, is_last=is_last), fit=fit)
    return png, fit


def test_short_card_text_uses_the_large_sizes_and_fits():
    png, fit = _render("O que é?\n\nUm spray de frequência vibracional.", "card")
    assert Image.open(io.BytesIO(png)).size == (render.OUTPUT_WIDTH, render.OUTPUT_HEIGHT)
    assert fit["heading_px"] == pytest.approx(render.START_FONT_PX["heading"], abs=0.5)
    assert fit["body_px"] == pytest.approx(render.START_FONT_PX["body"], abs=0.5)
    assert fit["overflow"] is False


def test_long_card_text_shrinks_but_stays_readable_and_fits():
    _, fit = _render(SATURNO_LONG, "card")
    assert fit["body_px"] < render.START_FONT_PX["body"]
    assert fit["body_px"] >= render.MIN_FONT_PX["body"]
    assert fit["heading_px"] >= render.MIN_FONT_PX["heading"]
    assert fit["overflow"] is False


def test_very_long_card_text_shrinks_the_medallion_before_going_below_minimum():
    _, fit = _render(SATURNO_LONG + " " + SATURNO_LONG.split("\n\n")[1], "card")
    assert fit["body_px"] == pytest.approx(render.MIN_FONT_PX["body"], abs=0.5)
    assert fit["medallion_pct"] < render.MEDALLION_WIDTH_PCT["start"]
    assert fit["medallion_pct"] >= render.MEDALLION_WIDTH_PCT["min"]


def test_hero_title_fits_in_at_most_three_lines():
    _, fit = _render("Metais planetários e o corpo\n\nO que é. Para que serve.", "hero")
    assert fit["hero_title_px"] >= render.MIN_FONT_PX["hero_title"]
    assert fit["overflow"] is False


def test_long_hero_title_shrinks_to_three_lines_without_going_below_minimum():
    _, fit = _render("Alquimia do corpo: os sete metais planetários e os órgãos", "hero")
    assert fit["hero_title_px"] < render.START_FONT_PX["hero_title"]
    assert fit["hero_title_px"] >= render.MIN_FONT_PX["hero_title"]
    assert fit["overflow"] is False


# --- review round: long words, hero subtitle, honest contrast, brand keys, offline fonts ---

def _solid_png_bytes(colour):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 80), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_very_long_single_word_is_broken_inside_the_panel():
    _, fit = _render("Palavra\n\n" + "Supercalifragilístico" * 5, "card")
    assert fit["overflow"] is False


def test_very_long_card_text_reports_overflow():
    _, fit = _render(SATURNO_LONG + (" " + SATURNO_LONG.split("\n\n")[1]) * 3, "card")
    assert fit["overflow"] is True


def test_long_hero_subtitle_shrinks_to_fit():
    subtitle = "O que é, para que serve, como se usa no dia a dia e porque faz sentido para ti."
    _, fit = _render(f"Elixir\n\n{subtitle}", "hero")
    assert render.MIN_FONT_PX["body"] <= fit["hero_subtitle_px"] < render.START_FONT_PX["hero_subtitle"]
    assert fit["overflow"] is False


def test_hero_subtitle_too_long_even_at_minimum_reports_overflow():
    subtitle = "Uma frase comprida que continua e continua. " * 6
    _, fit = _render(f"Elixir\n\n{subtitle}", "hero")
    assert fit["overflow"] is True


def _blend(fg, bg, alpha):
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(alpha * x + (1 - alpha) * y) for x, y in zip(f, b))


def test_hero_scrim_is_at_full_strength_behind_the_title_and_the_bottom_text():
    palette = render.load_palette(BRAND)
    fit = {}
    png = render.render_png(
        render.build_slide_html(
            "Alquimia do corpo: os sete metais planetários e os órgãos\n\nO que é. Para que serve.",
            _solid_png_bytes("#ffffff"), BRAND, "hero",
        ),
        fit=fit,
    )
    image = Image.open(io.BytesIO(png)).convert("RGB")
    expected = _blend(palette["Moldura escura"], "#ffffff", render.SCRIM_ALPHA)
    for top, bottom in (fit["boxes"]["hero-title"], fit["boxes"]["hero-bottom"]):
        for y in (top, (top + bottom) / 2, bottom - 1):
            pixel = image.getpixel((4, int(y)))
            assert all(abs(p - e) <= 3 for p, e in zip(pixel, expected)), (y, pixel, expected)


def test_hero_contrast_check_accounts_for_scrim_strength_and_handle_opacity(monkeypatch):
    palette = render.load_palette(BRAND)
    # Passes against the plain scrim colour (5.1:1) but not once the scrim is
    # blended over a white image and the handle is drawn at its opacity.
    assert render.contrast_ratio(palette["Fundo (pergaminho)"], "#3a5c3c") >= 4.5
    monkeypatch.setattr(render, "load_palette", lambda brand_pack: {**palette, "Moldura escura": "#3a5c3c"})
    with pytest.raises(render.LowContrastError):
        render.build_slide_html("Título", FAKE_IMAGE, BRAND, "hero")


@pytest.mark.parametrize("role, key", [
    ("hero", "Handle"), ("hero", "Moldura escura"), ("card", "Moldura escura"), ("card", "Texto escuro"),
])
def test_missing_brand_key_raises_a_clear_error(monkeypatch, role, key):
    palette = render.load_palette(BRAND)
    del palette[key]
    monkeypatch.setattr(render, "load_palette", lambda brand_pack: palette)
    with pytest.raises(render.BrandPackError) as excinfo:
        render.build_slide_html("Título\n\nCorpo", FAKE_IMAGE, BRAND, role)
    message = str(excinfo.value)
    assert key in message
    assert f"brands/{BRAND}/visual-style.md" in message


@pytest.mark.parametrize("role", ["hero", "card"])
def test_slide_html_embeds_local_fonts_and_never_calls_google_fonts(role):
    html = render.build_slide_html("Título\n\nCorpo", FAKE_IMAGE, BRAND, role)
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "@font-face" in html


def test_render_works_offline_with_the_bundled_fonts(monkeypatch):
    import socket

    real_connect = socket.socket.connect

    def local_only(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise OSError("rede bloqueada neste teste")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    for role, fonts in (("hero", {"Cormorant Garamond"}), ("card", {"Cormorant Garamond", "Lora"})):
        png, fit = _render("Título\n\nCorpo do texto.", role)
        assert Image.open(io.BytesIO(png)).size == (render.OUTPUT_WIDTH, render.OUTPUT_HEIGHT)
        assert fonts <= set(fit["fonts_loaded"])


def test_font_licences_are_bundled_with_the_fonts():
    fonts = Path(render.__file__).parent / "assets" / "fonts"
    for name in ("CormorantGaramond", "Lora"):
        assert (fonts / f"OFL-{name}.txt").read_text(encoding="utf-8").count("Open Font License") >= 1
