import base64
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BRANDS_DIR = Path(__file__).parent / "brands"

# Standard Instagram portrait carousel size.
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1350
BASE_WIDTH = 420
DEVICE_SCALE_FACTOR = OUTPUT_WIDTH / BASE_WIDTH
BASE_HEIGHT = OUTPUT_HEIGHT / DEVICE_SCALE_FACTOR

MIN_FONT_PX = {"hero_title": 58, "heading": 43, "body": 34, "caption": 24}
MIN_CONTRAST = {"hero_title": 3.0, "heading": 4.5, "body": 4.5, "caption": 4.5}

_PALETTE_LINE_RE = re.compile(r"\*\*(.+?):\*\*\s*`(#[0-9A-Fa-f]{6})`")


class LowContrastError(Exception):
    pass


def load_palette(brand_pack):
    doc = (BRANDS_DIR / brand_pack / "visual-style.md").read_text(encoding="utf-8")
    return dict(_PALETTE_LINE_RE.findall(doc))


def _base_font_px(role):
    return MIN_FONT_PX[role] / DEVICE_SCALE_FACTOR


def _relative_luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    channels = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a, hex_b):
    l1, l2 = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def check_contrast(role, text_color, background_color):
    ratio = contrast_ratio(text_color, background_color)
    if ratio < MIN_CONTRAST[role]:
        raise LowContrastError(
            f"Contraste {ratio:.2f}:1 entre {text_color} e {background_color} é "
            f"insuficiente para '{role}' (mínimo {MIN_CONTRAST[role]}:1)."
        )


def build_slide_html(slide_text, image_bytes, brand_pack, slide_role):
    palette = load_palette(brand_pack)
    background = palette["Fundo (pergaminho)"]
    frame = palette["Moldura/estrutura"]
    text_color = "#2C1A0E"
    image_b64 = base64.b64encode(image_bytes).decode()

    if slide_role == "hero":
        title_px = _base_font_px("hero_title")
        return (
            f"<html><body style=\"margin:0;width:{BASE_WIDTH}px;height:{BASE_HEIGHT}px;"
            f"background-image:url(data:image/png;base64,{image_b64});"
            "background-size:cover;background-position:center;"
            "font-family:'DM Sans',sans-serif;position:relative;\">"
            f"<div style=\"position:absolute;bottom:24px;left:24px;right:24px;"
            "color:#fff;font-family:'Cormorant Garamond',serif;"
            f"font-size:{title_px}px;text-shadow:0 2px 6px rgba(0,0,0,0.6);\">"
            f"{slide_text}</div></body></html>"
        )

    check_contrast("body", text_color, background)
    body_px = _base_font_px("body")
    return (
        f"<html><body style=\"margin:0;width:{BASE_WIDTH}px;height:{BASE_HEIGHT}px;"
        f"background:{background};border:6px solid {frame};box-sizing:border-box;"
        "font-family:'DM Sans',sans-serif;display:flex;flex-direction:column;\">"
        f"<div style=\"height:55%;background-image:url(data:image/png;base64,{image_b64});"
        "background-size:cover;background-position:center;\"></div>"
        f"<div style=\"flex:1;padding:16px;color:{text_color};"
        f"font-size:{body_px}px;line-height:1.4;\">{slide_text}</div></body></html>"
    )


def render_png(html):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": BASE_WIDTH, "height": int(BASE_HEIGHT)},
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        page.set_content(html)
        png_bytes = page.screenshot()
        browser.close()
        return png_bytes
