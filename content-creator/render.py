import base64
import html
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
# Auto-fit starts at these sizes (output px) and shrinks towards MIN_FONT_PX.
START_FONT_PX = {"hero_title": 96, "heading": 72, "body": 52}
# Fixed cover sizes (output px) for the subtitle and the handle.
HERO_SUBTITLE_PX = 44
HERO_HANDLE_PX = 34
# Card medallion width, as % of the panel's content width.
MEDALLION_WIDTH_PCT = {"start": 38, "min": 22}
# The parchment panel's inset from each edge of the slide, as % of the width.
PANEL_INSET_PCT = 9
HEADING_MAX_CHARS = 80

# Any "**Key:** `value`" line of visual-style.md (colours and the handle).
_PALETTE_LINE_RE = re.compile(r"\*\*(.+?):\*\*\s*`([^`]+)`")

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600'
    '&family=Lora:wght@400&display=swap" rel="stylesheet">'
)

# Runs in the page before the screenshot: shrinks every [data-role] font
# size (all together) until #fit-content fits, never below its data-min; if it
# still overflows, shrinks the #medallion. Returns the final sizes in output px.
FIT_SCRIPT = """
<script>
window.fitSlide = async function () {
  await document.fonts.ready;
  const content = document.getElementById('fit-content');
  const box = content.parentElement;
  const texts = [...document.querySelectorAll('[data-role]')];
  const fits = () => {
    if (content.scrollWidth > content.clientWidth + 0.5) return false;
    if (content.dataset.maxLines) {
      const lineHeight = parseFloat(getComputedStyle(content).lineHeight);
      return content.offsetHeight <= content.dataset.maxLines * lineHeight + 1;
    }
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
  const medallion = document.getElementById('medallion');
  if (medallion) {
    let width = +medallion.dataset.start;
    while (!fits() && width > +medallion.dataset.min) {
      width = Math.max(+medallion.dataset.min, width - 1);
      medallion.style.width = width + '%';
    }
  }
  const result = {overflow: !fits()};
  texts.forEach(el => { result[el.dataset.role + '_px'] = parseFloat(el.style.fontSize) * SCALE; });
  if (medallion) result.medallion_pct = parseFloat(medallion.style.width);
  return result;
};
</script>
""".replace("SCALE", repr(DEVICE_SCALE_FACTOR))


class LowContrastError(Exception):
    pass


def load_palette(brand_pack):
    doc = (BRANDS_DIR / brand_pack / "visual-style.md").read_text(encoding="utf-8")
    return dict(_PALETTE_LINE_RE.findall(doc))


def _base_px(output_px):
    return output_px / DEVICE_SCALE_FACTOR


def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return ",".join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))


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
        f'<html><head><meta charset="utf-8">{FONT_LINK}</head>'
        f'<body style="margin:0;width:{BASE_WIDTH}px;height:{BASE_HEIGHT}px;'
        f'position:relative;overflow:hidden;{body_style}">{inner}{FIT_SCRIPT}</body></html>'
    )


def _build_hero_html(slide_text, image_b64, palette):
    text_color = palette["Fundo (pergaminho)"]
    scrim = palette["Moldura escura"]
    check_contrast("hero_title", text_color, scrim)
    check_contrast("caption", text_color, scrim)
    title, subtitle = split_heading(slide_text)
    if title is None:
        title, subtitle = subtitle, None
    subtitle_html = (
        f'<p style="margin:0 0 {_base_px(18)}px;font-size:{_base_px(HERO_SUBTITLE_PX)}px;'
        f'line-height:1.25;">{html.escape(subtitle)}</p>' if subtitle else ""
    )
    side = _base_px(70)
    fade = f"rgba({_rgb(scrim)},0.85),rgba({_rgb(scrim)},0)"
    inner = (
        f'<div style="position:absolute;left:0;right:0;top:0;height:42%;'
        f'background:linear-gradient(to bottom,{fade});"></div>'
        f'<div style="position:absolute;left:0;right:0;bottom:0;height:34%;'
        f'background:linear-gradient(to top,{fade});"></div>'
        f'<div style="position:absolute;top:{_base_px(90)}px;left:{side}px;right:{side}px;'
        f'text-align:center;">'
        f'<h1 id="fit-content" data-max-lines="3" {_fit_attrs("hero_title")} '
        'style="margin:0;font-weight:500;line-height:1.1;text-transform:uppercase;'
        f'letter-spacing:0.08em;">{html.escape(title)}</h1></div>'
        f'<div style="position:absolute;bottom:{_base_px(70)}px;left:{side}px;right:{side}px;'
        'text-align:center;">'
        f"{subtitle_html}"
        f'<p style="margin:0;font-size:{_base_px(HERO_HANDLE_PX)}px;opacity:0.85;">'
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
        f'stroke="{gold}" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
    medallion = MEDALLION_WIDTH_PCT
    inner = (
        f'<div style="position:absolute;inset:{inset}px;background:{parchment};'
        f"box-shadow:inset 0 0 {_base_px(90)}px rgba(120,90,40,0.22);"
        "display:flex;align-items:center;justify-content:center;"
        f'padding:{_base_px(84)}px {_base_px(56)}px;box-sizing:border-box;">'
        '<div id="fit-content" style="width:100%;display:flex;flex-direction:column;'
        f'align-items:center;text-align:center;color:{text_color};overflow-wrap:break-word;">'
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
    image_b64 = base64.b64encode(image_bytes).decode()
    if slide_role == "hero":
        return _build_hero_html(slide_text, image_b64, palette)
    return _build_card_html(slide_text, image_b64, palette, is_last)


def render_png(html, fit=None):
    """Screenshot the slide at 1080x1350 after the in-page auto-fit has run.
    Pass a dict as `fit` to receive the final font sizes (output px), the
    medallion width and whether the content still overflows."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": BASE_WIDTH, "height": int(BASE_HEIGHT)},
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        page.set_content(html)
        result = page.evaluate(
            "window.fitSlide ? window.fitSlide() : document.fonts.ready.then(() => null)"
        )
        if fit is not None and result:
            fit.update(result)
        png_bytes = page.screenshot()
        browser.close()
        return png_bytes
