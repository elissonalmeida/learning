import base64
import functools
import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BRANDS_DIR = Path(__file__).parent / "brands"
FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

# Standard Instagram portrait carousel size.
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1350
BASE_WIDTH = 420
DEVICE_SCALE_FACTOR = OUTPUT_WIDTH / BASE_WIDTH
BASE_HEIGHT = OUTPUT_HEIGHT / DEVICE_SCALE_FACTOR

MIN_FONT_PX = {"hero_title": 58, "hero_subtitle": 34, "heading": 43, "body": 34, "caption": 24}
MIN_CONTRAST = {"hero_title": 3.0, "heading": 4.5, "body": 4.5, "caption": 4.5}
# Auto-fit starts at these sizes (output px) and shrinks towards MIN_FONT_PX.
START_FONT_PX = {"hero_title": 96, "hero_subtitle": 44, "heading": 72, "body": 52}
# Fixed cover size (output px) for the handle.
HERO_HANDLE_PX = 34
HERO_HANDLE_OPACITY = 0.9
# The cover's scrim is this opaque everywhere behind its text (the page grows
# the solid part to cover the text after fitting), so contrast is checked
# against the scrim blended over the worst case: a white image.
SCRIM_ALPHA = 0.88
WORST_CASE_IMAGE = "#ffffff"
# Card medallion width, as % of the panel's content width.
MEDALLION_WIDTH_PCT = {"start": 38, "min": 22}
# The parchment panel's inset from each edge of the slide, as % of the width.
PANEL_INSET_PCT = 9
HEADING_MAX_CHARS = 80

# Brand-pack keys each slide type needs from visual-style.md.
REQUIRED_KEYS = {
    "hero": ("Fundo (pergaminho)", "Moldura escura", "Handle"),
    "card": ("Fundo (pergaminho)", "Moldura escura", "Acento dourado", "Texto escuro"),
}

# Any "**Key:** `value`" line of visual-style.md (colours and the handle).
_PALETTE_LINE_RE = re.compile(r"\*\*(.+?):\*\*\s*`([^`]+)`")

# Bundled OFL fonts (see assets/fonts/OFL-*.txt), embedded so rendering never
# depends on the network.
FONT_FILES = {
    "Cormorant Garamond": "CormorantGaramond[wght].ttf",
    "Lora": "Lora[wght].ttf",
}

# Runs in the page before the screenshot. For every [data-fit] block, shrinks
# its [data-role] font sizes (all together) until it fits, never below
# data-min; then, if a #medallion is inside, shrinks it. Then grows each
# [data-scrim] so its solid part covers the element it protects. Returns the
# final sizes (output px), overflow, element boxes and the loaded fonts.
FIT_SCRIPT = """
<script>
window.fitSlide = async function () {
  await document.fonts.ready;
  const result = {overflow: false, boxes: {}};
  for (const content of document.querySelectorAll('[data-fit]')) {
    const texts = content.matches('[data-role]') ? [content] : [...content.querySelectorAll('[data-role]')];
    const fits = () => {
      if (content.scrollWidth > content.clientWidth + 0.5) return false;
      if (content.dataset.maxLines) {
        const lineHeight = parseFloat(getComputedStyle(content).lineHeight);
        return content.offsetHeight <= content.dataset.maxLines * lineHeight + 1;
      }
      const box = content.parentElement;
      const bs = getComputedStyle(box);
      const room = box.clientHeight - parseFloat(bs.paddingTop) - parseFloat(bs.paddingBottom);
      return content.offsetHeight <= room + 0.5;
    };
    let factor = 1;
    const apply = () => texts.forEach(el => {
      el.style.fontSize = Math.max(+el.dataset.min, el.dataset.start * factor) + 'px';
    });
    apply();
    // Compare the unrounded sizes: the browser may round the stored value up.
    while (!fits() && texts.some(el => el.dataset.start * factor > +el.dataset.min)) {
      factor *= 0.98;
      apply();
    }
    const medallion = content.querySelector('#medallion');
    if (medallion) {
      let width = +medallion.dataset.start;
      while (!fits() && width > +medallion.dataset.min) {
        width = Math.max(+medallion.dataset.min, width - 1);
        medallion.style.width = width + '%';
      }
      result.medallion_pct = parseFloat(medallion.style.width);
    }
    if (!fits()) result.overflow = true;
    texts.forEach(el => { result[el.dataset.role + '_px'] = parseFloat(el.style.fontSize) * SCALE; });
  }
  for (const scrim of document.querySelectorAll('[data-scrim]')) {
    const target = document.getElementById(scrim.dataset.cover).getBoundingClientRect();
    const fromTop = scrim.dataset.scrim === 'top';
    const solid = (fromTop ? target.bottom : innerHeight - target.top) + 8;
    const rgb = scrim.dataset.rgb, alpha = scrim.dataset.alpha;
    scrim.style.height = (solid + innerHeight * 0.15) + 'px';
    scrim.style.background = `linear-gradient(to ${fromTop ? 'bottom' : 'top'}, ` +
      `rgba(${rgb},${alpha}) 0px, rgba(${rgb},${alpha}) ${solid}px, rgba(${rgb},0) 100%)`;
  }
  for (const el of document.querySelectorAll('[id]')) {
    const r = el.getBoundingClientRect();
    result.boxes[el.id] = [r.top * SCALE, r.bottom * SCALE];
  }
  result.fonts_loaded = [...document.fonts].filter(f => f.status === 'loaded')
    .map(f => f.family.replace(/["']/g, ''));
  return result;
};
</script>
""".replace("SCALE", repr(DEVICE_SCALE_FACTOR))


class LowContrastError(Exception):
    pass


class BrandPackError(Exception):
    pass


def load_palette(brand_pack):
    doc = (BRANDS_DIR / brand_pack / "visual-style.md").read_text(encoding="utf-8")
    return dict(_PALETTE_LINE_RE.findall(doc))


def _require_keys(palette, brand_pack, slide_role):
    for key in REQUIRED_KEYS[slide_role]:
        if key not in palette:
            raise BrandPackError(
                f"Falta a chave '{key}' em brands/{brand_pack}/visual-style.md. "
                f"Acrescenta uma linha como: - **{key}:** `valor`"
            )


@functools.lru_cache(maxsize=1)
def _font_face_css():
    faces = []
    for family, filename in FONT_FILES.items():
        data = base64.b64encode((FONTS_DIR / filename).read_bytes()).decode()
        faces.append(
            f"@font-face{{font-family:'{family}';font-weight:300 700;"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');}}"
        )
    return "".join(faces)


def _base_px(output_px):
    return output_px / DEVICE_SCALE_FACTOR


def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return ",".join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))


def _blend(fg_hex, bg_hex, alpha):
    fg = [int(fg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    bg = [int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(alpha * f + (1 - alpha) * b):02x}" for f, b in zip(fg, bg))


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


def split_heading(slide_text):
    """(heading, body) when the text opens with a short paragraph followed by a
    blank line; otherwise (None, the whole text)."""
    text = slide_text.replace("\r\n", "\n").strip()
    parts = re.split(r"\n\s*\n", text, maxsplit=1)
    if len(parts) == 2 and len(parts[0].strip()) <= HEADING_MAX_CHARS and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, text


def _fit_attrs(role):
    return (
        f'data-role="{role}" data-start="{_base_px(START_FONT_PX[role])}" '
        f'data-min="{_base_px(MIN_FONT_PX[role])}"'
    )


def _page(body_style, inner):
    return (
        f'<html><head><meta charset="utf-8"><style>{_font_face_css()}</style></head>'
        f'<body style="margin:0;width:{BASE_WIDTH}px;height:{BASE_HEIGHT}px;'
        f'position:relative;overflow:hidden;{body_style}">{inner}{FIT_SCRIPT}</body></html>'
    )


def _scrim(side, cover_id, color):
    direction = "bottom" if side == "top" else "top"
    fade = f"rgba({_rgb(color)},{SCRIM_ALPHA}),rgba({_rgb(color)},0)"
    return (
        f'<div data-scrim="{side}" data-cover="{cover_id}" data-rgb="{_rgb(color)}" '
        f'data-alpha="{SCRIM_ALPHA}" style="position:absolute;left:0;right:0;{side}:0;height:40%;'
        f'background:linear-gradient(to {direction},{fade});"></div>'
    )


def _build_hero_html(slide_text, image_b64, palette):
    text_color = palette["Fundo (pergaminho)"]
    scrim = palette["Moldura escura"]
    behind_text = _blend(scrim, WORST_CASE_IMAGE, SCRIM_ALPHA)
    check_contrast("hero_title", text_color, behind_text)
    check_contrast("body", text_color, behind_text)
    check_contrast("caption", _blend(text_color, behind_text, HERO_HANDLE_OPACITY), behind_text)
    title, subtitle = split_heading(slide_text)
    if title is None:
        title, subtitle = subtitle, None
    subtitle_html = (
        f'<p id="hero-subtitle" data-fit data-max-lines="3" {_fit_attrs("hero_subtitle")} '
        f'style="margin:0 0 {_base_px(18)}px;line-height:1.25;">{html.escape(subtitle)}</p>'
        if subtitle else ""
    )
    side = _base_px(70)
    inner = (
        _scrim("top", "hero-title", scrim)
        + _scrim("bottom", "hero-bottom", scrim)
        + f'<div style="position:absolute;top:{_base_px(90)}px;left:{side}px;right:{side}px;'
        'text-align:center;">'
        f'<h1 id="hero-title" data-fit data-max-lines="3" {_fit_attrs("hero_title")} '
        'style="margin:0;font-weight:500;line-height:1.1;text-transform:uppercase;'
        f'letter-spacing:0.08em;">{html.escape(title)}</h1></div>'
        f'<div id="hero-bottom" style="position:absolute;bottom:{_base_px(70)}px;left:{side}px;'
        f'right:{side}px;text-align:center;">'
        f"{subtitle_html}"
        f'<p style="margin:0;font-size:{_base_px(HERO_HANDLE_PX)}px;opacity:{HERO_HANDLE_OPACITY};">'
        f"{html.escape(palette['Handle'])}</p></div>"
    )
    return _page(
        f"background-image:url(data:image/png;base64,{image_b64});background-size:cover;"
        f"background-position:center;color:{text_color};"
        "font-family:'Cormorant Garamond',serif;",
        inner,
    )


def _build_card_html(slide_text, image_b64, palette, is_last):
    parchment = palette["Fundo (pergaminho)"]
    frame = palette["Moldura escura"]
    gold = palette["Acento dourado"]
    text_color = palette["Texto escuro"]
    check_contrast("heading", text_color, parchment)
    check_contrast("body", text_color, parchment)
    heading, body = split_heading(slide_text)
    inset = BASE_WIDTH * PANEL_INSET_PCT / 100
    heading_html = (
        f'<h1 id="heading" {_fit_attrs("heading")} style="margin:0 0 0.45em;'
        "font-family:'Cormorant Garamond',serif;font-weight:600;line-height:1.1;\">"
        f"{html.escape(heading)}</h1>" if heading else ""
    )
    arrow_html = "" if is_last else (
        f'<svg id="arrow" viewBox="0 0 60 16" style="position:absolute;right:6%;bottom:4.5%;'
        f'width:{_base_px(110)}px;"><path d="M1 8H57M49 1.5L57 8L49 14.5" fill="none" '
        f'stroke="{gold}" stroke-width="2.6" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
    medallion = MEDALLION_WIDTH_PCT
    inner = (
        f'<div style="position:absolute;inset:{inset}px;background:{parchment};'
        f"box-shadow:inset 0 0 {_base_px(90)}px rgba(120,90,40,0.22);"
        "display:flex;align-items:center;justify-content:center;"
        f'padding:{_base_px(84)}px {_base_px(56)}px;box-sizing:border-box;">'
        '<div id="fit-content" data-fit style="width:100%;display:flex;flex-direction:column;'
        f'align-items:center;text-align:center;color:{text_color};overflow-wrap:anywhere;">'
        f'<div id="medallion" data-start="{medallion["start"]}" data-min="{medallion["min"]}" '
        f'style="width:{medallion["start"]}%;aspect-ratio:4/5;border-radius:50%;flex:none;'
        f"border:{_base_px(4)}px solid {gold};"
        f"background-image:url(data:image/png;base64,{image_b64});background-size:cover;"
        f'background-position:center;margin-bottom:{_base_px(40)}px;"></div>'
        f"{heading_html}"
        f'<p id="body" {_fit_attrs("body")} style="margin:0;font-family:\'Lora\',serif;'
        f'line-height:1.35;white-space:pre-line;">{html.escape(body)}</p>'
        f"</div>{arrow_html}</div>"
    )
    return _page(f"background:{frame};", inner)


def build_slide_html(slide_text, image_bytes, brand_pack, slide_role, is_last=False):
    palette = load_palette(brand_pack)
    _require_keys(palette, brand_pack, "hero" if slide_role == "hero" else "card")
    image_b64 = base64.b64encode(image_bytes).decode()
    if slide_role == "hero":
        return _build_hero_html(slide_text, image_b64, palette)
    return _build_card_html(slide_text, image_b64, palette, is_last)


def render_png(html, fit=None):
    """Screenshot the slide at 1080x1350 after the in-page auto-fit has run.
    Pass a dict as `fit` to receive the final font sizes (output px), the
    medallion width, whether the content still overflows, element boxes and
    the fonts that loaded. The page never touches the network."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": BASE_WIDTH, "height": int(BASE_HEIGHT)},
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        page.route(re.compile(r"^https?://"), lambda route: route.abort())
        page.set_content(html)
        result = page.evaluate(
            "window.fitSlide ? window.fitSlide() : document.fonts.ready.then(() => null)"
        )
        if fit is not None and result:
            fit.update(result)
        png_bytes = page.screenshot()
        browser.close()
        return png_bytes
