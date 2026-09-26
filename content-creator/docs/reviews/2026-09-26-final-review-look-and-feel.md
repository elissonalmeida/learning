# Final review: look-and-feel Task 1 (ticket #13), as merged into main

Reviewed on a detached checkout of `main` (54ed84e) at `C:\Users\Elisson\Documents\learning-worktrees\review-main`.
Commits in scope: f5fa324 (config.toml), 47557ff (theme.py), 98632af (app.py wiring).
Files: `content-creator/theme.py`, `content-creator/.streamlit/config.toml`, `content-creator/app.py` (lines 9, 12, 67), `content-creator/tests/test_theme.py`.
Streamlit installed in the venv: **1.63.0**. Test suite: **171 passed** (`python -m pytest -q` from `content-creator/`).

## How this was checked

- Read the spec, plan Task 1, and the three commits.
- `python -m streamlit config show`: every key in `config.toml` is recognised by 1.63 and shows "set in ...content-creator/.streamlit/config.toml". `font`/`headingFont` use the documented `"<name>:<url>"` form.
- Ran the real app headless (temp DB with an approved idea and a slide image, fake API keys) and drove it with Playwright:
  - opened the Gerar Imagens tab, clicked Fullscreen, measured the close control, pressed Esc, clicked "Close fullscreen";
  - did the same on a stock Streamlit page (no config.toml) for comparison.
- Rendered a probe page containing every widget type the app uses (st.error/warning/success/info, st.code, caption, link, st.status error/complete, expander, radio, selectbox, checkbox, secondary/primary/disabled button, text_input). I rendered it once with this config.toml and once with stock settings, then computed WCAG contrast ratios from the computed styles.
- Read the installed frontend bundle (`streamlit/static/static/js/Toolbar.*.js`, `withFullScreenWrapper.*.js`, `ImageList.*.js`) to see how fullscreen enter/exit works.
- All temp servers were stopped afterwards. Nothing in the repo was modified.

## Strengths

- `config.toml` matches the plan exactly. Every palette hex matches the spec tokens (bg, card, border, text, rosa, gold, sage, blue, purple, muted). Fonts load through Streamlit's own `font`/`headingFont` keys rather than a hand-written `@import`, as the plan asked.
- Using documented theme keys instead of CSS aimed at Streamlit's internal classes is the right call. The injected CSS is limited to the two app-owned classes `.app-header` and `.app-header-title`. It cannot hit Streamlit internals, so it cannot break on a Streamlit upgrade.
- The app.py wiring is minimal and correct. `inject_theme()` runs right after `set_page_config`, and `st.title` is replaced by `render_header` (app.py:67). `layout="wide"` is unchanged.
- `run.bat` does `cd /d "%~dp0"`, and Streamlit 1.63 also reads `.streamlit/` next to the script, so the theme is picked up however the app is launched.
- The AppTest integration test (`test_app_renders_custom_header_instead_of_default_title`) is a real behavioural test. It fails if `st.title` comes back or the header stops rendering.
- The header reads well: gold #C4922A on brown #3E2208 is 5.2:1.
- The primary button (used by Task 3 / #15) is white on rosa at 4.45:1, better than stock Streamlit's 3.3:1. `violetColor`/`grayColor` are already set for the status pills in Task 2 / #14. Task 1 leaves nothing that #14 or #15 depend on in a bad state.

## Regression check: GitHub issue #47 (fullscreen image, "no way back")

**Verdict: the theme does not cause #47 and does not make it worse.**

- `[client] toolbarMode = "minimal"` only controls the app-level main menu (the Deploy/Rerun/Settings area). Per-element fullscreen is handled by the element toolbar (`Toolbar.*.js`), which never reads `toolbarMode`.
- When an element is in fullscreen, that toolbar is forced visible (`locked: a || isFullScreen`) and swaps its button for "Close fullscreen". The fullscreen wrapper also listens for Esc (`keyCode === 27`).
- The injected CSS only targets `.app-header` and `.app-header-title`. It hides nothing and adds no transforms or z-index.
- Measured in the real app with this theme: the "Close fullscreen" button is visible and is the topmost element at its own centre, so nothing covers it. Clicking it exits fullscreen, and so does Esc, with page state intact. Stock Streamlit behaves identically: same position (x=1361, y=15), same 22×22 px size, same 60%-opacity icon (contrast about 3.9:1 in both).
- The likely real cause is Streamlit's stock UX. The only exit is a small, faint icon in the far top-right corner of the window, and because app.py pins `st.image(..., width=300/400)` the image is **not enlarged** in fullscreen (it stayed 300×375 px). So "fullscreen" looks like a mostly empty cream page, and a user can easily miss the icon.
- The theme's cream background replaces white, but that does not change how discoverable the exit is.
- The fix belongs to #47, not here. The issue's own suggestion (an `st.dialog` preview with a visible "Fechar" button) addresses it. Another option is `st.image(..., use_container_width/width="stretch")` inside a narrow column so fullscreen actually enlarges.

## Contrast and readability of existing widgets (themed vs stock, WCAG ratio)

| Element | Themed | Stock | Note |
|---|---|---|---|
| body text / radio / checkbox / expander label / secondary button | 14.5–15.4 | 11.9–12.5 | better |
| st.error | 5.8 | 4.6 | better |
| st.info | 9.0 | 6.7 | better |
| st.success | **4.2** | 4.5 | slightly below AA 4.5 |
| st.warning | **4.2** | 4.7 | still stock *yellow* text, now on cream (see Important #1) |
| link | 10.4 | 7.5 | better |
| st.code | 15.4 | 11.9 | better |
| inline code (sage) | 4.85 | 4.66 | ok |
| primary button (white on rosa) | 4.45 | 3.3 | better |
| active tab label (rosa on cream) | 3.9 | — | below AA for 14px text |
| disabled button | 2.4 | 2.2 | as intended (disabled) |
| st.status (error/complete) | themed border/radius, icon readable | — | ok |

Selectbox, radio and checkbox render with a themed border and cream fill and read clearly.

## HTML injection (render_header)

`theme.py:28` interpolates `title` (built from `cfg.brand_pack`, which comes from `.env` `BRAND_PACK`) into markup rendered with `unsafe_allow_html=True`, without escaping.

The practical risk is low:
- `.env` is operator-controlled.
- `ai.load_tone_names(cfg.brand_pack)` (app.py:21) opens files under `brands/<brand_pack>/` first, so a value containing markup would almost certainly crash before the header renders.

Still, it's a one-line fix (`html.escape(title)`). The helper takes an arbitrary `title: str`, so it should not trust its input.

## Issues

### Critical
None.

### Important

1. **`content-creator/.streamlit/config.toml:14-19` (no `yellowColor`): `st.warning` is not remapped to AURA gold.**
   - The spec requires `stWarning → gold`. Plan Task 1 claims `orangeColor` covers `st.warning`, but in Streamlit 1.63 `st.warning` uses the *yellow* palette. Measured: warning text is rgb(146,108,5), byte-identical to stock, on a yellow tint.
   - Why it matters: the one existing call site (app.py:157, "Pontos ainda não resolvidos…") stays off-palette, and the plan's own manual check step 4 would fail.
   - Fix: add `yellowColor = "#C4922A"` (and check the derived text contrast). Also correct the plan's "What this task covers" note.

### Minor

2. **`content-creator/theme.py:28`: `title` interpolated unescaped into `unsafe_allow_html` markup.** `brand_pack` comes from `.env`. Low practical risk (see above). Fix: `html.escape(title)`.

3. **`content-creator/.streamlit/config.toml:16,4` (greenColor/primaryColor on cream): three text colours fall below WCAG AA 4.5:1.**
   - `st.success` text is 4.2:1 (stock 4.5). It is used for "Aprovado", "Ideia criada…" and similar messages.
   - `st.warning` is 4.2:1.
   - The active tab label (rosa on cream) is 3.9:1.
   - All are still readable, but lower than before for the success box. Optional fix: set `greenTextColor` (for example `#4F6B46`) and a darker `yellowTextColor` explicitly.

4. **`content-creator/requirements.txt:1`: floor `streamlit>=1.38` while config.toml relies on much newer theme keys.**
   - Keys such as `baseRadius`, `buttonRadius`, `borderColor`, `showWidgetBorder`, the `"name:url"` font form and the `redColor…grayColor` palette did not exist in 1.38.
   - `run.bat` runs `pip install -r requirements.txt`, which won't upgrade an older Streamlit already in a venv (for example on the second computer). There Streamlit would warn and silently ignore most of the theme.
   - Fix: raise the floor to the version actually verified (`streamlit>=1.63`, or at least the release that introduced the palette keys).

5. **`content-creator/tests/test_theme.py:7-29`: config tests only compare TOML literals to themselves.**
   - They would not catch a key Streamlit rejects or ignores (for example a renamed or misspelled option in a future version), a malformed font spec, or a wrong palette mapping (they passed while `st.warning` is still stock yellow).
   - `test_inject_theme_...` only checks that the substring `"app-header"` is present.
   - Suggested fix: add a test that loads the config through `streamlit.config` (for example `config.get_config_options(force_reparse=True)` with cwd at `content-creator/`, then `config.get_option("theme.primaryColor") == "#B85C5C"`). That proves Streamlit itself parses and accepts the file.

6. **`content-creator/tests/test_theme.py:32,34,55,57`: imports in the middle of the module and a duplicate `from pathlib import Path`.** This was copied verbatim from the plan's "append" steps. Style only: move the imports to the top.

## Declined to judge

- Coach code in `.review-merged.diff`: out of scope per instructions.
- Status pills (Task 2 / #14) and `type="primary"` buttons (Task 3 / #15): not implemented yet, and by instruction their absence is not a defect.
- Pixel parity with `AURA_v4.html`: out of scope per the spec. I did not open the reference side by side.
- The ~16 px extra top gap from the style-only `st.markdown` element that `inject_theme()` emits: cosmetic, and inherent to the CSS-injection approach the spec chose.
- The #47 fix itself (dialog preview or stretch width): it belongs to issue #47, not to this branch.

## Recommendations

- Fix Important #1 before closing #13, then run the plan's manual step 4 in a browser.
- Handle #47 separately. It is a stock Streamlit discoverability problem made worse by the pinned image widths, not a theme regression.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** Task 1 is implemented as planned. All config keys are valid for the installed Streamlit 1.63, contrast is equal or better almost everywhere, and the theme is verified not to cause the fullscreen bug. The one spec gap is `st.warning`, which still renders stock yellow rather than gold. The remaining findings are small hardening and test-strength items.
