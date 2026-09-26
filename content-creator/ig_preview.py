"""Instagram-post mock for the carousel preview (#49). Pure HTML/CSS, no
brand text: the handle and optional avatar come from the brand pack."""
import base64
import html

# Instagram cuts the caption at about two lines / 125 characters.
CAPTION_LIMIT = 125

CSS = """
<style>
.ig-post { width: 100%; max-width: 400px; background: #fff; border: 1px solid #dbdbdb;
  border-radius: 8px; overflow: hidden; color: #000;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 18px; }
.ig-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
.ig-avatar { width: 32px; height: 32px; border-radius: 50%; flex: none; overflow: hidden;
  display: flex; align-items: center; justify-content: center; background: #efefef;
  color: #262626; font-weight: 600; font-size: 13px; box-shadow: 0 0 0 1px #dbdbdb; }
.ig-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ig-handle { font-weight: 600; flex: 1; }
.ig-media { position: relative; aspect-ratio: 4 / 5; background: #efefef; }
.ig-media img { display: block; width: 100%; height: 100%; object-fit: cover; }
.ig-count { position: absolute; top: 12px; right: 12px; padding: 3px 8px; border-radius: 12px;
  background: rgba(18, 18, 18, 0.7); color: #fff; font-size: 12px; line-height: 18px; }
.ig-actions { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center;
  padding: 6px 8px; }
.ig-icons { display: flex; gap: 14px; padding: 0 4px; }
.ig-icons.right { justify-content: flex-end; }
.ig-icon { width: 24px; height: 24px; display: block; }
.ig-dots { display: flex; gap: 4px; }
.ig-dot { width: 6px; height: 6px; border-radius: 50%; background: #a8a8a8; }
.ig-dot.active { background: #0095F6; }
.ig-caption { padding: 2px 12px 14px; white-space: pre-line; overflow-wrap: anywhere; }
.ig-caption b { font-weight: 600; }
.ig-mais { color: #737373; }
</style>
"""

# st.html strips inline <svg>, so each icon is an <img> with an SVG data URI.
_ICON_PATHS = {
    "heart": '<path d="M16.8 3.5c-2 0-3.7 1-4.8 2.7-1.1-1.7-2.8-2.7-4.8-2.7C4.3 3.5 2 5.9 2 8.9'
             'c0 5.3 8.3 10.9 10 11.6 1.7-.7 10-6.3 10-11.6 0-3-2.3-5.4-5.2-5.4z"/>',
    "comment": '<path d="M20.7 17A10 10 0 1 0 17 20.6L22 22z"/>',
    "share": '<path d="M22 3 9.2 10.1"/><path d="M11.7 20.3 22 3H2l7.2 7.1z"/>',
    "bookmark": '<path d="M20 21l-8-7.6L4 21V3h16z"/>',
    "more": '<g fill="#262626" stroke="none"><circle cx="5" cy="12" r="1.5"/>'
            '<circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></g>',
}


def _icon(name):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#262626" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round">{_ICON_PATHS[name]}</svg>'
    )
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return f'<img class="ig-icon" src="{uri}" alt="">'


def short_caption(caption):
    """First two lines, at most CAPTION_LIMIT characters (cut at a word).
    Returns (text, was_cut)."""
    caption = caption.strip()
    short = "\n".join(caption.splitlines()[:2])
    if len(short) > CAPTION_LIMIT:
        short = short[:CAPTION_LIMIT].rsplit(" ", 1)[0]
    short = short.rstrip()
    if short != caption:
        short = short.rstrip(".,;:…")
    return short, short != caption


def post_html(image_uri, handle, avatar_uri, index, total, caption, full_caption=False):
    handle = handle.lstrip("@")  # Instagram shows the name without the @
    if avatar_uri:
        avatar = f'<img src="{avatar_uri}" alt="">'
    else:
        avatar = html.escape(handle[:1].upper())
    dots = "".join(
        f'<span class="ig-dot{" active" if k == index else ""}"></span>' for k in range(total)
    )
    text, was_cut = (caption.strip(), False) if full_caption else short_caption(caption)
    more = '… <span class="ig-mais">mais</span>' if was_cut else ""
    return (
        CSS
        + '<div class="ig-post">'
        + f'<div class="ig-head"><div class="ig-avatar">{avatar}</div>'
        + f'<span class="ig-handle">{html.escape(handle)}</span>{_icon("more")}</div>'
        + f'<div class="ig-media"><img src="{image_uri}" alt="Slide {index + 1}">'
        + f'<span class="ig-count">{index + 1}/{total}</span></div>'
        + f'<div class="ig-actions"><div class="ig-icons">{_icon("heart")}{_icon("comment")}{_icon("share")}</div>'
        + f'<div class="ig-dots">{dots}</div><div class="ig-icons right">{_icon("bookmark")}</div></div>'
        + f'<div class="ig-caption"><b>{html.escape(handle)}</b> {html.escape(text)}{more}</div>'
        + "</div>"
    )
