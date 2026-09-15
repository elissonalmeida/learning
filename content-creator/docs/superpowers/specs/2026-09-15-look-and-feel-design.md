# Content Creator — Look & Feel Design Spec

## Background

This is backlog item #3 (`docs/backlog.md`, "AURA v2 scope"): a spec for the
shared visual language so the content-creator app's interface matches the
look and feel of `docs/reference/AURA_v4.html` — a hand-built, client-side
prototype the user made before this project, showing the intended UI/UX of
a much larger social-media-management tool. The user wants visual
continuity with that reference, not just its eventual functionality.

Two things this spec is explicitly *not* about, to avoid confusion with
similarly-named prior work:
- **Carousel image visual style** (colors/fonts baked into the generated
  Instagram slide PNGs) — that's `brands/marianabotelho-ig/visual-style.md`
  and `render.py`, covered by the v1.1 image-generation spec. It uses a
  different, brand-guide-sourced palette (green/red/gold parchment tones)
  from AURA v4's own UI chrome palette. This spec only touches the
  *operator-facing tool's own UI*, not the content it produces.
- **Carousel slide-style decisions** (photo-vs-text card layout) —
  `docs/mockups/v1.1-carousel-style/`, a separate, already-resolved
  question.

content-creator's actual app (`app.py`) is built in **Streamlit**, a
Python UI framework with a fundamentally different rendering model than
AURA v4's hand-written HTML/CSS/JS. Streamlit doesn't give free-form markup
control — theming happens through a `.streamlit/config.toml` file plus CSS
injected into the page via `st.markdown(..., unsafe_allow_html=True)`,
targeting Streamlit's own (undocumented, version-dependent) internal CSS
classes. True pixel parity with AURA v4 (its bottom-sheet modals, custom
bottom tab-bar, hand-built pill/date-box components) would require
replacing native widgets with embedded HTML components
(`st.components.v1.html`) and bridging their state back into Streamlit — a
much larger, more fragile undertaking that verges on rebuilding the
frontend. This spec deliberately does not do that; see Scope below.

## Purpose of this project

Give the content-creator app AURA v4's visual identity — palette,
typography, and component look (cards, pills, alerts, buttons) — using
Streamlit's native theming and CSS-injection mechanisms, so the tool feels
like the same product as the reference prototype without fighting
Streamlit's execution model.

## Scope

**In scope:**
- A global design-token set (colors, fonts, radii) matching AURA v4,
  applied via `.streamlit/config.toml` + one injected CSS block.
- Restyling every component the current app already uses: page header,
  tabs, buttons, status indicators (idea status, `st.success`/`warning`/
  `error`/`info`), and the progress checklist (`run_with_progress`).
- Hiding Streamlit's default chrome (hamburger menu, "Deploy" button,
  "Made with Streamlit" footer).
- Applying all of the above across the app's three existing tabs (Nova
  Ideia, Gerar Imagens, Biblioteca).

**Out of scope:**
- Narrowing the page to AURA's mobile-app width (~700px, centered). The
  app is a desktop tool operated at a desk, and existing multi-column
  layouts (slide image previews, thumbnail strips, Aprovar/Rejeitar button
  pairs) rely on wide layout. `layout="wide"` in `app.py` is unchanged.
- AURA's bottom-sheet modals, custom bottom tab-bar, and calendar/date-box
  components — these belong to backlog item #2 (Calendar) when that
  feature is actually built, per the backlog's own cross-dependency note
  ("design system should land before or alongside whichever UI feature
  gets built first").
- Any styling for Stories, Calendar, Dashboard, or other not-yet-built
  screens.
- Per-brand-pack theming (making the app's own chrome configurable per
  brand). AURA's palette is the *tool's* design system, not the managed
  brand's identity — it's reused here as a fixed, hardcoded skin, matching
  today's single-brand-pack reality. Multi-brand tool theming is a
  separate, currently hypothetical concern.
- Full pixel parity via embedded HTML components (`st.components.v1.html`)
  — rejected as a much larger, more fragile approach than the scope above;
  see Background.

## Design tokens

Lifted directly from `docs/reference/AURA_v4.html`'s `:root` variables, as
CSS custom properties:

```css
--bg: #F5EFE2;        --card: #FFFDF8;      --border: #D4C4A8;
--text: #2C1A0E;      --muted: #8B6A4A;     --brown: #3E2208;
--gold: #C4922A;      --gold-l: #FDF6E3;
--rosa: #B85C5C;      --rosa-l: #FAF0F0;
--sage: #7A9E6F;      --sage-l: #EEF4EB;
--purple: #534AB7;    --purple-l: #EEEDFE;
--blue: #185FA5;      --blue-l: #E6F1FB;
--cream: #EFE4D0;
```

Typography: `Cormorant Garamond` (serif, weights 400/600) for
titles/headings, `DM Sans` (weights 300–600) for body text and controls —
both loaded via the same Google Fonts URL AURA v4 uses.

Shape: 8–12px border radius on cards/buttons/pills, 1.5px borders on cards
and inputs — matching AURA's `.card`/`.btn`/`.pill` rules.

## Architecture

One new module, following the same pattern as existing brand-agnostic
modules (`ai.py`, `pipeline.py`):

```
content-creator/
  .streamlit/
    config.toml     NEW: base theme (backgroundColor, primaryColor,
                     font) so Streamlit's own default styling starts
                     from AURA's palette before any CSS override runs
  theme.py          NEW: inject_theme() — builds and returns the CSS
                     block (Google Fonts @import, component overrides,
                     Streamlit-chrome hiding rules); render_status_pill(),
                     render_alert() — small helpers returning HTML
                     snippets for the two component patterns that need
                     more than a CSS override (status pills, alerts)
  app.py            calls theme.inject_theme() once, near the top,
                     right after st.set_page_config()
```

`theme.py` responsibilities:
- `inject_theme()` — a single `st.markdown(CSS, unsafe_allow_html=True)`
  call containing: the Google Fonts `@import`, CSS custom properties,
  Streamlit widget-class overrides (buttons, tabs, containers, alert
  boxes, `st.status`), and rules hiding `#MainMenu`, `header
  [data-testid="stToolbar"]`, and `footer`.
- `render_status_pill(status)` — returns an HTML `<span>` styled as an
  AURA `.pill`, color-mapped per idea status:
  - `idea` → gold, `reviewed` → blue, `approved` → sage,
    `rejected` → rosa, `images_ready` → purple, `archived` → muted
    (AURA's `.pill-muted`)
  - Used in the Biblioteca tab's expander labels in place of the current
    plain-text `({idea['status']})`.
- Streamlit's native `st.success`/`st.warning`/`st.error`/`st.info` calls
  are restyled in place via CSS targeting their `data-testid` attributes
  (`stSuccess`→sage, `stWarning`→gold, `stError`→rosa, `stInfo`→blue) —
  no code changes needed at call sites in `app.py`.
- The `run_with_progress` checklist (`app.py`) keeps its existing
  `st.status`/`st.markdown` structure; CSS overrides restyle the
  `st.status` container border/background to match AURA's `.check-item`
  card look, and the ⏳/✅/❌ prefix convention already in place is kept
  as-is (AURA's own check-mark pattern, just with different bullet glyphs
  — not worth reconciling for a cosmetic difference).

## Application to existing screens

- **Header:** `st.title(...)` call is preceded by a CSS rule turning
  Streamlit's title-block background into AURA's `.hdr` treatment (brown
  background bar, gold serif text) rather than changing `app.py`'s title
  call itself.
- **Tabs (Nova Ideia / Gerar Imagens / Biblioteca):** CSS overrides
  `[data-testid="stTabs"]` to match AURA's `.nav`/`.nav-btn` look — rosa
  underline + rosa text on the active tab, muted text on inactive tabs.
- **Buttons:** primary actions (Gerar rascunho, Aprovar, Gerar imagem)
  styled rosa background per AURA's `.btn-primary`; secondary/destructive
  actions (Rejeitar, Eliminar definitivamente, Arquivar) use AURA's
  `.btn-muted` (cream background, brown text, bordered) — same visual
  hierarchy AURA uses between its primary and muted button variants.
- **Biblioteca idea list:** each `st.expander` gains a `render_status_pill`
  badge appended to its label; no structural change to the expander
  itself (Streamlit doesn't allow custom HTML inside expander labels'
  interactive chrome, so the pill is rendered as inline text with color
  via a small amount of unicode/HTML Streamlit does support in expander
  labels — confirmed during implementation, see Testing).

## Error handling

None needed — this is a pure styling change. No new failure modes: if
`inject_theme()` doesn't render correctly (e.g. a future Streamlit version
changes its internal class names), the app still functions with default
Streamlit styling, just visually inconsistent. This is a real, accepted
risk of the CSS-injection approach (Streamlit's internal classes aren't a
public API) — noted here rather than mitigated, since there's no
Streamlit-supported alternative that gives this level of control.

## Testing

- Manual visual verification is the primary check here (this is a styling
  spec — there's no meaningful unit test for "does this look like AURA").
  Run the app (`streamlit run app.py`) and compare each of the three tabs
  against `docs/reference/AURA_v4.html` opened side-by-side in a browser.
- Confirm expander labels actually render the status-pill HTML (Streamlit
  expander label support for embedded markup is limited and
  version-dependent) before relying on it — if it doesn't render cleanly,
  fall back to a plain colored-text status word instead of a full pill
  shape.
- Confirm the CSS override selectors still match after `pip list | grep
  streamlit` is checked against the currently pinned version in
  `requirements.txt` — internal class names can change across Streamlit
  releases, so this is worth a quick sanity check even though no
  version bump is planned as part of this work.
- No changes to `pipeline.py`, `db.py`, `ai.py`, `image_gen.py`, or
  `render.py` — existing test suite (`tests/`) is unaffected and should
  still pass unchanged.
