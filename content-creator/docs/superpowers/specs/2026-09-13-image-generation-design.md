# Content Creator v1.1 — Image Generation Design Spec

## Background

v1 (merged to `main`, PR #11) produces the text side of a carousel — caption
and per-slide copy — through a generate → critique → revise loop, ending
with a human-approved draft. It produces no images: a "finished" idea today
is text only, and the actual carousel graphics are still made by hand
outside the tool.

Two real reference sources ground this spec:

- **The official brand visual guide**
  (`C:\Users\Elisson\Documents\Aura\Images\guiaImagens.png`) — exact hex
  colors, botanical line-art, and an oval "ELIXIR / MARIANA BOTELHO" label
  motif.
- **A real, previously-posted carousel**
  (`C:\Users\Elisson\Documents\Aura\Instagram\Carrossel Elixir\1.jpg`,
  `2.jpg`, `3.jpg`) — slide 1 is a near-full-bleed product photo (the
  "hero"), slides 2+ are parchment-background text cards framed in the
  brand's dark green/gold, each paired with a small image related to that
  slide's specific point.

A third reference — `docs/reference/AURA_v4.html`, a hand-built prototype of
a much larger social-media-management tool (calendar, ads, analytics,
stories) — informed the long-term product vision but is explicitly **out of
scope** for this spec; see `docs/backlog.md`.

An open-source multi-agent framework, OpenSquad
(`C:\Users\Elisson\Documents\Aura\opensquad`), was reviewed for its own
carousel-image approach before finalizing this design. Its
`instagram-carousel` skill renders slides via HTML+CSS through Playwright,
compositing text on top of the image rather than asking an AI model to
render text directly — the same approach this spec takes — but it has a
hard-coded requirement for a human to approve an HTML preview inside a live
Claude Code chat session before it will export anything, which is why it
was never usable as a standalone, unattended tool. Several of its concrete
rendering choices (fixed output size, minimum font sizes, a Playwright
scale-factor trick) are reused directly here; see "Rendering" below.

## Purpose of this project

Produce a complete, ready-to-post set of carousel images automatically from
an approved v1 draft — no further editing in Canva or any other tool
required. This is the first pass toward a longer-term goal (see
`docs/backlog.md`) of fully AI-generated, high-quality, on-brand imagery;
v1.1 deliberately ships the simplest version of that pipeline first.

## Scope — v1.1

**In scope:**
- Generating one image per slide, automatically, from the approved draft's
  text — no photo upload, no manually curated image gallery.
- Each slide's image is an AI-generated background (via the Gemini API)
  with the brand's text/colors/framing composited on top afterward via an
  HTML+CSS template rendered through Playwright.
- Slide 1 (hero) uses a visually distinct, near-full-bleed layout; slides
  2+ use a consistent card layout (image + text block).
- A prompt-review step: the auto-built image prompt for each slide is shown
  to the user, editable, before the API call is made.
- Per-slide regeneration if a generated image isn't right.
- A live, in-app carousel preview (single full-size slide + Prev/Next +
  thumbnail strip) once images are generated.
- Rendered PNGs saved to a per-carousel, human-named folder in the same
  Dropbox-synced tree as the database.
- Image generation costs tracked through the same daily-spend-cap mechanism
  already built for text generation in v1.

**Out of scope for v1.1** (see `docs/backlog.md` for the deferred items):
- Two-stage AI generation where the AI model bakes the text directly into
  the image (full automation) — deferred until multilingual AI text
  rendering is reliable enough to trust unattended.
- Any of the broader AURA-style feature set: content calendar, Stories/Reels
  planning, ad-budget tracking, analytics dashboards, per-profile config UI.
- Auto-publishing to Instagram.
- A second, different visual template/brand pack (the architecture supports
  it via the same brand-pack pattern as v1; building a second one is a
  separate exercise).

## User flow

1. User approves a draft (existing v1 flow — idea status becomes
   `approved`).
2. User opens a new "Gerar imagens" step for that idea. For each slide, the
   app shows an editable, pre-filled prompt (built automatically from the
   slide's text and the brand's visual style) and a "Gerar imagem" button.
3. On confirm, the app calls Gemini for the background image, composites it
   with the brand template (hero layout for slide 1, card layout for the
   rest), and shows the resulting PNG for that slide.
4. User reviews each slide's image individually: **Aprovar** or **Gerar
   novamente** (which re-shows the editable prompt and re-generates just
   that slide — the rest of the carousel is untouched).
5. Once every slide's image is approved, the idea's status becomes
   `images_ready`, and a "Pré-visualização do Carrossel" view becomes
   available: one slide shown at full size at a time, with Prev/Next
   buttons, a thumbnail strip to jump directly to any slide, and the
   caption text displayed alongside — reading like the actual Instagram
   post.

## Architecture

Two new brand-agnostic modules, following the same pattern as
`ai.py`/`pipeline.py` from v1:

```
content-creator/
  image_gen.py    Gemini API wrapper: build_image_prompt(), generate_image()
  render.py       HTML/CSS + Playwright compositor: two templates
                  (hero, card), both driven by the brand pack's
                  visual-style.md, not hard-coded to one brand
  brands/
    marianabotelho-ig/
      visual-style.md   NEW: hex palette, mood/aesthetic keywords,
                         botanical motif description, font pairing —
                         extracted from guiaImagens.png
  pipeline.py     extended with run_image_generation(), following the
                  same on_step callback / ai_module-injection pattern
                  already built for run_generation_pipeline()
  app.py          new "Gerar imagens" step + carousel preview view
```

`image_gen.py` responsibilities:
- `build_image_prompt(slide_text, brand_pack, slide_role)` — constructs a
  text-to-image prompt from the slide's own text plus `visual-style.md`'s
  mood/color/aesthetic keywords. `slide_role` (`"hero"` vs `"card"`) shifts
  the framing instructions (e.g. hero prompts ask for a fuller scene; card
  prompts ask for a tighter, single-subject image that leaves room for a
  text block).
- `generate_image(prompt) -> (image_bytes, cost_usd)` — calls the Gemini
  API (`gemini-3.1-flash-image`, confirmed working via a live throwaway
  test: ~$0.06–0.07 per 1024×1024 image) and returns the raw image bytes
  plus real cost computed from the response's token usage, mirroring how
  `ai.py` computes `calculate_cost()` for text calls.
- Explicitly instructs the model **not** to render any text into the image
  — text is always composited afterward, matching both this project's
  reliability requirement (correct PT-PT accents every time) and
  OpenSquad's own stated reason for the same rule.

`render.py` responsibilities:
- Builds each slide's HTML at a small base width (420px), using the
  brand's real hex palette (from `visual-style.md`) and a Google Fonts
  pairing, with the AI-generated image embedded as a base64 background and
  the slide's text laid out on top per the hero/card template.
- Enforces minimum font sizes (58px hero title / 43px heading / 34px body
  / 24px caption) and a basic WCAG AA contrast check between text color and
  its background swatch before rendering — reused directly from
  OpenSquad's `template-designer`/`image-creator` rules.
- Renders the final PNG via Playwright with `device_scale_factor≈2.57`,
  producing a crisp 1080×1350px image (standard Instagram portrait carousel
  size) from the 420px HTML layout — the same technique OpenSquad's
  `instagram-carousel` skill uses for its own export step.

## Data model

```sql
CREATE TABLE slide_images (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    slide_index INTEGER NOT NULL,     -- 0 = hero, 1..N = cards
    prompt TEXT NOT NULL,             -- the (possibly user-edited) prompt actually used
    file_path TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    created_at TEXT NOT NULL
);
```

A slide can have multiple rows over time (one per regeneration attempt);
only the latest `approved` row per `(idea_id, slide_index)` is used for the
final carousel preview and export. This mirrors how v1's `drafts` table
keeps every round rather than overwriting.

`ideas` gains one new column: `image_folder TEXT` — the per-carousel folder
name (see "Storage" below), set once on the first "Gerar imagens" click and
reused for every subsequent regeneration so files never move.

Image generation costs are logged through the existing `db.log_api_call()`
/ `api_calls` table (`function='generate_image'`), so they count against
the same `MAX_DAILY_SPEND_USD` cap already enforced for text generation —
no new cost-tracking mechanism needed.

## Storage

Images are saved in the same Dropbox-synced tree as the database, in a
per-carousel folder named `<YYYY-MM-DD>_<topic-slug>` (date the images were
first generated + a slugified version of the idea's topic), e.g.:

```
C:\Users\Elisson\Dropbox\learning\aura\images\2026-09-13_ritual-matinal-com-oleo-de-lavanda\
    slide-01.png
    slide-02.png
    ...
```

The images root (`.../aura/images/`) is derived from `DB_PATH`'s parent
directory in `config.py` — no new environment variable required. If the
computed folder name already exists (e.g. two ideas share a topic and a
generation date), a numeric suffix is appended (`..._2`, `..._3`, ...) at
creation time. The resolved name is stored in `ideas.image_folder` so it
never needs to be recomputed or renamed later.

## Error handling

Both the per-slide image generation call and the Playwright render step
report progress through the exact `on_step(step_name, status, detail)`
callback already built and shipped in v1.1's progress-UX work — same
`st.status` checklist, same "Detalhes do erro (para diagnóstico)" expander
on failure. No new UI pattern is introduced. A failed render leaves that
slide's status as `pending` (or the previous `approved` row untouched, if
this was a regeneration attempt), so a failure never destroys a
previously-good image.

## Testing

Following the same dependency-injection pattern as `ai.py` / `pipeline.py`:

- `image_gen` and `render` are both passed into `pipeline.run_image_generation()`
  as injectable modules (`image_gen_module=image_gen, render_module=render`),
  so pipeline tests use fakes — no real API calls, no real Playwright
  invocations, fast and free.
- `render.py`'s HTML-building logic (`build_slide_html()`) is tested
  directly as pure string output — palette substitution, font-size
  enforcement, contrast-check logic — separately from the actual Playwright
  screenshot call.
- Folder-naming logic (slug generation, collision suffixing) is tested with
  plain unit tests against a fake/temp directory listing.
- The real, paid, end-to-end path (actual Gemini call + actual Playwright
  render of a real slide) is exercised once manually before the feature is
  considered done — matching the project's established rule that no amount
  of mocked-test coverage substitutes for one real, human-observed run
  before trusting an AI-calling feature (see `docs/decisions.md`,
  2026-09-13 entry on the three real bugs mocks couldn't catch).
