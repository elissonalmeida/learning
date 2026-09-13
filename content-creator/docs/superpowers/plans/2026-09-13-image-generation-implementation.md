# Content Creator v1.1 — Image Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a complete, ready-to-post set of carousel images automatically from an approved v1 draft, with no manual editing in any other tool.

**Architecture:** Two new brand-agnostic modules (`image_gen.py` for the Gemini API call, `render.py` for HTML+Playwright compositing) plug into the existing `pipeline.py`/`app.py` structure using the same dependency-injection and `on_step` progress-callback patterns already shipped in v1 and the v1.1 progress-UX work. A new `storage.py` module handles per-carousel folder naming. Images are AI-generated backgrounds; all text is drawn on top afterward via HTML/CSS, never rendered by the AI model itself.

**Tech Stack:** Python 3.14, `google-genai` SDK (Gemini API), Playwright (sync API), SQLite (stdlib `sqlite3`), Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-image-generation-design.md`

## Global Constraints

- All user-facing strings and generated content are European Portuguese (PT-PT), matching the rest of the app.
- Image generation costs count against the existing `MAX_DAILY_SPEND_USD` daily cap (same `db.would_exceed_daily_cap` mechanism used for text).
- No AI model is ever asked to render text into an image — text is always composited afterward via `render.py`.
- Every new AI-calling or file-writing function accepts an injectable module parameter (`image_gen_module=image_gen`, `render_module=render`, `storage_module=storage`) so tests never make real API calls, real Playwright calls, or touch the real filesystem beyond `tmp_path`.
- Progress and errors report through the existing `on_step(step_name, status, detail=None)` callback shape — no new UI/error pattern is introduced.
- Final output images are 1080×1350px PNG (standard Instagram portrait carousel size).
- Minimum text sizes (in final 1080px output): 58px hero title / 43px heading / 34px body / 24px caption. WCAG AA contrast (4.5:1 normal text, 3.0:1 large/hero text) is checked before rendering.

---

## File Structure

```
content-creator/
  image_gen.py                       NEW — Gemini API wrapper
  render.py                          NEW — HTML/CSS + Playwright compositor
  storage.py                         NEW — per-carousel folder naming
  db.py                              MODIFY — slide_images table, ideas.image_folder column, CRUD
  config.py                          MODIFY — GEMINI_API_KEY
  pipeline.py                        MODIFY — generate_slide_image(), approve/reject, ensure_image_folder()
  app.py                             MODIFY — "Gerar Imagens" tab + carousel preview
  requirements.txt                   MODIFY — google-genai, playwright
  brands/marianabotelho-ig/
    visual-style.md                  NEW — palette, fonts, mood keywords for this brand pack
  tests/
    test_brand_pack.py               MODIFY — visual-style.md added to required files
    test_config.py                   MODIFY — GEMINI_API_KEY coverage
    test_db_slide_images.py          NEW
    test_storage.py                  NEW
    test_image_gen.py                NEW
    test_render.py                   NEW
    test_pipeline_images.py          NEW
```

---

### Task 1: Brand pack — `visual-style.md`

**Files:**
- Create: `content-creator/brands/marianabotelho-ig/visual-style.md`
- Modify: `content-creator/tests/test_brand_pack.py`

**Interfaces:**
- Produces: a markdown file with a **parseable** color-palette section (used by `render.py` in Task 6) in the exact format `- **Label:** \`#RRGGBB\`` — one line per color, and free-text sections (mood keywords, typography, the "never ask for text in image" rule) used by `image_gen.py` in Task 5.

- [ ] **Step 1: Create the brand pack file**

```markdown
# Estilo Visual — @marianabotelho.pt

Fonte: guia de imagens oficial da marca (`guiaImagens.png`) e o carrossel
"Elixir" já publicado. Usado por `image_gen.py` (para construir os prompts
de imagem) e por `render.py` (para os templates HTML/CSS).

## Paleta de cores (hex)

- **Fundo (pergaminho):** `#efe4d0`
- **Moldura/estrutura:** `#83ae37`
- **Acento vermelho:** `#CA2D2D`
- **Acento dourado:** `#e6b55c`
- **Rosa claro:** `#ebb5a2`
- **Bege claro:** `#e7d1a8`

## Tipografia

- Títulos/destaque: **Cormorant Garamond** (serifada, elegante)
- Corpo de texto: **DM Sans** (sem serifa, legível em ecrã pequeno)

## Motivo botânico e moldura

Ilustrações botânicas em linha fina (plantas, ervas) e uma moldura oval
dourada/verde-escura com o texto "ELIXIR / MARIANA BOTELHO" — usada como
referência de composição, não para ser reproduzida literalmente em cada
imagem.

## Palavras-chave de ambiente/mood (para prompts de imagem)

natureza, botânico, artesanal, quente, acolhedor, luz natural suave, tons
terrosos, minimalista, orgânico, calmo — nunca clínico, nunca futurista,
nunca néon.

## Regra obrigatória para geração de imagem

**Nunca pedir texto na imagem.** O modelo de IA gera apenas o fundo/cena; o
texto (título, legenda) é sempre sobreposto depois via HTML/CSS em
`render.py`. Um prompt de imagem nunca deve incluir palavras que apareçam
escritas na imagem.
```

- [ ] **Step 2: Add it to the brand pack's required-files test**

In `tests/test_brand_pack.py`, add `"visual-style.md"` to the `REQUIRED_FILES` list:

```python
REQUIRED_FILES = [
    "tone-of-voice.md",
    "domain-framework.md",
    "quality-criteria.md",
    "anti-patterns.md",
    "output-examples.md",
    "research-brief.md",
    "visual-style.md",
]
```

- [ ] **Step 3: Run the test**

Run: `cd content-creator && python3 -m pytest tests/test_brand_pack.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add brands/marianabotelho-ig/visual-style.md tests/test_brand_pack.py
git commit -m "Add visual-style.md brand pack file for image generation"
```

---

### Task 2: Dependencies and `GEMINI_API_KEY` config

**Files:**
- Modify: `content-creator/requirements.txt`
- Modify: `content-creator/config.py`
- Modify: `content-creator/tests/test_config.py`

**Interfaces:**
- Produces: `Config.gemini_api_key` (str), consumed by `image_gen.get_client()` in Task 5 and by `app.py` in Task 8.

- [ ] **Step 1: Write the failing tests**

Update `tests/test_config.py` to require `GEMINI_API_KEY`:

```python
import pytest
from config import load_config, ConfigError, DEFAULT_DB_PATH, DEFAULT_MAX_DAILY_SPEND_USD, DEFAULT_BRAND_PACK

def test_raises_when_api_key_missing():
    with pytest.raises(ConfigError):
        load_config(env={})

def test_raises_when_gemini_api_key_missing():
    with pytest.raises(ConfigError):
        load_config(env={"ANTHROPIC_API_KEY": "sk-test"})

def test_applies_defaults_when_only_required_keys_set():
    cfg = load_config(env={"ANTHROPIC_API_KEY": "sk-test", "GEMINI_API_KEY": "gk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.gemini_api_key == "gk-test"
    assert cfg.db_path == DEFAULT_DB_PATH
    assert cfg.max_daily_spend_usd == DEFAULT_MAX_DAILY_SPEND_USD
    assert cfg.brand_pack == DEFAULT_BRAND_PACK

def test_overrides_are_respected():
    cfg = load_config(env={
        "ANTHROPIC_API_KEY": "sk-test",
        "GEMINI_API_KEY": "gk-test",
        "DB_PATH": "C:\\custom\\path.db",
        "MAX_DAILY_SPEND_USD": "5.5",
        "BRAND_PACK": "other-brand",
    })
    assert cfg.db_path == "C:\\custom\\path.db"
    assert cfg.max_daily_spend_usd == 5.5
    assert cfg.brand_pack == "other-brand"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_config.py -v`
Expected: FAIL (`ConfigError` not raised for missing `GEMINI_API_KEY`; `AttributeError` for `cfg.gemini_api_key`)

- [ ] **Step 3: Update `config.py`**

```python
class Config:
    def __init__(self, api_key, gemini_api_key, db_path, max_daily_spend_usd, brand_pack):
        self.api_key = api_key
        self.gemini_api_key = gemini_api_key
        self.db_path = db_path
        self.max_daily_spend_usd = max_daily_spend_usd
        self.brand_pack = brand_pack


def load_config(env=None):
    env = env if env is not None else os.environ
    api_key = env.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file before running the app."
        )
    gemini_api_key = env.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ConfigError(
            "GEMINI_API_KEY is not set. Add it to a .env file before running the app."
        )
    db_path = env.get("DB_PATH", DEFAULT_DB_PATH)
    max_daily_spend_usd = float(env.get("MAX_DAILY_SPEND_USD", DEFAULT_MAX_DAILY_SPEND_USD))
    brand_pack = env.get("BRAND_PACK", DEFAULT_BRAND_PACK)
    return Config(api_key, gemini_api_key, db_path, max_daily_spend_usd, brand_pack)
```

(Replace the existing `Config.__init__` and `load_config` definitions with these.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Add dependencies to `requirements.txt`**

```
streamlit>=1.38
anthropic>=0.34
python-dotenv>=1.0
pytest>=8.0
google-genai>=2.20
playwright>=1.47
```

- [ ] **Step 6: Install the new dependencies and the Playwright browser**

Run: `cd content-creator && python3 -m pip install -r requirements.txt`
Run: `python3 -m playwright install chromium`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt config.py tests/test_config.py
git commit -m "Add GEMINI_API_KEY config and image-generation dependencies"
```

---

### Task 3: Database — `slide_images` table and `ideas.image_folder`

**Files:**
- Modify: `content-creator/db.py`
- Create: `content-creator/tests/test_db_slide_images.py`

**Interfaces:**
- Produces:
  - `db.create_slide_image(conn, idea_id, slide_index, prompt, file_path, cost_usd) -> int`
  - `db.get_slide_image(conn, slide_image_id) -> dict | None`
  - `db.list_slide_images(conn, idea_id) -> list[dict]` (all rows, every regeneration attempt, ordered by `slide_index`, `created_at`)
  - `db.get_latest_slide_images(conn, idea_id) -> list[dict]` (one row per `slide_index` — the most recent attempt — ordered by `slide_index`)
  - `db.update_slide_image_status(conn, slide_image_id, status)` (`status` is `"pending"`, `"approved"`, or `"rejected"`)
  - `db.set_idea_image_folder(conn, idea_id, image_folder)`
  - `db.get_idea(...)` rows now include an `"image_folder"` key (`None` until set)
- Consumes: nothing new (extends existing `db.py` conventions — `_now()`, `dict(row)` for `sqlite3.Row`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_slide_images.py`:

```python
import pytest
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


@pytest.fixture
def idea(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    return db.get_idea(conn, idea_id)


def test_new_idea_has_no_image_folder(idea):
    assert idea["image_folder"] is None


def test_set_and_read_image_folder(conn, idea):
    db.set_idea_image_folder(conn, idea["id"], "2026-09-13_ritual-matinal")
    assert db.get_idea(conn, idea["id"])["image_folder"] == "2026-09-13_ritual-matinal"


def test_create_and_get_slide_image(conn, idea):
    slide_image_id = db.create_slide_image(
        conn, idea["id"], 0, "um prompt", "C:\\fake\\slide-00.png", 0.07,
    )
    row = db.get_slide_image(conn, slide_image_id)
    assert row["idea_id"] == idea["id"]
    assert row["slide_index"] == 0
    assert row["prompt"] == "um prompt"
    assert row["file_path"] == "C:\\fake\\slide-00.png"
    assert row["cost_usd"] == pytest.approx(0.07)
    assert row["status"] == "pending"


def test_update_slide_image_status(conn, idea):
    slide_image_id = db.create_slide_image(conn, idea["id"], 0, "p", "f.png", 0.07)
    db.update_slide_image_status(conn, slide_image_id, "approved")
    assert db.get_slide_image(conn, slide_image_id)["status"] == "approved"


def test_list_slide_images_returns_every_attempt(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p1", "f1.png", 0.07)
    db.create_slide_image(conn, idea["id"], 0, "p2", "f2.png", 0.07)
    rows = db.list_slide_images(conn, idea["id"])
    assert len(rows) == 2


def test_get_latest_slide_images_returns_one_row_per_slide(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p1", "f1.png", 0.07)
    db.create_slide_image(conn, idea["id"], 0, "p2", "f2.png", 0.07)
    db.create_slide_image(conn, idea["id"], 1, "p3", "f3.png", 0.07)
    latest = db.get_latest_slide_images(conn, idea["id"])
    assert [row["slide_index"] for row in latest] == [0, 1]
    assert latest[0]["prompt"] == "p2"  # the most recent attempt for slide 0


def test_hard_delete_idea_removes_slide_images(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p", "f.png", 0.07)
    db.archive_idea(conn, idea["id"])
    db.hard_delete_idea(conn, idea["id"])
    assert db.list_slide_images(conn, idea["id"]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_db_slide_images.py -v`
Expected: FAIL (`AttributeError: module 'db' has no attribute 'create_slide_image'`, and `idea["image_folder"]` raises `KeyError` / `IndexError`)

- [ ] **Step 3: Update `db.py`**

Add `slide_images` to the schema in `init_db`, and an idempotent column migration for pre-existing databases, right after the existing `executescript(...)` call (`db.py:14-47`):

```python
def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            brand_pack TEXT NOT NULL,
            source_type TEXT NOT NULL,
            reference_text TEXT,
            topic TEXT NOT NULL,
            pillar TEXT,
            tone TEXT,
            status TEXT NOT NULL DEFAULT 'idea',
            archived_at TEXT
        );
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY,
            idea_id INTEGER NOT NULL REFERENCES ideas(id),
            round INTEGER NOT NULL,
            caption TEXT NOT NULL,
            slides TEXT NOT NULL,
            quality_flags TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_calls (
            id INTEGER PRIMARY KEY,
            idea_id INTEGER REFERENCES ideas(id),
            function TEXT NOT NULL,
            tokens_in INTEGER NOT NULL,
            tokens_out INTEGER NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS slide_images (
            id INTEGER PRIMARY KEY,
            idea_id INTEGER NOT NULL REFERENCES ideas(id),
            slide_index INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            file_path TEXT NOT NULL,
            cost_usd REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        """
    )
    try:
        conn.execute("ALTER TABLE ideas ADD COLUMN image_folder TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists — idempotent migration for pre-v1.1 databases
    conn.commit()
```

Add near the end of `db.py`, after `would_exceed_daily_cap`:

```python
def create_slide_image(conn, idea_id, slide_index, prompt, file_path, cost_usd):
    cursor = conn.execute(
        "INSERT INTO slide_images (idea_id, slide_index, prompt, file_path, cost_usd, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (idea_id, slide_index, prompt, file_path, cost_usd, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_slide_image(conn, slide_image_id):
    row = conn.execute("SELECT * FROM slide_images WHERE id = ?", (slide_image_id,)).fetchone()
    return dict(row) if row else None


def update_slide_image_status(conn, slide_image_id, status):
    conn.execute("UPDATE slide_images SET status = ? WHERE id = ?", (status, slide_image_id))
    conn.commit()


def list_slide_images(conn, idea_id):
    rows = conn.execute(
        "SELECT * FROM slide_images WHERE idea_id = ? ORDER BY slide_index ASC, created_at ASC",
        (idea_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_slide_images(conn, idea_id):
    """Return the most recent slide_images row per slide_index. Regenerating a
    slide inserts a new row rather than overwriting the old one (same pattern
    as drafts keeping every round), so this collapses to the current state."""
    latest = {}
    for row in list_slide_images(conn, idea_id):
        latest[row["slide_index"]] = row
    return [latest[i] for i in sorted(latest)]


def set_idea_image_folder(conn, idea_id, image_folder):
    conn.execute("UPDATE ideas SET image_folder = ? WHERE id = ?", (image_folder, idea_id))
    conn.commit()
```

Add `import sqlite3` is already present at the top of `db.py` (line 1) — no new import needed.

Update `hard_delete_idea` (`db.py:93-102`) to also remove `slide_images` rows, so the `NOT NULL REFERENCES ideas(id)` foreign key (enforced via `PRAGMA foreign_keys = ON` in `get_connection`) doesn't reject the idea deletion:

```python
def hard_delete_idea(conn, idea_id):
    idea = get_idea(conn, idea_id)
    if idea is None or idea["archived_at"] is None:
        raise ValueError("Can only hard-delete an idea that has already been archived")
    # Drafts and slide_images belong to the idea and go with it; api_calls are
    # a spend audit trail that must survive the idea being cleaned up, so we
    # only null the link.
    conn.execute("DELETE FROM drafts WHERE idea_id = ?", (idea_id,))
    conn.execute("DELETE FROM slide_images WHERE idea_id = ?", (idea_id,))
    conn.execute("UPDATE api_calls SET idea_id = NULL WHERE idea_id = ?", (idea_id,))
    conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_db_slide_images.py tests/test_db_ideas.py tests/test_db_drafts_and_spend.py -v`
Expected: PASS (all, including the pre-existing db tests — confirms the migration and `hard_delete_idea` change didn't break anything)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db_slide_images.py
git commit -m "Add slide_images table and ideas.image_folder column"
```

---

### Task 4: `storage.py` — per-carousel folder naming

**Files:**
- Create: `content-creator/storage.py`
- Create: `content-creator/tests/test_storage.py`

**Interfaces:**
- Produces:
  - `storage.images_root(db_path) -> pathlib.Path` (the `images/` folder alongside the database file)
  - `storage.slugify(text) -> str`
  - `storage.make_carousel_folder(root, topic, date_str) -> str` (folder name only, does not create the directory; appends `_2`, `_3`, ... on collision)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storage.py`:

```python
import storage


def test_slugify_handles_accents_and_spaces():
    assert storage.slugify("Ritual Matinal com Óleo de Lavanda") == "ritual-matinal-com-oleo-de-lavanda"


def test_slugify_strips_punctuation():
    assert storage.slugify("3 sinais! (importante)") == "3-sinais-importante"


def test_make_carousel_folder_returns_date_and_slug(tmp_path):
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal"


def test_make_carousel_folder_appends_suffix_on_collision(tmp_path):
    (tmp_path / "2026-09-13_ritual-matinal").mkdir()
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal_2"


def test_make_carousel_folder_increments_past_multiple_collisions(tmp_path):
    (tmp_path / "2026-09-13_ritual-matinal").mkdir()
    (tmp_path / "2026-09-13_ritual-matinal_2").mkdir()
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal_3"


def test_images_root_is_sibling_of_db_file():
    root = storage.images_root(r"C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db")
    assert str(root) == r"C:\Users\Elisson\Dropbox\learning\aura\images"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_storage.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'storage'`)

- [ ] **Step 3: Write `storage.py`**

```python
import re
import unicodedata
from pathlib import Path


def images_root(db_path):
    """Images live in an 'images' folder alongside the database file, in the
    same Dropbox-synced tree, so they get backed up the same way the DB is."""
    return Path(db_path).parent / "images"


def slugify(text):
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def make_carousel_folder(root, topic, date_str):
    """Return a unique folder name '<date_str>_<topic-slug>' under root,
    appending a numeric suffix on collision. Does not create the directory."""
    base = f"{date_str}_{slugify(topic)}"
    candidate = base
    suffix = 2
    while (Path(root) / candidate).exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "Add storage.py for per-carousel image folder naming"
```

---

### Task 5: `image_gen.py` — Gemini API wrapper

**Files:**
- Create: `content-creator/image_gen.py`
- Create: `content-creator/tests/test_image_gen.py`

**Interfaces:**
- Consumes: `visual-style.md` via a `load_brand_doc(brand_pack, filename)` helper (same shape as `ai.load_brand_doc`, duplicated locally to keep `image_gen.py` independent of `ai.py`).
- Produces:
  - `image_gen.get_client(api_key) -> genai.Client`
  - `image_gen.build_image_prompt(slide_text, brand_pack, slide_role) -> str` (`slide_role` is `"hero"` or `"card"`)
  - `image_gen.generate_image(client, prompt) -> (image_bytes: bytes, tokens_in: int, tokens_out: int, cost_usd: float)`
  - `image_gen.calculate_cost(tokens_in, tokens_out) -> float`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_gen.py`:

```python
import base64
from unittest.mock import MagicMock
import pytest
import image_gen


def make_fake_client(image_bytes=b"\x89PNG-fake", tokens_in=50, tokens_out=1120):
    fake_interaction = MagicMock()
    fake_interaction.output_image.data = base64.b64encode(image_bytes).decode()
    fake_interaction.usage.total_input_tokens = tokens_in
    fake_interaction.usage.total_output_tokens = tokens_out
    client = MagicMock()
    client.interactions.create.return_value = fake_interaction
    return client


def test_build_image_prompt_includes_slide_text():
    prompt = image_gen.build_image_prompt("óleo de lavanda para o sono", "marianabotelho-ig", "hero")
    assert "óleo de lavanda para o sono" in prompt


def test_build_image_prompt_includes_brand_palette():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "#83ae37" in prompt


def test_build_image_prompt_never_asks_for_text_in_image():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "sem texto nenhum escrito na imagem" in prompt


def test_build_image_prompt_differs_by_slide_role():
    hero = image_gen.build_image_prompt("texto", "marianabotelho-ig", "hero")
    card = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert hero != card


def test_generate_image_returns_bytes_tokens_and_cost():
    client = make_fake_client(image_bytes=b"\x89PNG-fake", tokens_in=50, tokens_out=1120)
    image_bytes, tokens_in, tokens_out, cost = image_gen.generate_image(client, "um prompt qualquer")
    assert image_bytes == b"\x89PNG-fake"
    assert tokens_in == 50
    assert tokens_out == 1120
    assert cost == pytest.approx(image_gen.calculate_cost(50, 1120))


def test_generate_image_calls_the_configured_model(monkeypatch):
    client = make_fake_client()
    image_gen.generate_image(client, "um prompt")
    _, kwargs = client.interactions.create.call_args
    assert kwargs["model"] == image_gen.MODEL
    assert kwargs["input"] == "um prompt"


def test_calculate_cost_matches_gemini_pricing():
    # Gemini 3.1 Flash Image standard pricing: $0.50/1M input, $60.00/1M output.
    assert image_gen.calculate_cost(1_000_000, 0) == pytest.approx(0.50)
    assert image_gen.calculate_cost(0, 1_000_000) == pytest.approx(60.00)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_image_gen.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'image_gen'`)

- [ ] **Step 3: Write `image_gen.py`**

```python
import base64
from pathlib import Path

from google import genai

MODEL = "gemini-3.1-flash-image"

# USD per token for Gemini 3.1 Flash Image (standard pricing, confirmed via a
# real test generation: $0.50 in / $60.00 out per million tokens).
PRICE_PER_INPUT_TOKEN = 0.50 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 60.00 / 1_000_000

BRANDS_DIR = Path(__file__).parent / "brands"


def load_brand_doc(brand_pack, filename):
    return (BRANDS_DIR / brand_pack / filename).read_text(encoding="utf-8")


def calculate_cost(tokens_in, tokens_out):
    return tokens_in * PRICE_PER_INPUT_TOKEN + tokens_out * PRICE_PER_OUTPUT_TOKEN


def get_client(api_key):
    return genai.Client(api_key=api_key)


def build_image_prompt(slide_text, brand_pack, slide_role):
    visual_style = load_brand_doc(brand_pack, "visual-style.md")
    if slide_role == "hero":
        framing = "Composição de cena completa, ambiente com espaço em redor do assunto principal."
    else:
        framing = (
            "Composição fechada num único assunto, com espaço vazio numa das "
            "margens para texto ser sobreposto depois."
        )
    return (
        "Gera uma imagem fotográfica, sem texto nenhum escrito na imagem, que "
        f"represente visualmente o seguinte conteúdo: {slide_text}\n\n"
        f"{framing}\n\n"
        "Segue este estilo visual da marca:\n" + visual_style
    )


def generate_image(client, prompt):
    interaction = client.interactions.create(model=MODEL, input=prompt)
    image_bytes = base64.b64decode(interaction.output_image.data)
    tokens_in = interaction.usage.total_input_tokens
    tokens_out = interaction.usage.total_output_tokens
    return image_bytes, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_image_gen.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add image_gen.py tests/test_image_gen.py
git commit -m "Add image_gen.py Gemini API wrapper"
```

---

### Task 6: `render.py` — HTML/CSS + Playwright compositor

**Files:**
- Create: `content-creator/render.py`
- Create: `content-creator/tests/test_render.py`

**Interfaces:**
- Consumes: `visual-style.md`'s color-palette lines (format locked in Task 1: `- **Label:** \`#RRGGBB\``).
- Produces:
  - `render.load_palette(brand_pack) -> dict[str, str]` (label → hex)
  - `render.contrast_ratio(hex_a, hex_b) -> float`
  - `render.check_contrast(role, text_color, background_color)` (raises `render.LowContrastError` if below the minimum for that `role`)
  - `render.build_slide_html(slide_text, image_bytes, brand_pack, slide_role) -> str`
  - `render.render_png(html) -> bytes` (Playwright; not unit-tested — exercised only in Task 8's manual live verification)
  - `render.MIN_FONT_PX`, `render.DEVICE_SCALE_FACTOR`, `render.BASE_WIDTH`, `render.BASE_HEIGHT` module constants

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_render.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'render'`)

- [ ] **Step 3: Write `render.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "Add render.py HTML/CSS + Playwright carousel-slide compositor"
```

---

### Task 7: `pipeline.py` — image generation orchestration

**Files:**
- Modify: `content-creator/pipeline.py`
- Create: `content-creator/tests/test_pipeline_images.py`

**Interfaces:**
- Consumes: `image_gen.generate_image(client, prompt) -> (bytes, int, int, float)` (Task 5), `render.build_slide_html(...) -> str` and `render.render_png(html) -> bytes` (Task 6), `storage.make_carousel_folder(root, topic, date_str) -> str` (Task 4), `db.create_slide_image`, `db.get_slide_image`, `db.list_slide_images`, `db.get_latest_slide_images`, `db.update_slide_image_status`, `db.set_idea_image_folder` (Task 3).
- Produces:
  - `pipeline.ensure_image_folder(conn, idea, images_root, storage_module=storage) -> str`
  - `pipeline.generate_slide_image(gemini_client, conn, idea, slide_index, slide_role, slide_text, prompt, images_root, daily_cap_usd, image_gen_module=image_gen, render_module=render, storage_module=storage, on_step=None) -> dict` (the created `slide_images` row)
  - `pipeline.approve_slide_image(conn, slide_image_id)`
  - `pipeline.reject_slide_image(conn, slide_image_id)`
  - `pipeline.maybe_mark_images_ready(conn, idea_id, total_slides)` (sets idea status to `"images_ready"` once every slide's latest attempt is `"approved"`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_images.py`:

```python
from pathlib import Path
from types import SimpleNamespace
import pytest
import db
import pipeline


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


@pytest.fixture
def idea(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    return db.get_idea(conn, idea_id)


def make_fake_image_gen(cost=0.07):
    def generate_image(client, prompt):
        return b"fake-image-bytes", 50, 1120, cost
    return SimpleNamespace(generate_image=generate_image)


def make_fake_render():
    def build_slide_html(slide_text, image_bytes, brand_pack, slide_role):
        return f"<html>{slide_role}:{slide_text}</html>"

    def render_png(html):
        return b"fake-png-bytes"

    return SimpleNamespace(build_slide_html=build_slide_html, render_png=render_png)


def test_generate_slide_image_creates_file_and_db_row(conn, idea, tmp_path):
    row = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "Ritual matinal", "um prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    assert row["status"] == "pending"
    assert row["cost_usd"] == pytest.approx(0.07)
    saved_file = Path(row["file_path"])
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"fake-png-bytes"


def test_generate_slide_image_sets_and_reuses_image_folder(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row1 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    assert idea_after["image_folder"] is not None

    row2 = pipeline.generate_slide_image(
        None, conn, idea_after, 1, "card", "texto 2", "prompt 2", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    assert Path(row1["file_path"]).parent == Path(row2["file_path"]).parent


def test_generate_slide_image_raises_when_daily_cap_already_reached(conn, idea, tmp_path):
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
        )


def test_generate_slide_image_reports_progress_via_on_step(conn, idea, tmp_path):
    events = []
    pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
        on_step=lambda step, status, detail=None: events.append((step, status)),
    )
    assert events == [
        ("generate_image", "running"), ("generate_image", "done"),
        ("render_image", "running"), ("render_image", "done"),
    ]


def test_on_step_reports_error_when_render_fails(conn, idea, tmp_path):
    def failing_render(slide_text, image_bytes, brand_pack, slide_role):
        raise ValueError("contraste insuficiente")

    fake_render = SimpleNamespace(build_slide_html=failing_render, render_png=lambda html: b"x")
    events = []
    with pytest.raises(ValueError):
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(), render_module=fake_render,
            on_step=lambda step, status, detail=None: events.append((step, status, detail)),
        )
    assert events[-1] == ("render_image", "error", "contraste insuficiente")


def test_regenerating_a_slide_creates_a_new_row_not_overwrite(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row1 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt v1", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    row2 = pipeline.generate_slide_image(
        None, conn, idea_after, 0, "hero", "texto", "prompt v2", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    assert row1["id"] != row2["id"]
    assert len(db.list_slide_images(conn, idea["id"])) == 2


def test_approve_and_reject_slide_image(conn, idea, tmp_path):
    row = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    pipeline.approve_slide_image(conn, row["id"])
    assert db.get_slide_image(conn, row["id"])["status"] == "approved"
    pipeline.reject_slide_image(conn, row["id"])
    assert db.get_slide_image(conn, row["id"])["status"] == "rejected"


def test_maybe_mark_images_ready_only_when_all_slides_approved(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row0 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "t0", "p0", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    row1 = pipeline.generate_slide_image(
        None, conn, idea_after, 1, "card", "t1", "p1", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    pipeline.approve_slide_image(conn, row0["id"])
    pipeline.maybe_mark_images_ready(conn, idea["id"], total_slides=2)
    assert db.get_idea(conn, idea["id"])["status"] != "images_ready"

    pipeline.approve_slide_image(conn, row1["id"])
    pipeline.maybe_mark_images_ready(conn, idea["id"], total_slides=2)
    assert db.get_idea(conn, idea["id"])["status"] == "images_ready"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd content-creator && python3 -m pytest tests/test_pipeline_images.py -v`
Expected: FAIL (`AttributeError: module 'pipeline' has no attribute 'generate_slide_image'`)

- [ ] **Step 3: Update `pipeline.py`**

Add these imports at the top of `pipeline.py` (alongside the existing `import ai` / `import db`):

```python
from datetime import datetime, timezone
from pathlib import Path

import ai
import db
import image_gen
import render
import storage
```

Add these functions at the end of `pipeline.py` (after `run_generation_pipeline`):

```python
def ensure_image_folder(conn, idea, images_root, storage_module=storage):
    """Compute (once) and persist the per-carousel folder name, or return the
    existing one — so regenerating a single slide always lands in the same
    place instead of picking a new folder each time."""
    if idea.get("image_folder"):
        return idea["image_folder"]
    date_str = datetime.now(timezone.utc).date().isoformat()
    folder = storage_module.make_carousel_folder(images_root, idea["topic"], date_str)
    Path(images_root, folder).mkdir(parents=True, exist_ok=True)
    db.set_idea_image_folder(conn, idea["id"], folder)
    idea["image_folder"] = folder
    return folder


def generate_slide_image(
    gemini_client, conn, idea, slide_index, slide_role, slide_text, prompt,
    images_root, daily_cap_usd, image_gen_module=image_gen, render_module=render,
    storage_module=storage, on_step=None,
):
    idea_id = idea["id"]

    if on_step:
        on_step("generate_image", "running")
    if db.would_exceed_daily_cap(conn, ESTIMATED_MAX_CALL_COST_USD, daily_cap_usd):
        error = DailyBudgetExceededError(
            f"This call could push today's spend over the ${daily_cap_usd:.2f} daily cap. "
            "Try again tomorrow or raise MAX_DAILY_SPEND_USD."
        )
        if on_step:
            on_step("generate_image", "error", str(error))
        raise error
    try:
        image_bytes, tokens_in, tokens_out, cost = image_gen_module.generate_image(gemini_client, prompt)
    except Exception as e:
        if on_step:
            on_step("generate_image", "error", str(e))
        raise
    db.log_api_call(conn, "generate_image", tokens_in, tokens_out, cost, idea_id=idea_id)
    if on_step:
        on_step("generate_image", "done")

    folder = ensure_image_folder(conn, idea, images_root, storage_module=storage_module)

    if on_step:
        on_step("render_image", "running")
    try:
        html = render_module.build_slide_html(slide_text, image_bytes, idea["brand_pack"], slide_role)
        png_bytes = render_module.render_png(html)
        file_path = Path(images_root) / folder / f"slide-{slide_index:02d}.png"
        file_path.write_bytes(png_bytes)
    except Exception as e:
        if on_step:
            on_step("render_image", "error", str(e))
        raise
    if on_step:
        on_step("render_image", "done")

    slide_image_id = db.create_slide_image(conn, idea_id, slide_index, prompt, str(file_path), cost)
    return db.get_slide_image(conn, slide_image_id)


def approve_slide_image(conn, slide_image_id):
    db.update_slide_image_status(conn, slide_image_id, "approved")


def reject_slide_image(conn, slide_image_id):
    db.update_slide_image_status(conn, slide_image_id, "rejected")


def maybe_mark_images_ready(conn, idea_id, total_slides):
    latest = db.get_latest_slide_images(conn, idea_id)
    if len(latest) == total_slides and all(row["status"] == "approved" for row in latest):
        db.update_idea_status(conn, idea_id, "images_ready")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd content-creator && python3 -m pytest tests/test_pipeline_images.py tests/test_pipeline.py -v`
Expected: PASS (both files — confirms the new imports/functions didn't disturb the existing text pipeline)

- [ ] **Step 5: Commit**

```bash
git add pipeline.py tests/test_pipeline_images.py
git commit -m "Add image-generation orchestration to pipeline.py"
```

---

### Task 8: `app.py` — "Gerar Imagens" tab and carousel preview

**Files:**
- Modify: `content-creator/app.py`

**Interfaces:**
- Consumes: `pipeline.generate_slide_image`, `pipeline.approve_slide_image`, `pipeline.reject_slide_image`, `pipeline.maybe_mark_images_ready` (Task 7), `image_gen.build_image_prompt`, `image_gen.get_client` (Task 5), `storage.images_root` (Task 4), `db.get_latest_slide_images` (Task 3), and the existing `run_with_progress` helper already defined in `app.py`.
- Produces: no new importable interface — this is the UI leaf.

This task has no isolated unit tests (it's UI wiring over already-tested logic, same as v1 and the progress-UX task) — it's verified with one real, manual, paid end-to-end run, matching this project's established rule that no amount of mocked coverage substitutes for a real human-observed run before trusting an AI-calling feature.

- [ ] **Step 1: Add new imports and clients near the top of `app.py`**

After the existing `import pipeline` line, add:

```python
import image_gen
import storage
```

After `client = ai.get_client(cfg.api_key)`, add:

```python
gemini_client = image_gen.get_client(cfg.gemini_api_key)
images_root = storage.images_root(cfg.db_path)
```

- [ ] **Step 2: Add the "Gerar Imagens" tab**

Change the tabs line from:

```python
tab_new, tab_library = st.tabs(["Nova Ideia", "Biblioteca"])
```

to:

```python
tab_new, tab_images, tab_library = st.tabs(["Nova Ideia", "Gerar Imagens", "Biblioteca"])
```

- [ ] **Step 3: Implement the tab body**

Insert this new `with tab_images:` block between the existing `with tab_new:` block and the existing `with tab_library:` block:

```python
with tab_images:
    st.subheader("Gerar Imagens do Carrossel")
    approved = db.list_ideas(conn, brand_pack=cfg.brand_pack, status="approved")
    if not approved:
        st.info("Sem ideias aprovadas. Aprova um rascunho na aba 'Nova Ideia' primeiro.")
    else:
        options = {f"#{i['id']} — {i['topic']}": i for i in approved}
        chosen_label = st.selectbox("Ideia", list(options.keys()), key="img_idea_select")
        idea = db.get_idea(conn, options[chosen_label]["id"])
        latest_draft = db.list_drafts_for_idea(conn, idea["id"])[-1]
        slides = latest_draft["slides"]
        existing_images = {img["slide_index"]: img for img in db.get_latest_slide_images(conn, idea["id"])}

        for i, slide_text in enumerate(slides):
            role = "hero" if i == 0 else "card"
            st.markdown(f"**Slide {i + 1}** ({'capa' if role == 'hero' else 'cartão'})")
            existing = existing_images.get(i)

            if existing:
                st.image(existing["file_path"], width=300)
                if existing["status"] == "approved":
                    st.success("Aprovado")
                col1, col2 = st.columns(2)
                if existing["status"] != "approved" and col1.button("Aprovar", key=f"approve_{i}"):
                    pipeline.approve_slide_image(conn, existing["id"])
                    pipeline.maybe_mark_images_ready(conn, idea["id"], len(slides))
                    st.rerun()
                if col2.button("Gerar novamente", key=f"regen_{i}"):
                    st.session_state[f"show_prompt_{i}"] = True

            if not existing or st.session_state.get(f"show_prompt_{i}"):
                prompt_key = f"prompt_{i}"
                if prompt_key not in st.session_state:
                    st.session_state[prompt_key] = image_gen.build_image_prompt(slide_text, cfg.brand_pack, role)
                st.session_state[prompt_key] = st.text_area(
                    "Prompt da imagem (podes editar)", value=st.session_state[prompt_key], key=f"prompt_area_{i}",
                )
                if st.button("Gerar imagem", key=f"generate_{i}"):
                    try:
                        run_with_progress(
                            lambda on_step: pipeline.generate_slide_image(
                                gemini_client, conn, idea, i, role, slide_text,
                                st.session_state[prompt_key], images_root, cfg.max_daily_spend_usd,
                                on_step=on_step,
                            ),
                        )
                    except pipeline.DailyBudgetExceededError as e:
                        st.error(str(e))
                    else:
                        st.session_state[f"show_prompt_{i}"] = False
                        st.rerun()

        st.divider()
        st.subheader("Pré-visualização do Carrossel")
        latest = db.get_latest_slide_images(conn, idea["id"])
        approved_images = [img for img in latest if img["status"] == "approved"]
        if len(approved_images) == len(slides):
            preview_key = "carousel_preview_index"
            if preview_key not in st.session_state:
                st.session_state[preview_key] = 0
            idx = st.session_state[preview_key]
            st.image(approved_images[idx]["file_path"], width=400)
            st.caption(slides[idx])
            col_prev, col_next = st.columns(2)
            if col_prev.button("◀ Anterior") and idx > 0:
                st.session_state[preview_key] -= 1
                st.rerun()
            if col_next.button("Seguinte ▶") and idx < len(slides) - 1:
                st.session_state[preview_key] += 1
                st.rerun()
            thumb_cols = st.columns(len(slides))
            for j, col in enumerate(thumb_cols):
                if col.button(f"{j + 1}", key=f"thumb_{j}"):
                    st.session_state[preview_key] = j
                    st.rerun()
            st.write(f"**Legenda:** {latest_draft['caption']}")
        else:
            st.info("Aprova todas as imagens para veres a pré-visualização do carrossel.")
```

- [ ] **Step 4: Run the full test suite to confirm nothing else broke**

Run: `cd content-creator && python3 -m pytest -v`
Expected: PASS (every test from Tasks 1–7 plus the pre-existing v1/progress-UX suite)

- [ ] **Step 5: Manual live verification (real, paid, end-to-end)**

Start the app (`python3 -m streamlit run app.py`), open it in a browser, and with an idea that already has an `approved` draft (from earlier testing):
1. Open "Gerar Imagens", pick that idea.
2. For slide 1, confirm the auto-built prompt appears, edit it if desired, click "Gerar imagem" — confirm the progress checklist appears and a real image is produced and displayed.
3. Click "Aprovar" for that slide.
4. Repeat for at least one more slide (a `"card"`-role slide) to confirm the hero/card visual difference is real.
5. Deliberately trigger one regeneration ("Gerar novamente") on an approved slide to confirm it replaces only that slide.
6. Once every slide is approved, confirm the "Pré-visualização do Carrossel" section appears, and that Prev/Next and the thumbnail strip correctly step through the real generated images alongside the real caption text.
7. Check the Dropbox-synced `images/<date>_<slug>/` folder on disk to confirm the PNG files are actually there.

If any step fails, fix it and re-run this same manual check from the start — this is the step that catches the real, unmockable bugs (API response shape surprises, Playwright/font rendering issues, path handling on Windows), the same way v1's final live test caught 3 real bugs no unit test could.

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "Add 'Gerar Imagens' tab and carousel preview to app.py"
```

---

## Self-Review Notes

- **Spec coverage:** every "In scope" item in the spec has a task — brand-pack visual style (Task 1), Gemini provider + cost tracking (Tasks 2, 5, 7), per-slide regeneration (Task 7's new-row-per-attempt + Task 8's "Gerar novamente"), prompt review step (Task 8's editable `st.text_area`), hero/card distinct layouts (Task 6), fixed output size + font minimums + contrast checks (Task 6), per-carousel Dropbox-synced storage with stable folder naming (Tasks 3, 4, 7), carousel preview (Task 8), `on_step` error/progress reporting reused everywhere (Tasks 7, 8).
- **Placeholder scan:** no TBD/TODO markers; every step has real, complete code.
- **Type consistency:** `slide_role` is `"hero"` / `"card"` consistently across `image_gen.build_image_prompt`, `render.build_slide_html`, and `pipeline.generate_slide_image`. `on_step(step, status, detail=None)` signature matches the one already shipped in `pipeline.py`'s text functions. `images_root` is a `pathlib.Path` everywhere it's threaded through (Task 4 → 7 → 8).
