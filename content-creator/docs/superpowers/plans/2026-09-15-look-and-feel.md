# Content Creator — Look & Feel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the content-creator Streamlit app AURA v4's visual identity (palette, typography, component look) using Streamlit's native theming.

**Architecture:** A `.streamlit/config.toml` theme file carries almost the entire visual language (colors, fonts, radii, borders, toolbar visibility) through Streamlit's own documented `[theme]`/`[client]` config keys — no CSS-selector hacking needed for any of that. A small `theme.py` module covers the two things config.toml can't express: a bespoke branded header bar (replacing `st.title`) and a status-pill helper for idea statuses (built on Streamlit's native colored-markdown syntax, not raw HTML). `app.py` gets minimal, targeted edits: one new import, one call to inject the theme, one header-rendering swap, one expander-label change, and `type="primary"` added to the app's primary-action buttons.

**Tech Stack:** Streamlit 1.63 (native `[theme]` config, colored-markdown text directives), Python 3.14 stdlib `tomllib` for config tests, `pytest` + `unittest.mock` + `streamlit.testing.v1.AppTest` (existing project test stack).

**Spec:** `content-creator/docs/superpowers/specs/2026-09-15-look-and-feel-design.md`

## Global Constraints

- Palette, exact hex values (from AURA v4 / the spec) — do not invent or approximate substitutes:
  `bg=#F5EFE2 card=#FFFDF8 border=#D4C4A8 text=#2C1A0E muted=#8B6A4A brown=#3E2208 gold=#C4922A rosa=#B85C5C sage=#7A9E6F purple=#534AB7 blue=#185FA5`.
- Typography: `Cormorant Garamond` for headings, `DM Sans` for body — loaded via Streamlit's `headingFont`/`font` config keys pointing at Google Fonts, not a manual `@import`.
- `app.py` keeps `layout="wide"` — no layout narrowing (out of scope per spec).
- Prefer Streamlit's documented `[theme]`/`[client]` config keys over custom CSS wherever an official key achieves the same visual result. This plan found that most of the spec's originally-assumed CSS-injection work (alert-box colors, toolbar hiding, card/button/tab styling) is actually covered by documented config keys — CSS is used only where no config key exists (the custom header bar, the status pill).
- No changes to `pipeline.py`, `db.py`, `ai.py`, `image_gen.py`, `render.py`, or their tests.
- Idea status values this plan must color-map are exactly: `idea`, `reviewed`, `approved`, `rejected`, `images_ready`, `archived` (from `db.py`/`pipeline.py` — there is no `pending` or other status in the current codebase).

---

### Task 1: Global theme foundation (config.toml + branded header)

**Files:**
- Create: `content-creator/.streamlit/config.toml`
- Create: `content-creator/theme.py`
- Modify: `content-creator/app.py:1-10` (add `import theme`, call `theme.inject_theme()`), `content-creator/app.py:65` (replace `st.title(...)` with `theme.render_header(...)`)
- Test: `content-creator/tests/test_theme.py`

**Interfaces:**
- Consumes: nothing (first task, no dependencies).
- Produces: `theme.inject_theme() -> None`, `theme.render_header(title: str) -> None` — not consumed by later tasks in this plan, but this is the module Task 2 adds to.

**What this task covers with zero extra code (no separate task needed):** per the spec's component-mapping table, several AURA-look requirements are satisfied purely by the `config.toml` values in Step 3 above, through Streamlit's own documented theming — no CSS selectors, no call-site changes:
- **Tabs** (`st.tabs`) — the active tab's underline and any focus/selection accents use `primaryColor` (rosa) automatically; the tab-strip's bottom border uses `borderColor`.
- **`st.success`/`st.warning`/`st.error`/`st.info`** — these render using the theme's basic color palette (green/orange/red/blue respectively), so remapping `greenColor`/`orangeColor`/`redColor`/`blueColor` to AURA's sage/gold/rosa/blue makes every existing call site (e.g. `app.py`'s `st.error(str(e))`, `st.success(...)`, `st.info(...)`) render in AURA's colors with no code change.
- **The `run_with_progress` checklist** (`st.status` in `app.py`) — its container border/corner radius comes from `baseRadius`/`borderColor`, same as any other bordered container (expanders, forms). No code change needed.
None of the above has an automated color assertion (Streamlit's theme rendering isn't inspectable through `AppTest`) — they're covered instead by the "Manual visual verification" checklist at the end of this plan.

- [ ] **Step 1: Write the failing test for `config.toml`**

Create `content-creator/tests/test_theme.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with `FileNotFoundError` (no `.streamlit/config.toml` yet).

- [ ] **Step 3: Create `.streamlit/config.toml`**

Create `content-creator/.streamlit/config.toml`:

```toml
[theme]
base = "light"
primaryColor = "#B85C5C"
backgroundColor = "#F5EFE2"
secondaryBackgroundColor = "#FFFDF8"
textColor = "#2C1A0E"
borderColor = "#D4C4A8"
font = "DM Sans:https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap"
headingFont = "Cormorant Garamond:https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&display=swap"
baseRadius = "0.75rem"
buttonRadius = "0.5rem"
showWidgetBorder = true
redColor = "#B85C5C"
orangeColor = "#C4922A"
greenColor = "#7A9E6F"
blueColor = "#185FA5"
violetColor = "#534AB7"
grayColor = "#8B6A4A"

[client]
toolbarMode = "minimal"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: PASS (both `config.toml` tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/.streamlit/config.toml content-creator/tests/test_theme.py
git commit -m "feat: add AURA-palette Streamlit theme config"
```

- [ ] **Step 6: Write the failing tests for `theme.py`'s header functions**

Append to `content-creator/tests/test_theme.py`:

```python
from unittest.mock import patch

import theme


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
    html = mock_st.markdown.call_args[0][0]
    assert "app-header-title" in html
    assert "Content Creator — marianabotelho-ig" in html
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'theme'`.

- [ ] **Step 8: Create `theme.py`**

Create `content-creator/theme.py`:

```python
import streamlit as st

HEADER_CSS = """
<style>
.app-header {
    background: #3E2208;
    padding: 12px 18px;
    border-radius: 0.75rem;
    margin-bottom: 1rem;
}
.app-header-title {
    font-family: "Cormorant Garamond", serif;
    font-size: 28px;
    color: #C4922A;
    letter-spacing: 1px;
    margin: 0;
}
</style>
"""


def inject_theme():
    st.markdown(HEADER_CSS, unsafe_allow_html=True)


def render_header(title):
    st.markdown(
        f'<div class="app-header"><span class="app-header-title">{title}</span></div>',
        unsafe_allow_html=True,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_theme.py -v`
Expected: PASS (all 4 tests so far).

- [ ] **Step 10: Commit**

```bash
git add content-creator/theme.py content-creator/tests/test_theme.py
git commit -m "feat: add theme.py with branded header CSS and render_header"
```

- [ ] **Step 11: Write the failing integration test against `app.py`**

Append to `content-creator/tests/test_theme.py`:

```python
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


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
```

- [ ] **Step 12: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL — `at.title` is non-empty (app.py still calls `st.title`) and no `app-header-title` markdown exists yet.

- [ ] **Step 13: Wire `theme` into `app.py`**

In `content-creator/app.py`, change the import block (currently lines 1-8):

```python
import streamlit as st

import ai
import config
import db
import image_gen
import pipeline
import storage
import theme
```

Then replace line 65 (`st.title(f"Content Creator — {cfg.brand_pack}")`) with:

```python
theme.render_header(f"Content Creator — {cfg.brand_pack}")
```

And immediately after the existing `st.set_page_config(page_title="Content Creator", layout="wide")` call (line 10), add:

```python
theme.inject_theme()
```

- [ ] **Step 14: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: PASS (all tests, including the new integration test).

- [ ] **Step 15: Run the full existing test suite to check for regressions**

Run: `pytest -v`
Expected: PASS — `test_app_smoke.py`'s existing tests must still pass unchanged (they only assert `not at.exception`, which remains true).

- [ ] **Step 16: Commit**

```bash
git add content-creator/app.py content-creator/tests/test_theme.py
git commit -m "feat: wire AURA theme and branded header into app.py"
```

---

### Task 2: Status pill component for idea statuses

**Files:**
- Modify: `content-creator/theme.py` (add `STATUS_PILL_COLORS`, `render_status_pill`)
- Modify: `content-creator/app.py:254` (Biblioteca tab expander label)
- Test: `content-creator/tests/test_theme.py`

**Interfaces:**
- Consumes: `.streamlit/config.toml`'s `orangeColor`/`blueColor`/`greenColor`/`redColor`/`violetColor`/`grayColor` values (Task 1) — no function-call dependency, but the pill only renders AURA's exact hex (rather than Streamlit's stock orange/blue/etc.) once Task 1's config is merged.
- Produces: `theme.render_status_pill(status: str) -> str`, `theme.STATUS_PILL_COLORS: dict[str, str]`.

- [ ] **Step 1: Write the failing tests for `render_status_pill`**

Append to `content-creator/tests/test_theme.py`:

```python
import pytest


@pytest.mark.parametrize("status,expected_color", [
    ("idea", "orange"),
    ("reviewed", "blue"),
    ("approved", "green"),
    ("rejected", "red"),
    ("images_ready", "violet"),
    ("archived", "gray"),
])
def test_render_status_pill_maps_each_known_status(status, expected_color):
    assert theme.render_status_pill(status) == f":{expected_color}-background[{status}]"


def test_render_status_pill_raises_for_unknown_status():
    with pytest.raises(KeyError):
        theme.render_status_pill("not_a_real_status")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with `AttributeError: module 'theme' has no attribute 'render_status_pill'`.

- [ ] **Step 3: Add `render_status_pill` to `theme.py`**

Append to `content-creator/theme.py`:

```python
STATUS_PILL_COLORS = {
    "idea": "orange",
    "reviewed": "blue",
    "approved": "green",
    "rejected": "red",
    "images_ready": "violet",
    "archived": "gray",
}


def render_status_pill(status):
    color = STATUS_PILL_COLORS[status]
    return f":{color}-background[{status}]"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_theme.py -v`
Expected: PASS (all 6 parametrized cases + the `KeyError` case).

- [ ] **Step 5: Commit**

```bash
git add content-creator/theme.py content-creator/tests/test_theme.py
git commit -m "feat: add render_status_pill for idea status colors"
```

- [ ] **Step 6: Write the failing integration test for the Biblioteca tab**

Append to `content-creator/tests/test_theme.py`:

```python
import db


def test_biblioteca_expander_shows_status_pill(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any(":green-background[approved]" in label for label in labels)
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL — no expander label contains `:green-background[approved]` yet (current label format is `(approved)`).

- [ ] **Step 8: Update the Biblioteca tab's expander label**

In `content-creator/app.py`, change line 254 from:

```python
        with st.expander(f"#{idea['id']} — {idea['topic']} ({idea['status']})"):
```

to:

```python
        with st.expander(f"#{idea['id']} — {idea['topic']} {theme.render_status_pill(idea['status'])}"):
```

- [ ] **Step 9: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: PASS.

- [ ] **Step 10: Run the full existing test suite to check for regressions**

Run: `pytest -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add content-creator/app.py content-creator/tests/test_theme.py
git commit -m "feat: show AURA-colored status pill in Biblioteca idea list"
```

---

### Task 3: Button hierarchy — primary vs secondary actions

**Files:**
- Modify: `content-creator/app.py` (add `type="primary"` to 7 button call sites: lines 75, 80, 104, 123, 157, 190, 205)
- Test: `content-creator/tests/test_theme.py`

**Interfaces:**
- Consumes: `.streamlit/config.toml`'s `primaryColor` value (Task 1) — no function-call dependency, but `type="primary"` buttons only render AURA's rosa once Task 1's config is merged.
- Produces: nothing (no other task depends on this one).

**Context — the 7 buttons that become `type="primary"`, and why:** these are the app's main forward-driving actions per the spec's button-hierarchy guidance (primary actions get AURA's `.btn-primary` rosa look; everything else keeps Streamlit's default secondary/muted look, matching AURA's `.btn-muted`):
- `st.button("Criar ideia")` — creates an idea from a direct topic
- `st.button("Extrair tópicos")` — extracts topic candidates from reference text
- `st.button("Criar ideias seleccionadas")` — creates ideas from selected topics
- `st.button("Gerar rascunho")` — generates a draft
- `col1.button("Aprovar")` (draft approval)
- `col1.button("Aprovar", key=f"approve_{i}")` (slide image approval)
- `st.button("Gerar imagem", key=f"generate_{i}")` — generates a slide image

Buttons that stay `type="secondary"` (default, no code change): Rejeitar, Gerar novamente, Arquivar, Eliminar definitivamente, ◀ Anterior, Seguinte ▶, and the numbered thumbnail buttons — matching AURA's muted-button treatment for secondary/destructive/navigation actions.

- [ ] **Step 1: Write the failing test for the Nova Ideia tab's default-visible primary buttons**

Append to `content-creator/tests/test_theme.py`:

```python
def test_default_visible_primary_buttons_use_primary_type(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
    buttons_by_label = {b.label: b.proto.type for b in at.button}
    assert buttons_by_label["Criar ideia"] == "primary"


def test_extrair_topicos_button_uses_primary_type(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()
    at.radio[0].set_value("Texto de referência").run()

    buttons_by_label = {b.label: b.proto.type for b in at.button}
    assert buttons_by_label["Extrair tópicos"] == "primary"


def test_gerar_rascunho_button_uses_primary_type(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.run()

    buttons_by_label = {b.label: b.proto.type for b in at.button}
    assert buttons_by_label["Gerar rascunho"] == "primary"


def test_aprovar_draft_button_uses_primary_type(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    idea = db.get_idea(conn, idea_id)
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.session_state["current_result"] = {
        "draft": {"caption": "legenda", "slides": ["s1", "s2"]},
        "flags": [],
        "rounds": 1,
        "idea": idea,
    }
    at.run()

    buttons_by_label = {b.label: b.proto.type for b in at.button}
    assert buttons_by_label["Aprovar"] == "primary"


def test_image_tab_aprovar_and_gerar_imagem_buttons_use_primary_type(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    db.create_draft(conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2"])
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.run()

    buttons = [b for b in at.button if b.label == "Gerar imagem"]
    assert buttons, "expected at least one 'Gerar imagem' button for the first ungenerated slide"
    assert all(b.proto.type == "primary" for b in buttons)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL — all five new tests fail because every button currently defaults to `type="secondary"`.

- [ ] **Step 3: Add `type="primary"` to the 7 button call sites**

In `content-creator/app.py`, make these exact changes:

Line 75, from:
```python
        if st.button("Criar ideia") and topic_input:
```
to:
```python
        if st.button("Criar ideia", type="primary") and topic_input:
```

Line 80, from:
```python
        if st.button("Extrair tópicos") and reference_text:
```
to:
```python
        if st.button("Extrair tópicos", type="primary") and reference_text:
```

Line 104, from:
```python
            if st.button("Criar ideias seleccionadas") and selected:
```
to:
```python
            if st.button("Criar ideias seleccionadas", type="primary") and selected:
```

Line 123, from:
```python
        if st.button("Gerar rascunho"):
```
to:
```python
        if st.button("Gerar rascunho", type="primary"):
```

Line 157, from:
```python
        if col1.button("Aprovar"):
```
to:
```python
        if col1.button("Aprovar", type="primary"):
```

Line 190, from:
```python
                if existing["status"] != "approved" and col1.button("Aprovar", key=f"approve_{i}"):
```
to:
```python
                if existing["status"] != "approved" and col1.button("Aprovar", key=f"approve_{i}", type="primary"):
```

Line 205, from:
```python
                if st.button("Gerar imagem", key=f"generate_{i}"):
```
to:
```python
                if st.button("Gerar imagem", key=f"generate_{i}", type="primary"):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_theme.py -v`
Expected: PASS (all 5 new tests).

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `pytest -v`
Expected: PASS — button behavior (what happens on click) is unchanged, only the `type` kwarg was added, so no existing test should break.

- [ ] **Step 6: Commit**

```bash
git add content-creator/app.py content-creator/tests/test_theme.py
git commit -m "feat: mark primary-action buttons with type=primary for AURA styling"
```

---

## Manual visual verification (after all 3 tasks)

Not a task with its own review gate — a final check before considering this plan done, since no automated test can assert on-screen color/font rendering:

1. Run `streamlit run app.py` from `content-creator/`.
2. Open the app in a browser side-by-side with `docs/reference/AURA_v4.html`.
3. Confirm: cream background, brown/gold header bar, Cormorant Garamond headings, DM Sans body text, rosa primary buttons, rosa active-tab underline, colored status pills in Biblioteca, no hamburger/deploy toolbar.
4. Trigger each of `st.success`/`st.warning`/`st.error`/`st.info` at least once (e.g. submit an empty required field, hit a real error path) and confirm they render in AURA's sage/gold/rosa/blue rather than Streamlit's stock colors.
5. Trigger `run_with_progress` (e.g. click "Gerar rascunho") and confirm the step checklist's container renders with the themed border radius/color rather than Streamlit's default square-cornered gray box.
