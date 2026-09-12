# Content Creator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python/Streamlit app that turns a topic or reference text into a quality-checked Instagram carousel (caption + slides) in PT-PT, using a swappable "brand pack" of voice/quality docs, an Anthropic-API-backed generate→critique→revise pipeline, and a SQLite database that tracks every idea and draft.

**Architecture:** A brand-agnostic engine (`config.py`, `db.py`, `ai.py`, `pipeline.py`) that reads brand-specific docs from `brands/<brand_pack>/` at runtime, wrapped by a thin Streamlit UI (`app.py`). All AI calls go through the Anthropic API (not the Claude Pro/Max subscription), are cost-logged to SQLite, and are capped by an in-app daily spend limit plus a 2-round revision cap.

**Tech Stack:** Python 3.11+, `anthropic` SDK, Streamlit, SQLite (stdlib `sqlite3`), `python-dotenv`, `pytest`.

**Spec:** `content-creator/docs/superpowers/specs/2026-09-12-content-creator-design.md`

## Global Constraints

- All generated content (topics, captions, slides) is PT-PT, regardless of the language of any reference text.
- Reference text hard cap: 6,000 words — reject above that, do not silently truncate.
- Revision loop hard cap: 2 rounds, always — after round 2, hand off to the human regardless of remaining flags.
- No unbounded retries on any API call.
- Daily spend cap enforced in-app via `MAX_DAILY_SPEND_USD` (default `2.0`), checked before every API call.
- Deletion is soft by default (`archived_at` set); hard delete is a separate, explicit action only allowed on already-archived rows.
- Slides are stored as a JSON array in a single `drafts.slides` column, not a normalized table.
- Single shared Anthropic API key via `.env`; no per-user auth.
- `DB_PATH` defaults to `C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db`.
- `app.py`, `db.py`, `ai.py`, `pipeline.py` must contain no brand-specific text — everything Mariana-specific lives under `brands/marianabotelho-ig/`.

---

### Task 1: Brand pack — `marianabotelho-ig`

**Files:**
- Create: `content-creator/brands/marianabotelho-ig/tone-of-voice.md`
- Create: `content-creator/brands/marianabotelho-ig/domain-framework.md`
- Create: `content-creator/brands/marianabotelho-ig/quality-criteria.md`
- Create: `content-creator/brands/marianabotelho-ig/anti-patterns.md`
- Create: `content-creator/brands/marianabotelho-ig/output-examples.md`
- Create: `content-creator/brands/marianabotelho-ig/research-brief.md`
- Test: `content-creator/tests/test_brand_pack.py`

**Interfaces:**
- Produces: a `brand_pack_files(brand_pack_dir) -> list[str]` contract (any brand pack folder must contain exactly these 6 filenames) that Task 7 relies on when loading docs by name.

- [ ] **Step 1: Copy the six brand doc files verbatim**

Copy the full content of each file from the "Appendix: Brand Pack — `marianabotelho-ig`" section of the spec (`content-creator/docs/superpowers/specs/2026-09-12-content-creator-design.md`) into the six files listed above — each Appendix subsection (`### tone-of-voice.md`, etc.) is the exact content of the correspondingly-named file, with the ` ```markdown ` fence removed.

- [ ] **Step 2: Write the failing test**

```python
# content-creator/tests/test_brand_pack.py
from pathlib import Path

BRAND_PACK_DIR = Path(__file__).parent.parent / "brands" / "marianabotelho-ig"

REQUIRED_FILES = [
    "tone-of-voice.md",
    "domain-framework.md",
    "quality-criteria.md",
    "anti-patterns.md",
    "output-examples.md",
    "research-brief.md",
]

def test_all_required_brand_files_exist_and_are_nonempty():
    for filename in REQUIRED_FILES:
        path = BRAND_PACK_DIR / filename
        assert path.exists(), f"missing brand file: {filename}"
        assert len(path.read_text(encoding="utf-8").strip()) > 0, f"empty brand file: {filename}"
```

- [ ] **Step 3: Run test to verify it fails (before Step 1 is done) or passes (after)**

Run: `pytest content-creator/tests/test_brand_pack.py -v`
Expected: PASS (all 6 files present and non-empty) once Step 1 is complete.

- [ ] **Step 4: Commit**

```bash
git add content-creator/brands/marianabotelho-ig content-creator/tests/test_brand_pack.py
git commit -m "Add marianabotelho-ig brand pack, copied from OpenSquad"
```

---

### Task 2: Config loader

**Files:**
- Create: `content-creator/config.py`
- Test: `content-creator/tests/test_config.py`

**Interfaces:**
- Produces: `load_config(env: dict | None = None) -> Config`, where `Config` has attributes `.api_key: str`, `.db_path: str`, `.max_daily_spend_usd: float`, `.brand_pack: str`. Raises `ConfigError` if `ANTHROPIC_API_KEY` is missing. Used by Task 8 (`pipeline.py`) and Task 9 (`app.py`).

- [ ] **Step 1: Write the failing tests**

```python
# content-creator/tests/test_config.py
import pytest
from config import load_config, ConfigError, DEFAULT_DB_PATH, DEFAULT_MAX_DAILY_SPEND_USD, DEFAULT_BRAND_PACK

def test_raises_when_api_key_missing():
    with pytest.raises(ConfigError):
        load_config(env={})

def test_applies_defaults_when_only_api_key_set():
    cfg = load_config(env={"ANTHROPIC_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.db_path == DEFAULT_DB_PATH
    assert cfg.max_daily_spend_usd == DEFAULT_MAX_DAILY_SPEND_USD
    assert cfg.brand_pack == DEFAULT_BRAND_PACK

def test_overrides_are_respected():
    cfg = load_config(env={
        "ANTHROPIC_API_KEY": "sk-test",
        "DB_PATH": "C:\\custom\\path.db",
        "MAX_DAILY_SPEND_USD": "5.5",
        "BRAND_PACK": "other-brand",
    })
    assert cfg.db_path == "C:\\custom\\path.db"
    assert cfg.max_daily_spend_usd == 5.5
    assert cfg.brand_pack == "other-brand"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Write minimal implementation**

```python
# content-creator/config.py
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = r"C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db"
DEFAULT_MAX_DAILY_SPEND_USD = 2.0
DEFAULT_BRAND_PACK = "marianabotelho-ig"


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, api_key, db_path, max_daily_spend_usd, brand_pack):
        self.api_key = api_key
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
    db_path = env.get("DB_PATH", DEFAULT_DB_PATH)
    max_daily_spend_usd = float(env.get("MAX_DAILY_SPEND_USD", DEFAULT_MAX_DAILY_SPEND_USD))
    brand_pack = env.get("BRAND_PACK", DEFAULT_BRAND_PACK)
    return Config(api_key, db_path, max_daily_spend_usd, brand_pack)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add content-creator/config.py content-creator/tests/test_config.py
git commit -m "Add config loader with env defaults and validation"
```

---

### Task 3: Database — `ideas` table and CRUD

**Files:**
- Create: `content-creator/db.py`
- Test: `content-creator/tests/test_db_ideas.py`

**Interfaces:**
- Produces: `get_connection(db_path: str) -> sqlite3.Connection`, `init_db(conn)`, `create_idea(conn, brand_pack, source_type, topic, reference_text=None, pillar=None, tone=None) -> int`, `get_idea(conn, idea_id) -> dict | None`, `list_ideas(conn, brand_pack=None, status=None, include_archived=False) -> list[dict]`, `archive_idea(conn, idea_id)`, `hard_delete_idea(conn, idea_id)`, `update_idea_status(conn, idea_id, status)`. Used by Task 4, Task 8, Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# content-creator/tests/test_db_ideas.py
import pytest
import db

@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection

def test_create_and_get_idea(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ashwagandha para o stress")
    idea = db.get_idea(conn, idea_id)
    assert idea["topic"] == "ashwagandha para o stress"
    assert idea["brand_pack"] == "marianabotelho-ig"
    assert idea["status"] == "idea"
    assert idea["archived_at"] is None

def test_list_ideas_excludes_archived_by_default(conn):
    active_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic A")
    archived_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic B")
    db.archive_idea(conn, archived_id)

    ideas = db.list_ideas(conn, brand_pack="marianabotelho-ig")
    ids = [i["id"] for i in ideas]
    assert active_id in ids
    assert archived_id not in ids

def test_list_ideas_include_archived(conn):
    archived_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic B")
    db.archive_idea(conn, archived_id)

    ideas = db.list_ideas(conn, brand_pack="marianabotelho-ig", include_archived=True)
    ids = [i["id"] for i in ideas]
    assert archived_id in ids

def test_archive_sets_archived_at_and_status(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic C")
    db.archive_idea(conn, idea_id)
    idea = db.get_idea(conn, idea_id)
    assert idea["archived_at"] is not None
    assert idea["status"] == "archived"

def test_hard_delete_requires_archived_first(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic D")
    with pytest.raises(ValueError):
        db.hard_delete_idea(conn, idea_id)

def test_hard_delete_removes_row(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic E")
    db.archive_idea(conn, idea_id)
    db.hard_delete_idea(conn, idea_id)
    assert db.get_idea(conn, idea_id) is None

def test_update_idea_status(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic F")
    db.update_idea_status(conn, idea_id, "approved")
    assert db.get_idea(conn, idea_id)["status"] == "approved"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_db_ideas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Write minimal implementation**

```python
# content-creator/db.py
import sqlite3
from datetime import datetime, timezone


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
        """
    )
    conn.commit()


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_idea(conn, brand_pack, source_type, topic, reference_text=None, pillar=None, tone=None):
    cursor = conn.execute(
        "INSERT INTO ideas (created_at, brand_pack, source_type, reference_text, topic, pillar, tone, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'idea')",
        (_now(), brand_pack, source_type, reference_text, topic, pillar, tone),
    )
    conn.commit()
    return cursor.lastrowid


def get_idea(conn, idea_id):
    row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    return dict(row) if row else None


def list_ideas(conn, brand_pack=None, status=None, include_archived=False):
    query = "SELECT * FROM ideas WHERE 1=1"
    params = []
    if not include_archived:
        query += " AND archived_at IS NULL"
    if brand_pack:
        query += " AND brand_pack = ?"
        params.append(brand_pack)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def archive_idea(conn, idea_id):
    conn.execute(
        "UPDATE ideas SET archived_at = ?, status = 'archived' WHERE id = ?", (_now(), idea_id)
    )
    conn.commit()


def hard_delete_idea(conn, idea_id):
    idea = get_idea(conn, idea_id)
    if idea is None or idea["archived_at"] is None:
        raise ValueError("Can only hard-delete an idea that has already been archived")
    conn.execute("DELETE FROM drafts WHERE idea_id = ?", (idea_id,))
    conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()


def update_idea_status(conn, idea_id, status):
    conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_db_ideas.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add content-creator/db.py content-creator/tests/test_db_ideas.py
git commit -m "Add SQLite ideas table with CRUD and soft/hard delete"
```

---

### Task 4: Database — `drafts` and `api_calls`, spend tracking

**Files:**
- Modify: `content-creator/db.py` (add `drafts` and `api_calls` tables and functions)
- Test: `content-creator/tests/test_db_drafts_and_spend.py`

**Interfaces:**
- Consumes: `get_connection`, `init_db`, `create_idea` from Task 3.
- Produces: `create_draft(conn, idea_id, round_, caption, slides, quality_flags=None) -> int`, `list_drafts_for_idea(conn, idea_id) -> list[dict]` (with `slides` and `quality_flags` already JSON-decoded), `log_api_call(conn, function, tokens_in, tokens_out, estimated_cost_usd, idea_id=None)`, `get_spend_since(conn, since_iso) -> float`, `get_spend_today(conn) -> float`, `would_exceed_daily_cap(conn, estimated_call_cost, daily_cap_usd) -> bool`. Used by Task 8 (`pipeline.py`) and Task 9 (`app.py`).

- [ ] **Step 1: Write the failing tests**

```python
# content-creator/tests/test_db_drafts_and_spend.py
import pytest
import db

@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection

@pytest.fixture
def idea_id(conn):
    return db.create_idea(conn, "marianabotelho-ig", "manual", "5 plantas adaptogénicas")

def test_create_and_list_drafts_round_trips_json(conn, idea_id):
    db.create_draft(
        conn, idea_id, round_=0,
        caption="Legenda de teste",
        slides=["slide 1", "slide 2"],
        quality_flags=[{"criterion": "Hashtags", "issue": "só 3 hashtags"}],
    )
    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert len(drafts) == 1
    assert drafts[0]["slides"] == ["slide 1", "slide 2"]
    assert drafts[0]["quality_flags"] == [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]
    assert drafts[0]["round"] == 0

def test_drafts_ordered_by_round(conn, idea_id):
    db.create_draft(conn, idea_id, round_=1, caption="v2", slides=["a"])
    db.create_draft(conn, idea_id, round_=0, caption="v1", slides=["a"])
    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert [d["round"] for d in drafts] == [0, 1]

def test_log_api_call_and_get_spend_today(conn, idea_id):
    db.log_api_call(conn, "generate_draft", tokens_in=1000, tokens_out=500, estimated_cost_usd=0.05, idea_id=idea_id)
    db.log_api_call(conn, "critique_draft", tokens_in=800, tokens_out=200, estimated_cost_usd=0.03, idea_id=idea_id)
    assert db.get_spend_today(conn) == pytest.approx(0.08)

def test_would_exceed_daily_cap(conn, idea_id):
    db.log_api_call(conn, "generate_draft", tokens_in=1000, tokens_out=500, estimated_cost_usd=1.90, idea_id=idea_id)
    assert db.would_exceed_daily_cap(conn, estimated_call_cost=0.20, daily_cap_usd=2.0) is True
    assert db.would_exceed_daily_cap(conn, estimated_call_cost=0.05, daily_cap_usd=2.0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_db_drafts_and_spend.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: drafts`

- [ ] **Step 3: Add the new tables and functions to `db.py`**

Add to the `executescript` call inside `init_db` (same statement, extended):

```python
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
```

Add to the bottom of `db.py`:

```python
import json


def create_draft(conn, idea_id, round_, caption, slides, quality_flags=None):
    cursor = conn.execute(
        "INSERT INTO drafts (idea_id, round, caption, slides, quality_flags, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (idea_id, round_, caption, json.dumps(slides), json.dumps(quality_flags or []), _now()),
    )
    conn.commit()
    return cursor.lastrowid


def list_drafts_for_idea(conn, idea_id):
    rows = conn.execute(
        "SELECT * FROM drafts WHERE idea_id = ? ORDER BY round ASC", (idea_id,)
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["slides"] = json.loads(d["slides"])
        d["quality_flags"] = json.loads(d["quality_flags"]) if d["quality_flags"] else []
        result.append(d)
    return result


def log_api_call(conn, function, tokens_in, tokens_out, estimated_cost_usd, idea_id=None):
    conn.execute(
        "INSERT INTO api_calls (idea_id, function, tokens_in, tokens_out, estimated_cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (idea_id, function, tokens_in, tokens_out, estimated_cost_usd, _now()),
    )
    conn.commit()


def get_spend_since(conn, since_iso):
    row = conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd), 0) AS total FROM api_calls WHERE created_at >= ?",
        (since_iso,),
    ).fetchone()
    return row["total"]


def get_spend_today(conn):
    start_of_day = (
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    )
    return get_spend_since(conn, start_of_day)


def get_spend_this_month(conn):
    start_of_month = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    return get_spend_since(conn, start_of_month)


def would_exceed_daily_cap(conn, estimated_call_cost, daily_cap_usd):
    return (get_spend_today(conn) + estimated_call_cost) > daily_cap_usd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_db_drafts_and_spend.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full test suite to check nothing broke**

Run: `pytest content-creator/tests/ -v`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add content-creator/db.py content-creator/tests/test_db_drafts_and_spend.py
git commit -m "Add drafts and api_calls tables with spend tracking"
```

---

### Task 5: AI cost estimation and reference-length validation (pure functions)

**Files:**
- Create: `content-creator/ai.py`
- Test: `content-creator/tests/test_ai_cost_and_validation.py`

**Interfaces:**
- Produces: `MAX_REFERENCE_WORDS = 6000`, `MAX_REVISION_ROUNDS = 2`, `ReferenceTooLongError`, `validate_reference_length(reference_text: str)`, `calculate_cost(tokens_in: int, tokens_out: int) -> float`. Used by Task 7 and Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# content-creator/tests/test_ai_cost_and_validation.py
import pytest
from ai import validate_reference_length, calculate_cost, ReferenceTooLongError, MAX_REFERENCE_WORDS

def test_reference_under_limit_passes():
    validate_reference_length("palavra " * 100)  # 100 words, well under limit

def test_reference_over_limit_raises():
    with pytest.raises(ReferenceTooLongError):
        validate_reference_length("palavra " * (MAX_REFERENCE_WORDS + 1))

def test_calculate_cost_is_proportional_to_tokens():
    cost_small = calculate_cost(tokens_in=1000, tokens_out=500)
    cost_large = calculate_cost(tokens_in=2000, tokens_out=1000)
    assert cost_large == pytest.approx(cost_small * 2)
    assert cost_small > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_ai_cost_and_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai'`

- [ ] **Step 3: Write minimal implementation**

```python
# content-creator/ai.py
MAX_REFERENCE_WORDS = 6000
MAX_REVISION_ROUNDS = 2

# USD per token. Update if Anthropic's published pricing changes.
PRICE_PER_INPUT_TOKEN = 3.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 15.00 / 1_000_000


class ReferenceTooLongError(Exception):
    pass


def validate_reference_length(reference_text):
    word_count = len(reference_text.split())
    if word_count > MAX_REFERENCE_WORDS:
        raise ReferenceTooLongError(
            f"Reference text has {word_count} words, over the {MAX_REFERENCE_WORDS}-word limit. "
            "Trim it or split it into smaller parts."
        )


def calculate_cost(tokens_in, tokens_out):
    return tokens_in * PRICE_PER_INPUT_TOKEN + tokens_out * PRICE_PER_OUTPUT_TOKEN
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_ai_cost_and_validation.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add content-creator/ai.py content-creator/tests/test_ai_cost_and_validation.py
git commit -m "Add reference-length validation and API cost calculation"
```

---

### Task 6: Prompt templates — draft now, refine live in Claude Code

**Files:**
- Create: `content-creator/prompts/extract_topics.md`
- Create: `content-creator/prompts/generate_draft.md`
- Create: `content-creator/prompts/critique_draft.md`
- Create: `content-creator/prompts/revise_draft.md`

**Interfaces:**
- Produces: four prompt template files, each containing `{{PLACEHOLDER}}` tokens, loaded by `ai.load_prompt(name)` and filled by `ai.render_prompt(template, **kwargs)` in Task 7.

This task is **not** run by a subagent — per the spec's Testing strategy, judging prompt quality requires a human reading real output, so this is a manual, interactive task done together in Claude Code (free, using the Pro subscription, no API key spend).

- [ ] **Step 1: Save the v0 draft templates**

```markdown
<!-- content-creator/prompts/extract_topics.md -->
Você é um estrategista de conteúdo para Instagram. A sua tarefa é ler o texto de referência fornecido pelo utilizador e propor até 5 ângulos de conteúdo distintos, genuinamente bem fundamentados no material — nunca preencher a lista para atingir um número: 2 ângulos excelentes é melhor do que 5 medíocres.

Regras obrigatórias:
- Todo o output deve ser em Português Europeu (PT-PT), mesmo que o texto de referência esteja noutra língua.
- Cada ângulo deve estar associado a um dos pilares de conteúdo listados abaixo.
- Responda APENAS com um array JSON válido, sem texto adicional antes ou depois, no formato:
[{"topic": "...", "pillar": "..."}]

## Pilares de Conteúdo e Regras de Estrutura
{{DOMAIN_FRAMEWORK}}
```

```markdown
<!-- content-creator/prompts/generate_draft.md -->
Você é um copywriter especializado em Instagram, escrevendo para a marca descrita abaixo. Escreva um carrossel completo (slides + legenda) sobre o tópico fornecido pelo utilizador, seguindo rigorosamente a estrutura, o tom e as regras abaixo.

Regras obrigatórias:
- Todo o output deve ser em Português Europeu (PT-PT).
- Siga a estrutura de carrossel e legenda descrita no framework abaixo.
- Escreva no tom de voz indicado abaixo.
- Responda APENAS com um objecto JSON válido, sem texto adicional antes ou depois, no formato:
{"caption": "...", "slides": ["...", "...", "..."]}

## Framework de Estrutura
{{DOMAIN_FRAMEWORK}}

## Tom de Voz Escolhido
{{TONE_OF_VOICE}}
```

```markdown
<!-- content-creator/prompts/critique_draft.md -->
Você é um revisor de qualidade editorial. Avalie o rascunho de carrossel fornecido pelo utilizador contra os critérios de qualidade e os anti-padrões abaixo. Liste APENAS os critérios que falharam, cada um com uma explicação curta e específica da falha.

Responda APENAS com um array JSON válido, sem texto adicional antes ou depois, no formato:
[{"criterion": "...", "issue": "..."}]

Se não houver falhas, responda com um array vazio: []

## Rascunho a Avaliar
{{DRAFT_JSON}}

## Critérios de Qualidade
{{QUALITY_CRITERIA}}

## Anti-Padrões
{{ANTI_PATTERNS}}
```

```markdown
<!-- content-creator/prompts/revise_draft.md -->
Você é um copywriter a corrigir um rascunho de carrossel. Corrija APENAS os problemas listados abaixo — não reescreva partes que já estão correctas.

Responda APENAS com um objecto JSON válido, sem texto adicional antes ou depois, no formato:
{"caption": "...", "slides": ["...", "...", "..."]}

## Rascunho Actual
{{DRAFT_JSON}}

## Problemas a Corrigir
{{QUALITY_FLAGS}}
```

- [ ] **Step 2: Prototype each prompt live, in this Claude Code session**

For each of the 4 prompts, together in this conversation (not delegated to a subagent):
1. Pick 2-3 real example inputs (e.g. a real topic from `research-brief.md`'s gaps, or a deliberately flawed sample draft for `critique_draft`/`revise_draft`).
2. Run the prompt as a real Claude Code request, substituting `{{...}}` placeholders with real brand-pack content by hand.
3. Read the actual output and judge it against `quality-criteria.md` and `anti-patterns.md` in the brand pack.
4. If it's weak (vague hook, missed the pharmaceutical anchor, wrong CTA, etc.), edit the `.md` template's wording and re-run.
5. Repeat until output consistently passes a human read.

- [ ] **Step 3: Save the final wording back into the 4 files**

Overwrite the v0 drafts from Step 1 with whatever wording won in Step 2.

- [ ] **Step 4: Commit**

```bash
git add content-creator/prompts
git commit -m "Add and refine AI prompt templates for the generation pipeline"
```

---

### Task 7: AI API wrapper functions

**Files:**
- Modify: `content-creator/ai.py` (add prompt loading, rendering, Claude API calls)
- Test: `content-creator/tests/test_ai_functions.py`

**Interfaces:**
- Consumes: `validate_reference_length`, `calculate_cost` from Task 5; the 4 prompt files from Task 6; brand pack docs from Task 1.
- Produces: `get_client(api_key) -> anthropic.Anthropic`, `load_prompt(name: str) -> str`, `load_brand_doc(brand_pack: str, filename: str) -> str`, `render_prompt(template: str, **kwargs: str) -> str`, `extract_topics(client, reference_text, brand_pack) -> tuple[list[dict], int, int, float]`, `generate_draft(client, topic, tone, pillar, brand_pack) -> tuple[dict, int, int, float]`, `critique_draft(client, draft, brand_pack) -> tuple[list[dict], int, int, float]`, `revise_draft(client, draft, flags, brand_pack) -> tuple[dict, int, int, float]`. Each tuple is `(result, tokens_in, tokens_out, estimated_cost_usd)`. Used by Task 8 (`pipeline.py`).

- [ ] **Step 1: Write the failing tests (Anthropic client mocked — no real API calls)**

```python
# content-creator/tests/test_ai_functions.py
import json
from unittest.mock import MagicMock
import pytest
import ai


def make_fake_client(response_text, tokens_in=100, tokens_out=50):
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=response_text)]
    fake_response.usage.input_tokens = tokens_in
    fake_response.usage.output_tokens = tokens_out
    client = MagicMock()
    client.messages.create.return_value = fake_response
    return client


def test_render_prompt_substitutes_placeholders():
    template = "Olá {{NOME}}, o teu pilar é {{PILAR}}."
    result = ai.render_prompt(template, nome="Mariana", pilar="Educativo")
    assert result == "Olá Mariana, o teu pilar é Educativo."


def test_load_prompt_reads_file():
    text = ai.load_prompt("extract_topics")
    assert "{{DOMAIN_FRAMEWORK}}" in text


def test_load_brand_doc_reads_file():
    text = ai.load_brand_doc("marianabotelho-ig", "tone-of-voice.md")
    assert "Íntimo-Poético" in text


def test_extract_topics_parses_json_and_reports_usage():
    fake_json = json.dumps([{"topic": "5 plantas para o sono", "pillar": "Educativo Integrativo"}])
    client = make_fake_client(fake_json, tokens_in=500, tokens_out=100)
    topics, tokens_in, tokens_out, cost = ai.extract_topics(client, "um artigo de referência qualquer", "marianabotelho-ig")
    assert topics == [{"topic": "5 plantas para o sono", "pillar": "Educativo Integrativo"}]
    assert tokens_in == 500
    assert tokens_out == 100
    assert cost == pytest.approx(ai.calculate_cost(500, 100))


def test_extract_topics_rejects_reference_over_limit():
    client = make_fake_client("[]")
    with pytest.raises(ai.ReferenceTooLongError):
        ai.extract_topics(client, "palavra " * (ai.MAX_REFERENCE_WORDS + 1), "marianabotelho-ig")


def test_generate_draft_parses_json():
    fake_json = json.dumps({"caption": "legenda", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json)
    draft, tokens_in, tokens_out, cost = ai.generate_draft(
        client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
    )
    assert draft == {"caption": "legenda", "slides": ["s1", "s2"]}


def test_critique_draft_parses_json_array():
    fake_json = json.dumps([{"criterion": "Hashtags", "issue": "só 3 hashtags"}])
    client = make_fake_client(fake_json)
    draft = {"caption": "legenda", "slides": ["s1"]}
    flags, tokens_in, tokens_out, cost = ai.critique_draft(client, draft, "marianabotelho-ig")
    assert flags == [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]


def test_revise_draft_parses_json():
    fake_json = json.dumps({"caption": "legenda corrigida", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json)
    draft = {"caption": "legenda", "slides": ["s1"]}
    flags = [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]
    revised, tokens_in, tokens_out, cost = ai.revise_draft(client, draft, flags, "marianabotelho-ig")
    assert revised == {"caption": "legenda corrigida", "slides": ["s1", "s2"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_ai_functions.py -v`
Expected: FAIL — `AttributeError: module 'ai' has no attribute 'render_prompt'` (and similar for the other missing functions)

- [ ] **Step 3: Add prompt loading, rendering, and the 4 API functions to `ai.py`**

Add near the top of `content-creator/ai.py` (after the existing constants):

```python
import json
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000

PROMPTS_DIR = Path(__file__).parent / "prompts"
BRANDS_DIR = Path(__file__).parent / "brands"


def get_client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def load_prompt(name):
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_brand_doc(brand_pack, filename):
    return (BRANDS_DIR / brand_pack / filename).read_text(encoding="utf-8")


def render_prompt(template, **kwargs):
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace("{{" + key.upper() + "}}", value)
    return rendered


def _call_claude(client, prompt_text, max_tokens=MAX_TOKENS):
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt_text}],
    )
    text = response.content[0].text
    return text, response.usage.input_tokens, response.usage.output_tokens


def extract_topics(client, reference_text, brand_pack):
    validate_reference_length(reference_text)
    prompt = render_prompt(
        load_prompt("extract_topics"),
        domain_framework=load_brand_doc(brand_pack, "domain-framework.md"),
    )
    prompt = f"{prompt}\n\n## Texto de Referência\n{reference_text}"
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    topics = json.loads(text)
    return topics, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def generate_draft(client, topic, tone, pillar, brand_pack):
    prompt = render_prompt(
        load_prompt("generate_draft"),
        domain_framework=load_brand_doc(brand_pack, "domain-framework.md"),
        tone_of_voice=load_brand_doc(brand_pack, "tone-of-voice.md"),
    )
    prompt = f"{prompt}\n\n## Tópico\n{topic}\n\n## Pilar\n{pillar}\n\n## Tom Escolhido\n{tone}"
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    draft = json.loads(text)
    return draft, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def critique_draft(client, draft, brand_pack):
    prompt = render_prompt(
        load_prompt("critique_draft"),
        draft_json=json.dumps(draft, ensure_ascii=False),
        quality_criteria=load_brand_doc(brand_pack, "quality-criteria.md"),
        anti_patterns=load_brand_doc(brand_pack, "anti-patterns.md"),
    )
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    flags = json.loads(text)
    return flags, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def revise_draft(client, draft, flags, brand_pack):
    prompt = render_prompt(
        load_prompt("revise_draft"),
        draft_json=json.dumps(draft, ensure_ascii=False),
        quality_flags=json.dumps(flags, ensure_ascii=False),
    )
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    revised = json.loads(text)
    return revised, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)
```

Note: `render_prompt` upper-cases each kwarg name to match the `{{UPPER_CASE}}` tokens in the templates — e.g. `domain_framework=...` fills `{{DOMAIN_FRAMEWORK}}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_ai_functions.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the full test suite to check nothing broke**

Run: `pytest content-creator/tests/ -v`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add content-creator/ai.py content-creator/tests/test_ai_functions.py
git commit -m "Add Claude API wrapper functions for the 4 pipeline stages"
```

---

### Task 8: Pipeline orchestration — quality loop with budget enforcement

**Files:**
- Create: `content-creator/pipeline.py`
- Test: `content-creator/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `db.would_exceed_daily_cap`, `db.log_api_call`, `db.create_draft`, `db.update_idea_status` from Tasks 3-4; `ai.extract_topics`/`generate_draft`/`critique_draft`/`revise_draft`, `ai.MAX_REVISION_ROUNDS` from Tasks 5-7.
- Produces: `DailyBudgetExceededError`, `run_generation_pipeline(client, conn, idea: dict, tone: str, brand_pack: str, daily_cap_usd: float, ai_module=ai) -> tuple[dict, list[dict], int]` returning `(final_draft, remaining_flags, rounds_run)`. Used by Task 9 (`app.py`).

- [ ] **Step 1: Write the failing tests (AI module mocked, real in-memory SQLite)**

```python
# content-creator/tests/test_pipeline.py
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
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ashwagandha", pillar="Educativo Integrativo")
    return db.get_idea(conn, idea_id)


def make_fake_ai_module(critique_sequence, revised_captions=None):
    """critique_sequence: list of flag-lists returned by successive critique_draft calls."""
    calls = {"critique": 0, "revise": 0}
    revised_captions = revised_captions or []

    def generate_draft(client, topic, tone, pillar, brand_pack):
        return {"caption": "v0", "slides": ["a"]}, 100, 50, 0.01

    def critique_draft(client, draft, brand_pack):
        flags = critique_sequence[calls["critique"]]
        calls["critique"] += 1
        return flags, 80, 20, 0.005

    def revise_draft(client, draft, flags, brand_pack):
        caption = revised_captions[calls["revise"]]
        calls["revise"] += 1
        return {"caption": caption, "slides": ["a"]}, 90, 60, 0.008

    return SimpleNamespace(generate_draft=generate_draft, critique_draft=critique_draft, revise_draft=revise_draft)


def test_stops_immediately_when_no_flags(conn, idea):
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    draft, flags, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert draft["caption"] == "v0"
    assert flags == []
    assert rounds == 0
    assert db.get_idea(conn, idea["id"])["status"] == "reviewed"


def test_revises_once_then_stops_when_clean(conn, idea):
    fake_ai = make_fake_ai_module(
        critique_sequence=[[{"criterion": "Hashtags", "issue": "só 3"}], []],
        revised_captions=["v1"],
    )
    draft, flags, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert draft["caption"] == "v1"
    assert flags == []
    assert rounds == 1


def test_stops_after_max_rounds_even_with_remaining_flags(conn, idea):
    still_failing = [{"criterion": "Hook", "issue": "fraco"}]
    fake_ai = make_fake_ai_module(
        critique_sequence=[still_failing, still_failing, still_failing],
        revised_captions=["v1", "v2"],
    )
    draft, flags, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert rounds == pipeline.ai.MAX_REVISION_ROUNDS
    assert flags == still_failing
    assert draft["caption"] == "v2"


def test_persists_every_round_as_a_draft_row(conn, idea):
    fake_ai = make_fake_ai_module(
        critique_sequence=[[{"criterion": "Hook", "issue": "fraco"}], []],
        revised_captions=["v1"],
    )
    pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    drafts = db.list_drafts_for_idea(conn, idea["id"])
    assert [d["round"] for d in drafts] == [0, 1]
    assert [d["caption"] for d in drafts] == ["v0", "v1"]


def test_raises_when_daily_cap_already_reached(conn, idea):
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.run_generation_pipeline(
            client=None, conn=conn, idea=idea, tone="Educativo-Científico",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest content-creator/tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# content-creator/pipeline.py
import ai
import db

ESTIMATED_MAX_CALL_COST_USD = 0.20


class DailyBudgetExceededError(Exception):
    pass


def _invoke(conn, idea_id, daily_cap_usd, function_name, ai_call):
    if db.would_exceed_daily_cap(conn, ESTIMATED_MAX_CALL_COST_USD, daily_cap_usd):
        raise DailyBudgetExceededError(
            f"This call could push today's spend over the ${daily_cap_usd:.2f} daily cap. "
            "Try again tomorrow or raise MAX_DAILY_SPEND_USD."
        )
    result, tokens_in, tokens_out, cost = ai_call()
    db.log_api_call(conn, function_name, tokens_in, tokens_out, cost, idea_id=idea_id)
    return result


def run_generation_pipeline(client, conn, idea, tone, brand_pack, daily_cap_usd, ai_module=ai):
    idea_id = idea["id"]

    draft = _invoke(
        conn, idea_id, daily_cap_usd, "generate_draft",
        lambda: ai_module.generate_draft(client, idea["topic"], tone, idea["pillar"], brand_pack),
    )
    round_ = 0
    flags = _invoke(
        conn, idea_id, daily_cap_usd, "critique_draft",
        lambda: ai_module.critique_draft(client, draft, brand_pack),
    )
    db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], flags)

    while flags and round_ < ai.MAX_REVISION_ROUNDS:
        round_ += 1
        draft = _invoke(
            conn, idea_id, daily_cap_usd, "revise_draft",
            lambda: ai_module.revise_draft(client, draft, flags, brand_pack),
        )
        flags = _invoke(
            conn, idea_id, daily_cap_usd, "critique_draft",
            lambda: ai_module.critique_draft(client, draft, brand_pack),
        )
        db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], flags)

    db.update_idea_status(conn, idea_id, "reviewed")
    return draft, flags, round_
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest content-creator/tests/test_pipeline.py -v`
Expected: 6 passed

- [ ] **Step 5: Run the full test suite to check nothing broke**

Run: `pytest content-creator/tests/ -v`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add content-creator/pipeline.py content-creator/tests/test_pipeline.py
git commit -m "Add pipeline orchestration: capped quality loop with budget enforcement"
```

---

### Task 9: Streamlit app

**Files:**
- Create: `content-creator/app.py`
- Test: `content-creator/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `config.load_config`, `db.*`, `ai.*`, `pipeline.run_generation_pipeline` from Tasks 1-8.
- Produces: the running UI described in the spec's User Flow section. No new interfaces consumed by later tasks.

- [ ] **Step 1: Write the failing smoke test**

```python
# content-creator/tests/test_app_smoke.py
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_app_loads_without_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest content-creator/tests/test_app_smoke.py -v`
Expected: FAIL — `FileNotFoundError` (app.py doesn't exist yet)

- [ ] **Step 3: Write the implementation**

```python
# content-creator/app.py
import streamlit as st

import ai
import config
import db
import pipeline

st.set_page_config(page_title="Content Creator", layout="wide")

cfg = config.load_config()
conn = db.get_connection(cfg.db_path)
db.init_db(conn)
client = ai.get_client(cfg.api_key)

TONES = [
    "Íntimo-Poético",
    "Educativo-Científico",
    "Provocador-Suave",
    "Narrativo-Pessoal",
    "Ritual-Contemplativo",
    "Urgência-Gentil",
]

st.title(f"Content Creator — {cfg.brand_pack}")

tab_new, tab_library = st.tabs(["Nova Ideia", "Biblioteca"])

with tab_new:
    st.subheader("1. Fonte")
    input_mode = st.radio("Como queres começar?", ["Tópico directo", "Texto de referência"])

    if input_mode == "Tópico directo":
        topic_input = st.text_input("Tópico")
        if st.button("Criar ideia") and topic_input:
            idea_id = db.create_idea(conn, cfg.brand_pack, "manual", topic_input)
            st.success(f"Ideia criada (#{idea_id}).")
    else:
        reference_text = st.text_area("Cola aqui o texto de referência", height=300)
        if st.button("Extrair tópicos") and reference_text:
            try:
                ai.validate_reference_length(reference_text)
            except ai.ReferenceTooLongError as e:
                st.error(str(e))
            else:
                topics, tokens_in, tokens_out, cost = ai.extract_topics(
                    client, reference_text, cfg.brand_pack
                )
                db.log_api_call(conn, "extract_topics", tokens_in, tokens_out, cost)
                st.session_state["candidate_topics"] = topics
                st.session_state["reference_text"] = reference_text

        candidates = st.session_state.get("candidate_topics", [])
        if candidates:
            st.subheader("2. Escolhe os tópicos")
            selected = []
            for i, c in enumerate(candidates):
                if st.checkbox(f"{c['topic']} ({c['pillar']})", key=f"topic_{i}"):
                    selected.append(c)
            if st.button("Criar ideias seleccionadas") and selected:
                created_ids = [
                    db.create_idea(
                        conn, cfg.brand_pack, "reference", c["topic"],
                        reference_text=st.session_state["reference_text"], pillar=c["pillar"],
                    )
                    for c in selected
                ]
                st.success(f"{len(created_ids)} ideia(s) criada(s).")

    st.subheader("3. Gerar rascunho")
    pending = db.list_ideas(conn, brand_pack=cfg.brand_pack, status="idea")
    if pending:
        options = {f"#{i['id']} — {i['topic']}": i for i in pending}
        chosen_label = st.selectbox("Ideia a rascunhar", list(options.keys()))
        tone = st.selectbox("Tom", TONES)
        if st.button("Gerar rascunho"):
            idea = options[chosen_label]
            try:
                draft, flags, rounds = pipeline.run_generation_pipeline(
                    client, conn, idea, tone, cfg.brand_pack, cfg.max_daily_spend_usd,
                )
            except pipeline.DailyBudgetExceededError as e:
                st.error(str(e))
            else:
                st.subheader("Legenda")
                st.write(draft["caption"])
                st.subheader("Slides")
                for i, slide in enumerate(draft["slides"], start=1):
                    st.write(f"**Slide {i}:** {slide}")
                if flags:
                    remaining = ", ".join(f["criterion"] for f in flags)
                    st.warning(f"Pontos ainda não resolvidos após {rounds} ronda(s): {remaining}")
                col1, col2 = st.columns(2)
                if col1.button("Aprovar"):
                    db.update_idea_status(conn, idea["id"], "approved")
                if col2.button("Rejeitar"):
                    db.update_idea_status(conn, idea["id"], "rejected")
    else:
        st.info("Sem ideias pendentes. Cria uma acima.")

with tab_library:
    st.subheader("Biblioteca")
    show_archived = st.checkbox("Mostrar arquivadas")
    ideas = db.list_ideas(conn, brand_pack=cfg.brand_pack, include_archived=show_archived)
    spend_today = db.get_spend_today(conn)
    st.caption(f"Gasto hoje: ${spend_today:.2f} / ${cfg.max_daily_spend_usd:.2f}")
    for idea in ideas:
        with st.expander(f"#{idea['id']} — {idea['topic']} ({idea['status']})"):
            for d in db.list_drafts_for_idea(conn, idea["id"]):
                st.write(f"Ronda {d['round']}: {d['caption'][:120]}...")
            if idea["archived_at"] is None:
                if st.button("Arquivar", key=f"archive_{idea['id']}"):
                    db.archive_idea(conn, idea["id"])
            else:
                if st.button("Eliminar definitivamente", key=f"delete_{idea['id']}"):
                    db.hard_delete_idea(conn, idea["id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest content-creator/tests/test_app_smoke.py -v`
Expected: 1 passed

- [ ] **Step 5: Manually run the app and click through the flow once**

Run: `cd content-creator && streamlit run app.py`
Expected: browser opens; type a topic in "Tópico directo," click "Criar ideia," see it appear once you generate a draft. This step needs a real `ANTHROPIC_API_KEY` in `.env` and will spend a small amount of real money — expected and fine, this is the deliberate first end-to-end check the spec calls for.

- [ ] **Step 6: Commit**

```bash
git add content-creator/app.py content-creator/tests/test_app_smoke.py
git commit -m "Add Streamlit UI wiring the full idea-to-draft flow"
```

---

### Task 10: Distribution — dependencies, env template, launcher

**Files:**
- Create: `content-creator/requirements.txt`
- Create: `content-creator/.env.example`
- Create: `content-creator/run.bat`
- Create: `content-creator/.gitignore`

**Interfaces:**
- None — this is the final packaging task, consumed by nobody, just makes the app runnable by double-click per the spec's Distribution section.

- [ ] **Step 1: Write `requirements.txt`**

```
streamlit>=1.38
anthropic>=0.34
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: Write `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
DB_PATH=C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db
MAX_DAILY_SPEND_USD=2.0
BRAND_PACK=marianabotelho-ig
```

- [ ] **Step 3: Write `run.bat`**

```bat
@echo off
cd /d "%~dp0"
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
streamlit run app.py
pause
```

- [ ] **Step 4: Write `.gitignore` so secrets and local state never get committed**

```
.env
venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: Verify `.env` is not tracked**

Run: `git status`
Expected: `.env.example` shows as untracked/new, but there is no actual `.env` file in the repo (it must be created locally by the user, never committed).

- [ ] **Step 6: Commit**

```bash
git add content-creator/requirements.txt content-creator/.env.example content-creator/run.bat content-creator/.gitignore
git commit -m "Add dependencies, env template, launcher script, and gitignore"
```

---

## Self-Review Notes

- **Spec coverage:** brand pack (Task 1), config (Task 2), ideas/drafts/api_calls schema (Tasks 3-4), reference-length + cost pure functions (Task 5), prompt prototyping (Task 6), the 4 AI functions (Task 7), the capped generate→critique→revise loop with budget enforcement (Task 8), the Streamlit UI covering the full user flow (Task 9), and distribution packaging (Task 10) — every section of the spec maps to a task. Image generation, auto-publishing, and a TypeScript rewrite are explicitly out of scope per the spec and have no task here.
- **Type/interface consistency:** `ai.py`'s 4 functions all return the same `(result, tokens_in, tokens_out, cost)` shape, which `pipeline._invoke` relies on uniformly. `db.list_drafts_for_idea` and `db.create_draft` agree on `slides` being a plain list and `quality_flags` being a plain list of dicts (JSON handled inside `db.py`, never leaking raw JSON strings to callers). `pipeline.run_generation_pipeline`'s `ai_module` parameter is duck-typed against `ai`'s public function names, which the `make_fake_ai_module` test helper mirrors exactly.
