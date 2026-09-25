# Strategy Coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Strategy Coach: three gentle questions → automated research (Sherlock) → a ranked, plain-language strategy the user refines and accepts.

**Architecture:** Flat modules at the `content-creator/` root, matching the codebase (`ai.py`, `pipeline.py`). Persistent state in SQLite via a new `coach_store.py` (its own `init_schema(conn)`, called from `app.py`). AI calls reuse `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost` and are wrapped by `pipeline._invoke` (spend-cap check + cost logging). Sherlock lives in a `sherlock/` package with one gather function per source type, a chain that picks the right one, and a distiller that returns a short findings brief.

**Tech Stack:** Python, Streamlit, Anthropic SDK (`claude-sonnet-5`), SQLite, pytest + `unittest.mock`, stdlib `urllib`/`html.parser`, `yt-dlp` (CLI, video metadata), optional `whisper`.

**Spec:** `content-creator/docs/superpowers/specs/2026-09-25-strategy-coach-design.md`

**Feature branch:** `strategy-coach` (create from `main`; tickets branch off it as `ticket-<issue-number>`).

**Test command (run from `content-creator/`):** `python -m pytest tests -q`

## Global Constraints

- All user-facing text and all AI-generated text is **PT-PT**.
- **Gentle tone everywhere**: no urgency, no "critical", no blame. Gaps are framed as friendly invitations. Every AI prompt that writes user-facing feedback includes `tone_guard.GENTLE_TONE_RULE`.
- Every AI-calling function is invoked through `pipeline._invoke` (checks `db.would_exceed_daily_cap`, logs real cost with `db.log_api_call`).
- Engine code contains no brand-specific text; niche/brand knowledge comes from the user's answers and `brands/<pack>/`.
- One brand pack = one Instagram profile (multi-profile is in the backlog).
- Never copy competitor content: Sherlock extracts abstract patterns (hook, CTA, structure), never verbatim text.
- Free sources only in v1: website fetch, Instagram Business Discovery, yt-dlp/whisper, guided upload. The dummy-account crawl and paid scrapers are out of scope (backlog).
- Tests never call real networks or the real Anthropic API. One real, paid end-to-end run happens after the last task (see final checklist).
- Do not touch `db.py`'s existing tables; new tables live in `coach_store.py`.

---

### Task 1: Tone guard

**Files:**
- Create: `content-creator/tone_guard.py`
- Test: `content-creator/tests/test_tone_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tone_guard.GENTLE_TONE_RULE: str` (PT-PT prompt fragment) and `tone_guard.find_harsh_words(text: str) -> list[str]` (sorted, lower-case, unique).

- [ ] **Step 1: Write the failing tests**

```python
import tone_guard


def test_find_harsh_words_flags_urgent_and_critical():
    assert tone_guard.find_harsh_words("Isto é CRÍTICO e urgente!") == ["crítico", "urgente"]


def test_find_harsh_words_is_empty_for_gentle_text():
    assert tone_guard.find_harsh_words("Quando te apetecer, aqui fica uma ideia leve.") == []


def test_find_harsh_words_ignores_partial_words():
    assert tone_guard.find_harsh_words("Uma ideia urgentemente bonita") == []


def test_gentle_tone_rule_is_itself_gentle_and_mentions_pt_pt():
    assert "PT-PT" in tone_guard.GENTLE_TONE_RULE
    # The rule quotes the banned words as examples of what NOT to write, so it is exempt from the check.
    assert "gentil" in tone_guard.GENTLE_TONE_RULE
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tone_guard.py -v`
Expected: FAIL (`ModuleNotFoundError: tone_guard`).

- [ ] **Step 3: Implement**

```python
import re

GENTLE_TONE_RULE = (
    "Tom obrigatório: gentil, acolhedor e encorajador. Nunca uses urgência, alarme, culpa ou "
    "linguagem crítica (por exemplo 'crítico', 'urgente', 'falhaste'). Apresenta lacunas como "
    "convites simpáticos, por exemplo 'quando te apetecer, aqui fica uma ideia leve para "
    "retomares'. Escreve em Português Europeu (PT-PT)."
)

HARSH_WORDS = (
    "crítico", "crítica", "críticos", "críticas", "urgente", "urgentes", "urgência",
    "alerta", "falhaste", "erro teu", "erro seu", "desleixo", "desleixado", "desleixada",
    "atrasado", "atrasada", "grave", "inaceitável",
)

_HARSH_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(w) for w in HARSH_WORDS) + r")(?!\w)", re.IGNORECASE
)


def find_harsh_words(text):
    return sorted({m.group(1).lower() for m in _HARSH_RE.finditer(text or "")})
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_tone_guard.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/tone_guard.py content-creator/tests/test_tone_guard.py
git commit -m "feat: add tone guard (gentle-tone rule + harsh-word check)"
```

---

### Task 2: Coach store (schema and CRUD)

**Files:**
- Create: `content-creator/coach_store.py`
- Test: `content-creator/tests/test_coach_store.py`

**Interfaces:**
- Consumes: nothing (uses a `sqlite3.Connection` from `db.get_connection`).
- Produces: `coach_store.SECTION_KINDS = ("goals","offers","funnel","pillars","authority","rhythm")`
  - `coach_store.init_schema(conn) -> None`
  - `coach_store.create_strategy(conn, brand_pack, profile=None) -> int` (version = previous max + 1)
  - `coach_store.get_strategy(conn, strategy_id) -> dict | None` (keys: id, brand_pack, version, status, profile, created_at, accepted_at)
  - `coach_store.latest_strategy(conn, brand_pack, status=None) -> dict | None`
  - `coach_store.set_section(conn, strategy_id, kind, content, state="draft", evidence="reasoned") -> None` (upsert; `content` is a JSON-serialisable dict)
  - `coach_store.get_sections(conn, strategy_id) -> dict[str, dict]` (each value: `{"content", "state", "evidence"}`)
  - `coach_store.set_section_state(conn, strategy_id, kind, state) -> None`
  - `coach_store.log_decision(conn, strategy_id, section_kind, action, user_reason=None) -> None`
  - `coach_store.list_decisions(conn, strategy_id, limit=None) -> list[dict]` (oldest first; with `limit`, the most recent N)
  - `coach_store.mark_accepted(conn, strategy_id) -> None`
  - `coach_store.save_finding(conn, brand_pack, source_ref, method, brief_text, patterns) -> int`
  - `coach_store.list_findings(conn, brand_pack) -> list[dict]` (keys: id, source_ref, method, brief_text, patterns, fetched_at)
  - `coach_store.add_turn(conn, strategy_id, role, text) -> None`, `coach_store.list_turns(conn, strategy_id) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import coach_store
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    coach_store.init_schema(connection)
    return connection


def test_create_strategy_increments_version_per_brand(conn):
    first = coach_store.create_strategy(conn, "brand-a", profile={"who": "terapeuta"})
    second = coach_store.create_strategy(conn, "brand-a")
    other = coach_store.create_strategy(conn, "brand-b")
    assert coach_store.get_strategy(conn, first)["version"] == 1
    assert coach_store.get_strategy(conn, second)["version"] == 2
    assert coach_store.get_strategy(conn, other)["version"] == 1
    assert coach_store.get_strategy(conn, first)["profile"] == {"who": "terapeuta"}


def test_set_section_upserts_and_roundtrips_json(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    coach_store.set_section(conn, sid, "pillars", {"items": [1, 2]})
    coach_store.set_section(conn, sid, "pillars", {"items": [3]}, state="accepted", evidence="data")
    sections = coach_store.get_sections(conn, sid)
    assert sections["pillars"] == {"content": {"items": [3]}, "state": "accepted", "evidence": "data"}


def test_set_section_rejects_unknown_kind_and_state(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    with pytest.raises(ValueError):
        coach_store.set_section(conn, sid, "nonsense", {})
    with pytest.raises(ValueError):
        coach_store.set_section(conn, sid, "goals", {}, state="weird")


def test_decisions_are_chronological_and_limitable(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    for i in range(5):
        coach_store.log_decision(conn, sid, "offers", "edit", f"motivo {i}")
    all_ = coach_store.list_decisions(conn, sid)
    assert [d["user_reason"] for d in all_] == [f"motivo {i}" for i in range(5)]
    last_two = coach_store.list_decisions(conn, sid, limit=2)
    assert [d["user_reason"] for d in last_two] == ["motivo 3", "motivo 4"]


def test_mark_accepted_sets_status_and_latest_strategy_filters(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    assert coach_store.latest_strategy(conn, "brand-a", status="accepted") is None
    coach_store.mark_accepted(conn, sid)
    latest = coach_store.latest_strategy(conn, "brand-a", status="accepted")
    assert latest["id"] == sid and latest["accepted_at"] is not None


def test_findings_roundtrip(conn):
    coach_store.save_finding(conn, "brand-a", "https://x.pt", "website", "resumo", [{"type": "hook", "description": "pergunta"}])
    findings = coach_store.list_findings(conn, "brand-a")
    assert findings[0]["brief_text"] == "resumo"
    assert findings[0]["patterns"] == [{"type": "hook", "description": "pergunta"}]
    assert coach_store.list_findings(conn, "brand-b") == []


def test_turns_roundtrip(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    coach_store.add_turn(conn, sid, "user", "olá")
    coach_store.add_turn(conn, sid, "coach", "olá!")
    assert [t["role"] for t in coach_store.list_turns(conn, sid)] == ["user", "coach"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_coach_store.py -v`
Expected: FAIL (`ModuleNotFoundError: coach_store`).

- [ ] **Step 3: Implement**

```python
import json
from datetime import datetime, timezone

SECTION_KINDS = ("goals", "offers", "funnel", "pillars", "authority", "rhythm")
SECTION_STATES = ("draft", "accepted", "revisit")


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            profile_json TEXT,
            created_at TEXT NOT NULL,
            accepted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS strategy_sections (
            strategy_id INTEGER NOT NULL REFERENCES strategies(id),
            kind TEXT NOT NULL,
            content_json TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'draft',
            evidence TEXT NOT NULL DEFAULT 'reasoned',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (strategy_id, kind)
        );
        CREATE TABLE IF NOT EXISTS strategy_decisions (
            id INTEGER PRIMARY KEY,
            strategy_id INTEGER NOT NULL REFERENCES strategies(id),
            section_kind TEXT NOT NULL,
            action TEXT NOT NULL,
            user_reason TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_findings (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            method TEXT NOT NULL,
            brief_text TEXT NOT NULL,
            patterns_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coach_turns (
            id INTEGER PRIMARY KEY,
            strategy_id INTEGER NOT NULL REFERENCES strategies(id),
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def create_strategy(conn, brand_pack, profile=None):
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM strategies WHERE brand_pack = ?", (brand_pack,)
    ).fetchone()
    cursor = conn.execute(
        "INSERT INTO strategies (brand_pack, version, status, profile_json, created_at) "
        "VALUES (?, ?, 'draft', ?, ?)",
        (brand_pack, row["v"] + 1, json.dumps(profile) if profile is not None else None, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def _strategy_row(row):
    if row is None:
        return None
    data = dict(row)
    data["profile"] = json.loads(data.pop("profile_json")) if data.get("profile_json") else None
    return data


def get_strategy(conn, strategy_id):
    row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return _strategy_row(row)


def latest_strategy(conn, brand_pack, status=None):
    query = "SELECT * FROM strategies WHERE brand_pack = ?"
    params = [brand_pack]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY version DESC LIMIT 1"
    return _strategy_row(conn.execute(query, params).fetchone())


def set_section(conn, strategy_id, kind, content, state="draft", evidence="reasoned"):
    if kind not in SECTION_KINDS:
        raise ValueError(f"Unknown section kind: {kind}")
    if state not in SECTION_STATES:
        raise ValueError(f"Unknown section state: {state}")
    conn.execute(
        "INSERT INTO strategy_sections (strategy_id, kind, content_json, state, evidence, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(strategy_id, kind) DO UPDATE SET "
        "content_json = excluded.content_json, state = excluded.state, "
        "evidence = excluded.evidence, updated_at = excluded.updated_at",
        (strategy_id, kind, json.dumps(content, ensure_ascii=False), state, evidence, _now()),
    )
    conn.commit()


def get_sections(conn, strategy_id):
    rows = conn.execute(
        "SELECT kind, content_json, state, evidence FROM strategy_sections WHERE strategy_id = ?",
        (strategy_id,),
    ).fetchall()
    return {
        r["kind"]: {"content": json.loads(r["content_json"]), "state": r["state"], "evidence": r["evidence"]}
        for r in rows
    }


def set_section_state(conn, strategy_id, kind, state):
    if state not in SECTION_STATES:
        raise ValueError(f"Unknown section state: {state}")
    conn.execute(
        "UPDATE strategy_sections SET state = ?, updated_at = ? WHERE strategy_id = ? AND kind = ?",
        (state, _now(), strategy_id, kind),
    )
    conn.commit()


def log_decision(conn, strategy_id, section_kind, action, user_reason=None):
    conn.execute(
        "INSERT INTO strategy_decisions (strategy_id, section_kind, action, user_reason, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (strategy_id, section_kind, action, user_reason, _now()),
    )
    conn.commit()


def list_decisions(conn, strategy_id, limit=None):
    if limit is None:
        rows = conn.execute(
            "SELECT * FROM strategy_decisions WHERE strategy_id = ? ORDER BY id", (strategy_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM strategy_decisions WHERE strategy_id = ? ORDER BY id DESC LIMIT ?) "
            "ORDER BY id",
            (strategy_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_accepted(conn, strategy_id):
    conn.execute(
        "UPDATE strategies SET status = 'accepted', accepted_at = ? WHERE id = ?", (_now(), strategy_id)
    )
    conn.commit()


def save_finding(conn, brand_pack, source_ref, method, brief_text, patterns):
    cursor = conn.execute(
        "INSERT INTO research_findings (brand_pack, source_ref, method, brief_text, patterns_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (brand_pack, source_ref, method, brief_text, json.dumps(patterns, ensure_ascii=False), _now()),
    )
    conn.commit()
    return cursor.lastrowid


def list_findings(conn, brand_pack):
    rows = conn.execute(
        "SELECT * FROM research_findings WHERE brand_pack = ? ORDER BY id", (brand_pack,)
    ).fetchall()
    findings = []
    for r in rows:
        item = dict(r)
        item["patterns"] = json.loads(item.pop("patterns_json"))
        findings.append(item)
    return findings


def add_turn(conn, strategy_id, role, text):
    conn.execute(
        "INSERT INTO coach_turns (strategy_id, role, text, created_at) VALUES (?, ?, ?, ?)",
        (strategy_id, role, text, _now()),
    )
    conn.commit()


def list_turns(conn, strategy_id):
    rows = conn.execute(
        "SELECT * FROM coach_turns WHERE strategy_id = ? ORDER BY id", (strategy_id,)
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_coach_store.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/coach_store.py content-creator/tests/test_coach_store.py
git commit -m "feat: add coach_store (strategies, sections, decisions, findings, turns)"
```

---

### Task 3: Sherlock models and website gather

**Files:**
- Create: `content-creator/sherlock/__init__.py` (empty), `content-creator/sherlock/models.py`, `content-creator/sherlock/gather.py`
- Test: `content-creator/tests/test_sherlock_website.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sherlock.models.GatherResult(source: str, method: str, text: str)` (dataclass)
  - `sherlock.models.NeedsUpload(source: str, reason: str, instructions: str)` (dataclass)
  - `sherlock.models.detect_platform(source: str) -> str` (one of `"website"`, `"instagram"`, `"tiktok"`, `"youtube"`, `"text"`)
  - `sherlock.models.instagram_username(source: str) -> str | None`
  - `sherlock.models.upload_instructions(kind: str) -> str` (PT-PT, gentle; kinds `"website"`, `"instagram"`, `"tiktok"`, `"youtube"`, `"other"`; unknown kind → the `"other"` text)
  - `sherlock.gather.gather_website(url: str, fetch=<default urllib fetch>) -> GatherResult | NeedsUpload`

- [ ] **Step 1: Write the failing tests**

```python
from sherlock import gather, models


def test_detect_platform():
    assert models.detect_platform("https://www.instagram.com/mariana/") == "instagram"
    assert models.detect_platform("@mariana") == "instagram"
    assert models.detect_platform("https://www.tiktok.com/@x") == "tiktok"
    assert models.detect_platform("https://youtu.be/abc") == "youtube"
    assert models.detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert models.detect_platform("https://exemplo.pt/blog") == "website"
    assert models.detect_platform("um texto colado com várias palavras") == "text"


def test_instagram_username_from_url_and_handle():
    assert models.instagram_username("https://www.instagram.com/mariana.botelho/") == "mariana.botelho"
    assert models.instagram_username("@mariana.botelho") == "mariana.botelho"
    assert models.instagram_username("https://exemplo.pt") is None


def test_upload_instructions_mention_alt_text_for_instagram_and_are_gentle():
    from tone_guard import find_harsh_words

    text = models.upload_instructions("instagram")
    assert "descrição" in text.lower() or "alt" in text.lower()
    assert find_harsh_words(text) == []
    assert models.upload_instructions("qualquer-coisa") == models.upload_instructions("other")


def test_gather_website_extracts_visible_text_and_image_alt():
    html = (
        "<html><head><style>x{}</style><script>bad()</script></head><body>"
        "<h1>Olá mundo</h1><p>" + ("Texto útil de exemplo. " * 20) + "</p>"
        "<img src='a.png' alt='Uma mulher a meditar'></body></html>"
    )
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: html)
    assert isinstance(result, models.GatherResult)
    assert result.method == "website"
    assert "Olá mundo" in result.text
    assert "Uma mulher a meditar" in result.text
    assert "bad()" not in result.text


def test_gather_website_returns_needs_upload_on_fetch_error():
    def boom(url):
        raise OSError("bloqueado")

    result = gather.gather_website("https://exemplo.pt", fetch=boom)
    assert isinstance(result, models.NeedsUpload)
    assert "bloqueado" in result.reason
    assert result.instructions


def test_gather_website_returns_needs_upload_when_page_has_almost_no_text():
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: "<html><body>oi</body></html>")
    assert isinstance(result, models.NeedsUpload)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sherlock_website.py -v`
Expected: FAIL (`ModuleNotFoundError: sherlock`).

- [ ] **Step 3: Implement `sherlock/models.py`**

```python
import re
from dataclasses import dataclass


@dataclass
class GatherResult:
    source: str
    method: str
    text: str


@dataclass
class NeedsUpload:
    source: str
    reason: str
    instructions: str


_UPLOAD_INSTRUCTIONS = {
    "instagram": (
        "Não consegui ler este perfil automaticamente, mas podemos avançar juntos. "
        "Se quiseres, envia-me uma destas opções: (1) um PDF do perfil (no telemóvel, "
        "imprime a página do perfil e guarda como PDF); (2) capturas de ecrã dos posts mais "
        "recentes; (3) as legendas coladas em texto. Se puderes, inclui também a descrição "
        "das fotos (o texto alternativo), porque costuma trazer informação útil."
    ),
    "tiktok": (
        "Não consegui ler este perfil automaticamente, sem problema. Podes enviar capturas de "
        "ecrã dos vídeos mais recentes ou colar as descrições e o texto que aparece nos vídeos."
    ),
    "youtube": (
        "Não consegui ler este vídeo automaticamente. Podes colar o título, a descrição e, se "
        "tiveres, a transcrição (no YouTube: três pontos por baixo do vídeo, 'Mostrar transcrição')."
    ),
    "website": (
        "Não consegui abrir esta página automaticamente. Podes colar o texto principal da página "
        "ou enviar capturas de ecrã ou um PDF (no navegador: imprimir, guardar como PDF)."
    ),
    "other": (
        "Não consegui ler esta fonte automaticamente. Podes colar o texto, enviar capturas de "
        "ecrã ou um PDF, e eu aproveito o que lá estiver."
    ),
}


def upload_instructions(kind):
    return _UPLOAD_INSTRUCTIONS.get(kind, _UPLOAD_INSTRUCTIONS["other"])


def detect_platform(source):
    s = source.strip().lower()
    if "instagram.com" in s or (s.startswith("@") and " " not in s):
        return "instagram"
    if "tiktok.com" in s:
        return "tiktok"
    if "youtube.com" in s or "youtu.be" in s:
        return "youtube"
    if re.match(r"^(https?://|www\.)\S+$", s):
        return "website"
    return "text"


_IG_URL_RE = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.IGNORECASE)


def instagram_username(source):
    s = source.strip()
    if s.startswith("@"):
        return s[1:] or None
    m = _IG_URL_RE.search(s)
    if m and m.group(1).lower() not in {"p", "reel", "reels", "stories", "explore"}:
        return m.group(1)
    return None
```

- [ ] **Step 4: Implement `sherlock/gather.py`**

```python
import urllib.request
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, upload_instructions

MAX_CHARS = 20000
MIN_CHARS = 200


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f"[imagem: {alt}]")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def _http_fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ContentCreator/1.0)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def gather_website(url, fetch=_http_fetch):
    try:
        html = fetch(url)
    except Exception as e:  # network errors, HTTP errors, timeouts: all mean "ask for an upload"
        return NeedsUpload(url, str(e), upload_instructions("website"))
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        return NeedsUpload(url, "A página quase não tem texto legível.", upload_instructions("website"))
    return GatherResult(url, "website", text)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_sherlock_website.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/sherlock content-creator/tests/test_sherlock_website.py
git commit -m "feat: add Sherlock models, platform detection and website gather"
```

---

### Task 4: Sherlock video gather (yt-dlp, optional whisper)

**Files:**
- Modify: `content-creator/sherlock/gather.py` (append), `content-creator/requirements.txt` (add `yt-dlp>=2024.8`)
- Test: `content-creator/tests/test_sherlock_video.py`

**Interfaces:**
- Consumes: `GatherResult`, `NeedsUpload`, `detect_platform`, `upload_instructions` from `sherlock.models` (Task 3).
- Produces: `sherlock.gather.gather_video(url: str, run=subprocess.run, transcribe=None) -> GatherResult | NeedsUpload` and `sherlock.gather.whisper_transcribe(url: str, run=subprocess.run) -> str | None` (returns `None` when whisper/ffmpeg are not installed).

- [ ] **Step 1: Write the failing tests**

```python
import json
from types import SimpleNamespace

from sherlock import gather, models


def fake_run_ok(info):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(info), stderr="")
    return run


def test_gather_video_builds_text_from_metadata():
    info = {"title": "3 hábitos", "description": "Descrição do vídeo", "uploader": "Ana",
            "view_count": 1200, "like_count": 90, "comment_count": 5, "tags": ["saúde", "rotina"]}
    result = gather.gather_video("https://www.tiktok.com/@a/video/1", run=fake_run_ok(info))
    assert isinstance(result, models.GatherResult)
    assert result.method == "yt-dlp"
    assert "3 hábitos" in result.text and "Descrição do vídeo" in result.text
    assert "1200" in result.text and "saúde" in result.text


def test_gather_video_appends_transcript_when_available():
    info = {"title": "T", "description": "D"}
    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok(info), transcribe=lambda url: "olá a todos")
    assert result.method == "yt-dlp+whisper"
    assert "olá a todos" in result.text


def test_gather_video_returns_needs_upload_when_ytdlp_fails():
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: bloqueado")

    result = gather.gather_video("https://www.tiktok.com/@a", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert "bloqueado" in result.reason


def test_gather_video_returns_needs_upload_when_ytdlp_missing():
    def run(cmd, **kwargs):
        raise FileNotFoundError("yt-dlp")

    result = gather.gather_video("https://youtu.be/x", run=run)
    assert isinstance(result, models.NeedsUpload)


def test_whisper_transcribe_returns_none_when_whisper_not_installed(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError("no whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert gather.whisper_transcribe("https://youtu.be/x") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sherlock_video.py -v`
Expected: FAIL (`AttributeError: module 'sherlock.gather' has no attribute 'gather_video'`).

- [ ] **Step 3: Implement (append to `sherlock/gather.py`; add `import json, subprocess, tempfile` and `from sherlock.models import detect_platform` at the top)**

```python
def _video_text(info):
    lines = [
        f"Título: {info.get('title', '')}",
        f"Autor: {info.get('uploader', '')}",
        f"Descrição: {info.get('description', '')}",
    ]
    for label, key in (("Visualizações", "view_count"), ("Gostos", "like_count"), ("Comentários", "comment_count")):
        if info.get(key) is not None:
            lines.append(f"{label}: {info[key]}")
    if info.get("tags"):
        lines.append("Etiquetas: " + ", ".join(info["tags"]))
    return "\n".join(lines)


def gather_video(url, run=subprocess.run, transcribe=None):
    kind = detect_platform(url)
    try:
        proc = run(["yt-dlp", "--dump-single-json", "--skip-download", url], capture_output=True, text=True)
    except FileNotFoundError:
        return NeedsUpload(url, "O yt-dlp não está instalado.", upload_instructions(kind))
    if proc.returncode != 0:
        reason = (proc.stderr or "").strip()[:200] or "O yt-dlp não conseguiu ler este vídeo."
        return NeedsUpload(url, reason, upload_instructions(kind))
    text = _video_text(json.loads(proc.stdout))
    method = "yt-dlp"
    transcript = transcribe(url) if transcribe else None
    if transcript:
        text += f"\n\nTranscrição:\n{transcript}"
        method = "yt-dlp+whisper"
    return GatherResult(url, method, text[:MAX_CHARS])


def whisper_transcribe(url, run=subprocess.run):
    """Best-effort transcript via yt-dlp audio download + openai-whisper. Returns None if
    whisper or ffmpeg are unavailable or anything fails: the transcript is a bonus."""
    try:
        import whisper  # noqa: WPS433 (optional heavy dependency, imported lazily)
    except ImportError:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                ["yt-dlp", "-x", "--audio-format", "mp3", "-o", f"{tmp}/audio.%(ext)s", url],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                return None
            model = whisper.load_model("base")
            return model.transcribe(f"{tmp}/audio.mp3").get("text", "").strip() or None
    except Exception:
        return None
```

- [ ] **Step 4: Add the dependency**

Append `yt-dlp>=2024.8` to `content-creator/requirements.txt`. (`openai-whisper` is deliberately not added: it is a heavy optional extra; document it in a comment line `# optional: openai-whisper (video transcripts)` in the same file.)

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_sherlock_video.py tests/test_sherlock_website.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add content-creator/sherlock/gather.py content-creator/requirements.txt content-creator/tests/test_sherlock_video.py
git commit -m "feat: add Sherlock video gather via yt-dlp with optional whisper transcript"
```

---

### Task 5: Sherlock Instagram Business Discovery gather

**Files:**
- Modify: `content-creator/sherlock/gather.py` (append), `content-creator/.env.example` (append two commented variables)
- Test: `content-creator/tests/test_sherlock_instagram.py`

**Interfaces:**
- Consumes: `GatherResult`, `NeedsUpload`, `instagram_username`, `upload_instructions` (Task 3); serialised after the video gather (Task 4) because both edit `sherlock/gather.py`.
- Produces: `sherlock.gather.gather_instagram_discovery(source: str, ig_user_id: str | None, access_token: str | None, get_json=<default urllib GET>) -> GatherResult | NeedsUpload`. When `ig_user_id`/`access_token` are missing or the username can't be parsed, returns `NeedsUpload` (kindly explaining that the connection is optional).

- [ ] **Step 1: Verify the API shape against current docs**

Before coding, open Meta's current "Instagram Graph API — Business Discovery" docs and confirm: endpoint `GET https://graph.facebook.com/{version}/{ig-user-id}?fields=business_discovery.username({username}){followers_count,media_count,media{caption,like_count,comments_count,media_type,timestamp,permalink}}&access_token=...`, its rate limits, and that only Business/Creator accounts are readable. If anything differs, adjust `_DISCOVERY_FIELDS` and the parsing below, and note the difference in the commit message.

- [ ] **Step 2: Write the failing tests**

```python
from sherlock import gather, models

DISCOVERY = {
    "business_discovery": {
        "username": "outra",
        "followers_count": 5400,
        "media_count": 120,
        "media": {"data": [
            {"caption": "Como dormir melhor", "like_count": 300, "comments_count": 12,
             "media_type": "CAROUSEL_ALBUM", "timestamp": "2026-08-01T10:00:00+0000"},
            {"caption": "Bastidores do dia", "like_count": 80, "comments_count": 2,
             "media_type": "IMAGE", "timestamp": "2026-08-03T10:00:00+0000"},
        ]},
    }
}


def test_discovery_builds_text_from_captions_and_metrics():
    seen = {}

    def get_json(url):
        seen["url"] = url
        return DISCOVERY

    result = gather.gather_instagram_discovery("@outra", "1789", "tok", get_json=get_json)
    assert isinstance(result, models.GatherResult)
    assert result.method == "instagram-business-discovery"
    assert "Como dormir melhor" in result.text and "5400" in result.text
    assert "outra" in seen["url"] and "access_token=tok" in seen["url"]


def test_discovery_needs_upload_without_credentials():
    result = gather.gather_instagram_discovery("@outra", None, None, get_json=lambda u: DISCOVERY)
    assert isinstance(result, models.NeedsUpload)


def test_discovery_needs_upload_when_username_cannot_be_parsed():
    result = gather.gather_instagram_discovery("https://exemplo.pt", "1", "t", get_json=lambda u: DISCOVERY)
    assert isinstance(result, models.NeedsUpload)


def test_discovery_needs_upload_on_api_error():
    def boom(url):
        raise OSError("400 Bad Request")

    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=boom)
    assert isinstance(result, models.NeedsUpload)
    assert "400" in result.reason
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_sherlock_instagram.py -v`
Expected: FAIL (no attribute `gather_instagram_discovery`).

- [ ] **Step 4: Implement (append to `sherlock/gather.py`; add `import urllib.parse` and `from sherlock.models import instagram_username` at the top)**

```python
GRAPH_VERSION = "v21.0"
_DISCOVERY_FIELDS = (
    "business_discovery.username({username})"
    "{{followers_count,media_count,media{{caption,like_count,comments_count,media_type,timestamp,permalink}}}}"
)


def _http_get_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def gather_instagram_discovery(source, ig_user_id, access_token, get_json=_http_get_json):
    username = instagram_username(source)
    if not (username and ig_user_id and access_token):
        return NeedsUpload(
            source,
            "A ligação opcional ao Instagram (Business Discovery) não está configurada.",
            upload_instructions("instagram"),
        )
    fields = _DISCOVERY_FIELDS.format(username=username)
    url = (
        f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}"
        f"?fields={urllib.parse.quote(fields, safe='(){},')}&access_token={access_token}"
    )
    try:
        data = get_json(url)["business_discovery"]
    except Exception as e:
        return NeedsUpload(source, str(e), upload_instructions("instagram"))
    lines = [
        f"Perfil: @{data.get('username', username)}",
        f"Seguidores: {data.get('followers_count', '?')}  Publicações: {data.get('media_count', '?')}",
    ]
    for post in data.get("media", {}).get("data", []):
        lines.append(
            f"- [{post.get('media_type', '')}] {post.get('timestamp', '')[:10]} "
            f"gostos={post.get('like_count', '?')} comentários={post.get('comments_count', '?')}: "
            f"{post.get('caption', '')}"
        )
    return GatherResult(source, "instagram-business-discovery", "\n".join(lines)[:MAX_CHARS])
```

- [ ] **Step 5: Document the optional env vars**

Append to `.env.example`:

```
# Optional: Instagram Business Discovery for Sherlock (reads other Business/Creator accounts' public posts)
# IG_ACCESS_TOKEN=
# IG_BUSINESS_ACCOUNT_ID=
```

- [ ] **Step 6: Run to verify pass**

Run: `python -m pytest tests/test_sherlock_instagram.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add content-creator/sherlock/gather.py content-creator/.env.example content-creator/tests/test_sherlock_instagram.py
git commit -m "feat: add Sherlock Instagram Business Discovery gather"
```

---

### Task 6: Sherlock guided upload (pasted text, images, PDFs)

**Files:**
- Create: `content-creator/sherlock/upload.py`, `content-creator/prompts/sherlock_extract_upload.md`
- Test: `content-creator/tests/test_sherlock_upload.py`

**Interfaces:**
- Consumes: `GatherResult` (Task 3), `ai.MODEL`, `ai.MAX_TOKENS`, `ai.calculate_cost`, `ai.load_prompt`.
- Produces: `sherlock.upload.gather_uploaded(client, source_label: str, pasted_text: str = "", files=()) -> tuple[GatherResult, int, int, float]`. `files` is a sequence of `(name, bytes, media_type)`. With only pasted text there is no AI call (tokens 0, cost 0.0). Raises `ValueError` when there is neither text nor files. The 4-tuple matches what `pipeline._invoke` expects.

- [ ] **Step 1: Create the prompt file `prompts/sherlock_extract_upload.md`**

```
Vais receber imagens, PDFs ou texto de um perfil ou página de redes sociais. Transcreve, em texto simples e em Português Europeu (PT-PT), tudo o que for visível e útil: legendas, texto nos slides, descrições das fotos (texto alternativo), métricas visíveis (gostos, comentários, visualizações), datas e a estrutura de cada publicação.

Não resumas nem interpretes: apenas transcreve. Não inventes nada que não esteja visível.
```

- [ ] **Step 2: Write the failing tests**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sherlock import models, upload


def make_client(text="texto extraído"):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        stop_reason="end_turn",
    )
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def test_pasted_text_only_makes_no_ai_call():
    client = make_client()
    result, tin, tout, cost = upload.gather_uploaded(client, "perfil x", pasted_text="  legenda colada  ")
    assert result == models.GatherResult("perfil x", "upload", "legenda colada")
    assert (tin, tout, cost) == (0, 0, 0.0)
    client.messages.create.assert_not_called()


def test_images_and_pdfs_are_sent_as_content_blocks():
    client = make_client("legendas extraídas")
    files = [("a.png", b"\x89PNG", "image/png"), ("p.pdf", b"%PDF", "application/pdf")]
    result, tin, tout, cost = upload.gather_uploaded(client, "perfil x", pasted_text="extra", files=files)
    blocks = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["image", "document", "text"]
    assert "extra" in blocks[-1]["text"]
    assert result.text == "legendas extraídas" and result.method == "upload"
    assert tin == 100 and tout == 40 and cost > 0


def test_nothing_to_analyse_raises():
    with pytest.raises(ValueError):
        upload.gather_uploaded(make_client(), "x")
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_sherlock_upload.py -v`
Expected: FAIL (`ModuleNotFoundError: sherlock.upload`).

- [ ] **Step 4: Implement `sherlock/upload.py`**

```python
import base64

import ai
from sherlock.models import GatherResult


def _blocks(pasted_text, files):
    blocks = []
    for _name, data, media_type in files:
        kind = "document" if media_type == "application/pdf" else "image"
        blocks.append({
            "type": kind,
            "source": {"type": "base64", "media_type": media_type,
                       "data": base64.standard_b64encode(data).decode()},
        })
    text = ai.load_prompt("sherlock_extract_upload")
    if pasted_text.strip():
        text += "\n\n## Texto colado\n" + pasted_text.strip()
    blocks.append({"type": "text", "text": text})
    return blocks


def gather_uploaded(client, source_label, pasted_text="", files=()):
    files = list(files)
    if not files:
        if not pasted_text.strip():
            raise ValueError("Não há nada para analisar: cola texto ou envia ficheiros.")
        return GatherResult(source_label, "upload", pasted_text.strip()), 0, 0, 0.0
    response = client.messages.create(
        model=ai.MODEL,
        max_tokens=ai.MAX_TOKENS,
        messages=[{"role": "user", "content": _blocks(pasted_text, files)}],
    )
    block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
    if block is None:
        raise ai.InvalidAIResponseError("A resposta não continha texto extraído.")
    tokens_in, tokens_out = response.usage.input_tokens, response.usage.output_tokens
    return (
        GatherResult(source_label, "upload", block.text.strip()),
        tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_sherlock_upload.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/sherlock/upload.py content-creator/prompts/sherlock_extract_upload.md content-creator/tests/test_sherlock_upload.py
git commit -m "feat: add Sherlock guided-upload extraction (text, images, PDFs)"
```

---

### Task 7: Sherlock chain, distiller and orchestration

**Files:**
- Create: `content-creator/sherlock/chain.py`, `content-creator/sherlock/distill.py`, `content-creator/sherlock/run.py`, `content-creator/prompts/sherlock_distill.md`
- Test: `content-creator/tests/test_sherlock_chain_distill.py`

**Interfaces:**
- Consumes: `coach_store.save_finding` (Task 2); `GatherResult`, `NeedsUpload`, `detect_platform`, `upload_instructions` (Task 3); `gather_website` (Task 3); `gather_video`, `whisper_transcribe` (Task 4); `gather_instagram_discovery` (Task 5); `gather_uploaded` (Task 6); `tone_guard.GENTLE_TONE_RULE` (Task 1); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Produces: `sherlock.chain.gather_source(source: str, ig: dict | None = None) -> GatherResult | NeedsUpload` (`ig` = `{"user_id": str, "token": str}` or `None`)
  - `sherlock.distill.distill(client, results: list[GatherResult], niche: str, brand_pack: str) -> tuple[dict, int, int, float]` where the dict is `{"brief": str, "patterns": [{"type": "hook"|"cta"|"structure", "description": str}]}`
  - `sherlock.run.run_sherlock(client, conn, sources: list[str], brand_pack: str, niche: str, daily_cap_usd: float, ig=None, gatherer=gather_source, distiller=distill, on_step=None) -> dict` with keys `finding_ids: list[int]` and `needs_upload: list[NeedsUpload]`
  - `sherlock.run.finish_upload(client, conn, source_label, pasted_text, files, brand_pack, niche, daily_cap_usd, on_step=None) -> int` (extract, distill and save one uploaded source; returns the finding id)

- [ ] **Step 1: Create `prompts/sherlock_distill.md`**

```
És um analista de estratégia de redes sociais. Recebes material bruto recolhido de perfis ou páginas de referência para o nicho: {{NICHE}}.

{{TONE_RULE}}

Regras:
- Analisa COMO o conteúdo funciona, nunca copies o conteúdo em si. Não cites frases inteiras do material.
- Identifica: mistura de conteúdos, tipos de gancho (hook), estilos de CTA, estrutura, tom e ritmo, o que parece gerar mais interacção, e ideias adaptáveis.
- Responde APENAS com um objecto JSON válido, sem texto adicional, no formato:
{"brief": "resumo curto em PT-PT (máx. 250 palavras)", "patterns": [{"type": "hook" | "cta" | "structure", "description": "descrição abstracta do padrão"}]}
```

- [ ] **Step 2: Write the failing tests**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import coach_store
import db
from sherlock import chain, distill, models, run


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    coach_store.init_schema(connection)
    return connection


def test_chain_routes_by_platform(monkeypatch):
    calls = []
    monkeypatch.setattr(chain, "gather_website", lambda s: calls.append(("web", s)) or models.GatherResult(s, "website", "x"))
    monkeypatch.setattr(chain, "gather_video", lambda s, **kw: calls.append(("video", s)) or models.GatherResult(s, "yt-dlp", "x"))
    monkeypatch.setattr(chain, "gather_instagram_discovery",
                        lambda s, uid, tok: calls.append(("ig", s, uid, tok)) or models.GatherResult(s, "ig", "x"))
    chain.gather_source("https://exemplo.pt")
    chain.gather_source("https://www.tiktok.com/@a")
    chain.gather_source("https://youtu.be/x")
    chain.gather_source("@perfil", ig={"user_id": "1", "token": "t"})
    assert [c[0] for c in calls] == ["web", "video", "video", "ig"]
    assert calls[3][2:] == ("1", "t")


def test_chain_text_source_becomes_a_direct_result():
    result = chain.gather_source("um texto colado com várias palavras seguidas")
    assert isinstance(result, models.GatherResult) and result.method == "pasted-text"


def test_distill_validates_and_returns_cost():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"brief": "resumo", "patterns": [{"type": "hook", "description": "pergunta directa"}]}')],
        usage=SimpleNamespace(input_tokens=200, output_tokens=80), stop_reason="end_turn",
    )
    data, tin, tout, cost = distill.distill(client, [models.GatherResult("s", "website", "texto")], "holístico", "brand")
    assert data["patterns"][0]["type"] == "hook" and tin == 200 and cost > 0
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "holístico" in prompt and "PT-PT" in prompt


def test_distill_rejects_bad_pattern_type():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"brief": "r", "patterns": [{"type": "copiar", "description": "x"}]}')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason="end_turn",
    )
    with pytest.raises(ai.InvalidAIResponseError):
        distill.distill(client, [models.GatherResult("s", "w", "t")], "n", "b")


def test_run_sherlock_saves_findings_and_reports_needs_upload(conn):
    outcomes = {
        "https://a.pt": models.GatherResult("https://a.pt", "website", "texto a"),
        "@b": models.NeedsUpload("@b", "bloqueado", "instruções"),
    }
    fake_distill = lambda client, results, niche, brand_pack: ({"brief": "resumo", "patterns": []}, 10, 5, 0.001)
    steps = []
    outcome = run.run_sherlock(
        MagicMock(), conn, ["https://a.pt", "@b"], "brand", "nicho", 2.0,
        gatherer=lambda s, ig=None: outcomes[s], distiller=fake_distill,
        on_step=lambda *a: steps.append(a),
    )
    assert len(outcome["finding_ids"]) == 1
    assert [n.source for n in outcome["needs_upload"]] == ["@b"]
    assert coach_store.list_findings(conn, "brand")[0]["brief_text"] == "resumo"
    assert conn.execute("SELECT COUNT(*) FROM api_calls WHERE function = 'sherlock_distill'").fetchone()[0] == 1
    assert ("sherlock_distill", "done") in steps


def test_run_sherlock_with_only_blocked_sources_makes_no_ai_call(conn):
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called"))
    outcome = run.run_sherlock(
        MagicMock(), conn, ["@b"], "brand", "nicho", 2.0,
        gatherer=lambda s, ig=None: models.NeedsUpload(s, "x", "y"), distiller=boom,
    )
    assert outcome["finding_ids"] == [] and len(outcome["needs_upload"]) == 1
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_sherlock_chain_distill.py -v`
Expected: FAIL (`ImportError` for `sherlock.chain`).

- [ ] **Step 4: Implement `sherlock/chain.py`**

```python
from sherlock.gather import (
    gather_instagram_discovery, gather_video, gather_website, whisper_transcribe,
)
from sherlock.models import GatherResult, detect_platform


def gather_source(source, ig=None):
    """Pick the right free gatherer for this source. Instagram profiles use the official
    Business Discovery API when configured; TikTok/YouTube use yt-dlp (+ whisper if
    installed); websites use a plain fetch. Any failure is returned as NeedsUpload so the
    UI can kindly ask for a PDF, screenshots or pasted captions (guided upload)."""
    platform = detect_platform(source)
    if platform == "website":
        return gather_website(source)
    if platform in ("tiktok", "youtube"):
        return gather_video(source, transcribe=whisper_transcribe)
    if platform == "instagram":
        ig = ig or {}
        return gather_instagram_discovery(source, ig.get("user_id"), ig.get("token"))
    return GatherResult(source[:40], "pasted-text", source)
```

- [ ] **Step 5: Implement `sherlock/distill.py`**

```python
import ai
from tone_guard import GENTLE_TONE_RULE

PATTERN_TYPES = ("hook", "cta", "structure")
MAX_CHARS_PER_SOURCE = 12000


def _validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("brief"), str) or not isinstance(data.get("patterns"), list):
        raise ai.InvalidAIResponseError("A análise da fonte não veio no formato esperado.")
    for pattern in data["patterns"]:
        if not isinstance(pattern, dict) or pattern.get("type") not in PATTERN_TYPES or not isinstance(pattern.get("description"), str):
            raise ai.InvalidAIResponseError("Um dos padrões identificados tem um formato inválido.")


def distill(client, results, niche, brand_pack):
    material = "\n\n".join(
        f"### Fonte: {r.source} ({r.method})\n{r.text[:MAX_CHARS_PER_SOURCE]}" for r in results
    )
    prompt = ai.render_prompt(ai.load_prompt("sherlock_distill"), niche=niche, tone_rule=GENTLE_TONE_RULE)
    prompt = f"{prompt}\n\n## Material\n{material}"
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    data = ai._parse_json_response(text)
    _validate(data)
    return data, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)
```

- [ ] **Step 6: Implement `sherlock/run.py`**

```python
import coach_store
import pipeline
from sherlock import upload
from sherlock.chain import gather_source
from sherlock.distill import distill
from sherlock.models import GatherResult


def _save(conn, brand_pack, results, data):
    return coach_store.save_finding(
        conn, brand_pack,
        ", ".join(r.source for r in results),
        ", ".join(sorted({r.method for r in results})),
        data["brief"], data["patterns"],
    )


def run_sherlock(client, conn, sources, brand_pack, niche, daily_cap_usd, ig=None,
                 gatherer=gather_source, distiller=distill, on_step=None):
    results, needs = [], []
    if on_step:
        on_step("sherlock_gather", "running")
    for source in sources:
        outcome = gatherer(source, ig=ig)
        (results if isinstance(outcome, GatherResult) else needs).append(outcome)
    if on_step:
        on_step("sherlock_gather", "done")
    finding_ids = []
    if results:
        data = pipeline._invoke(
            conn, None, daily_cap_usd, "sherlock_distill",
            lambda: distiller(client, results, niche, brand_pack), on_step=on_step,
        )
        finding_ids.append(_save(conn, brand_pack, results, data))
    return {"finding_ids": finding_ids, "needs_upload": needs}


def finish_upload(client, conn, source_label, pasted_text, files, brand_pack, niche,
                  daily_cap_usd, on_step=None):
    result = pipeline._invoke(
        conn, None, daily_cap_usd, "sherlock_extract_upload",
        lambda: upload.gather_uploaded(client, source_label, pasted_text, files), on_step=on_step,
    )
    data = pipeline._invoke(
        conn, None, daily_cap_usd, "sherlock_distill",
        lambda: distill(client, [result], niche, brand_pack), on_step=on_step,
    )
    return _save(conn, brand_pack, [result], data)
```

- [ ] **Step 7: Run to verify pass**

Run: `python -m pytest tests/test_sherlock_chain_distill.py -v`
Expected: PASS (6 tests).

- [ ] **Step 8: Commit**

```bash
git add content-creator/sherlock content-creator/prompts/sherlock_distill.md content-creator/tests/test_sherlock_chain_distill.py
git commit -m "feat: add Sherlock chain, distiller and orchestration"
```

---

### Task 8: Goal scoring

**Files:**
- Create: `content-creator/scoring.py`, `content-creator/prompts/score_goals.md`
- Test: `content-creator/tests/test_scoring.py`

**Interfaces:**
- Consumes: `tone_guard.GENTLE_TONE_RULE` (Task 1); `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Produces: `scoring.GOAL_MENU: dict[str, dict]`, keys `grow_audience`, `build_authority`, `get_conversations`, `followers_to_leads`, `leads_to_clients`, `keep_engaged`; each value `{"label": str, "metric": str}` (PT-PT).
  - `scoring.EVIDENCE_LEVELS = ("data", "pattern", "reasoned")`
  - `scoring.score_goals(client, profile: dict, evidence: dict) -> tuple[list[dict], int, int, float]`. `profile` = `{"who": str, "goals": list[str], "offers": list[str], "sources": list[str]}`; `evidence` = `{"windsor": dict | None, "findings": list[str]}`. Returns goals sorted best-first: each item `{"goal", "rank", "score", "metric", "target", "reasons": list[str], "evidence"}` (rank is assigned locally 1..n from the score, never trusted from the model). The same function signature is the swap point for JEV later.
  - `scoring.validate_scored_goals(items: list, allowed_goals: list[str]) -> list[dict]`

- [ ] **Step 1: Create `prompts/score_goals.md`**

```
És uma especialista em marketing de redes sociais para pessoas que são elas próprias o produto (palestras, workshops, consultas, cursos ou produtos).

{{TONE_RULE}}

Recebes o perfil da pessoa, os objectivos que escolheu e as evidências disponíveis (dados reais do Windsor, achados de perfis de referência). Para CADA objectivo escolhido, devolve uma pontuação de 0 a 100 de quão bem esse objectivo se ajusta a esta pessoa agora, uma métrica com meta realista e 2 a 3 razões curtas e simples.

O campo "evidence" deve ser: "data" se a razão se apoia em dados reais do Windsor; "pattern" se se apoia nos achados de perfis de referência; "reasoned" se é apenas raciocínio de marketing (sem dados). Nunca declares "data" sem dados reais.

Responde APENAS com um array JSON válido, sem texto adicional:
[{"goal": "<chave do objectivo>", "score": 0-100, "metric": "...", "target": "...", "reasons": ["...", "..."], "evidence": "data|pattern|reasoned"}]
```

- [ ] **Step 2: Write the failing tests**

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import scoring


def fake_client(payload):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=300, output_tokens=120), stop_reason="end_turn",
    )
    return client


PROFILE = {"who": "terapeuta holística", "goals": ["build_authority", "get_conversations"], "offers": ["workshop"], "sources": []}
EVIDENCE = {"windsor": None, "findings": ["resumo de um perfil"]}


def test_goal_menu_has_six_plain_language_goals():
    assert set(scoring.GOAL_MENU) == {
        "grow_audience", "build_authority", "get_conversations",
        "followers_to_leads", "leads_to_clients", "keep_engaged",
    }
    assert all(v["label"] and v["metric"] for v in scoring.GOAL_MENU.values())


def test_score_goals_ranks_by_score_and_ignores_model_rank():
    payload = [
        {"goal": "get_conversations", "score": 55, "metric": "DMs/semana", "target": "5", "reasons": ["a"], "evidence": "reasoned", "rank": 1},
        {"goal": "build_authority", "score": 80, "metric": "guardados", "target": "+40%", "reasons": ["b"], "evidence": "pattern", "rank": 2},
    ]
    items, tin, tout, cost = scoring.score_goals(fake_client(payload), PROFILE, EVIDENCE)
    assert [i["goal"] for i in items] == ["build_authority", "get_conversations"]
    assert [i["rank"] for i in items] == [1, 2]
    assert tin == 300 and cost > 0


def test_score_goals_prompt_carries_tone_rule_and_evidence():
    client = fake_client([{"goal": "build_authority", "score": 1, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}])
    scoring.score_goals(client, PROFILE, EVIDENCE)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "gentil" in prompt and "resumo de um perfil" in prompt


@pytest.mark.parametrize("bad", [
    [{"goal": "inventado", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": 500, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "prova"}],
    [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": [], "evidence": "reasoned"}],
    {"not": "a list"},
])
def test_validate_rejects_malformed_items(bad):
    with pytest.raises(ai.InvalidAIResponseError):
        scoring.validate_scored_goals(bad, ["build_authority", "get_conversations"])


def test_data_evidence_is_downgraded_when_no_windsor_data():
    payload = [{"goal": "build_authority", "score": 70, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "data"}]
    items, *_ = scoring.score_goals(fake_client(payload), PROFILE, EVIDENCE)
    assert items[0]["evidence"] == "reasoned"
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL (`ModuleNotFoundError: scoring`).

- [ ] **Step 4: Implement `scoring.py`**

```python
import json

import ai
from tone_guard import GENTLE_TONE_RULE

GOAL_MENU = {
    "grow_audience": {"label": "Crescer a minha audiência", "metric": "novos seguidores por mês"},
    "build_authority": {"label": "Construir confiança e autoridade", "metric": "guardados e partilhas por publicação"},
    "get_conversations": {"label": "Ter mais conversas", "metric": "mensagens e comentários por semana"},
    "followers_to_leads": {"label": "Transformar seguidores em contactos", "metric": "inscrições ou pedidos por mês"},
    "leads_to_clients": {"label": "Transformar contactos em clientes", "metric": "marcações ou vendas por mês"},
    "keep_engaged": {"label": "Manter a comunidade envolvida", "metric": "pessoas que interagem repetidamente"},
}

EVIDENCE_LEVELS = ("data", "pattern", "reasoned")


def validate_scored_goals(items, allowed_goals):
    if not isinstance(items, list) or not items:
        raise ai.InvalidAIResponseError("A pontuação dos objectivos não veio como uma lista.")
    for item in items:
        if not isinstance(item, dict):
            raise ai.InvalidAIResponseError("Um objectivo pontuado tem formato inválido.")
        if item.get("goal") not in allowed_goals:
            raise ai.InvalidAIResponseError(f"Objectivo desconhecido: {item.get('goal')!r}.")
        score = item.get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ai.InvalidAIResponseError("A pontuação tem de estar entre 0 e 100.")
        if item.get("evidence") not in EVIDENCE_LEVELS:
            raise ai.InvalidAIResponseError("O nível de evidência é inválido.")
        reasons = item.get("reasons")
        if not isinstance(reasons, list) or not reasons or not all(isinstance(r, str) for r in reasons):
            raise ai.InvalidAIResponseError("Cada objectivo precisa de pelo menos uma razão.")
        if not isinstance(item.get("metric"), str) or not isinstance(item.get("target"), str):
            raise ai.InvalidAIResponseError("Cada objectivo precisa de métrica e meta.")
    return items


def score_goals(client, profile, evidence):
    prompt = ai.render_prompt(ai.load_prompt("score_goals"), tone_rule=GENTLE_TONE_RULE)
    goal_lines = "\n".join(
        f"- {key}: {GOAL_MENU[key]['label']} (métrica base: {GOAL_MENU[key]['metric']})"
        for key in profile["goals"]
    )
    prompt = (
        f"{prompt}\n\n## Perfil\n{json.dumps(profile, ensure_ascii=False)}"
        f"\n\n## Objectivos escolhidos\n{goal_lines}"
        f"\n\n## Evidências\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    items = validate_scored_goals(ai._parse_json_response(text), list(profile["goals"]))
    has_windsor = bool(evidence.get("windsor"))
    has_findings = bool(evidence.get("findings"))
    for item in items:
        if item["evidence"] == "data" and not has_windsor:
            item["evidence"] = "pattern" if has_findings else "reasoned"
        if item["evidence"] == "pattern" and not has_findings:
            item["evidence"] = "reasoned"
    items.sort(key=lambda i: i["score"], reverse=True)
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add content-creator/scoring.py content-creator/prompts/score_goals.md content-creator/tests/test_scoring.py
git commit -m "feat: add goal scoring with ranks, reasons and evidence labels"
```

---

### Task 9: Coach orchestration

**Files:**
- Create: `content-creator/coach.py`, `content-creator/prompts/coach_draft.md`, `content-creator/prompts/coach_refine.md`
- Test: `content-creator/tests/test_coach.py`

**Interfaces:**
- Consumes: `coach_store.*` (Task 2); `scoring.score_goals`, `scoring.GOAL_MENU` (Task 8); `tone_guard.GENTLE_TONE_RULE` (Task 1); `sherlock.run.run_sherlock` (Task 7); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Produces: `coach.DRAFT_KINDS = ("offers","funnel","pillars","authority","rhythm")`
  - `coach.normalize_pillars(pillars: list[dict]) -> list[dict]` (each `{"name","percent","why"}`; percents become integers summing to exactly 100 using largest-remainder)
  - `coach.validate_draft_sections(data: dict) -> dict` (raises `ai.InvalidAIResponseError`); `rhythm` must contain integer `posts_per_week`, `reels_per_week`, `stories_per_week`
  - `coach.start_strategy(conn, brand_pack, profile: dict) -> int`
  - `coach.draft_strategy(client, conn, strategy_id: int, brand_pack: str, daily_cap_usd: float, windsor_summary: dict | None = None, on_step=None, scorer=scoring.score_goals, drafter=None) -> dict` (returns `coach_store.get_sections`)
  - `coach.refine_section(client, conn, strategy_id, kind, user_text, brand_pack, daily_cap_usd, on_step=None, refiner=None) -> dict` (new content; logs decision; state → `draft`)
  - `coach.accept_section(conn, strategy_id, kind) -> None`, `coach.revisit_section(conn, strategy_id, kind, reason: str) -> None`
  - `coach.accept_strategy(conn, strategy_id) -> None` (raises `coach.StrategyNotReady` listing kinds whose state is not `accepted`, or missing)
  - `coach.build_context(conn, strategy_id, decisions_limit=10) -> dict` (`{"profile","sections","decisions"}`; no chat replay)

Accepted-strategy content shapes (the Calendar plan relies on these):
`goals = {"ranked": [scored goal dicts]}`, `offers = {"items": [{"name","why"}]}`, `funnel = {"stages": [{"name","description"}]}`, `pillars = {"items": [{"name","percent","why"}]}`, `authority = {"items": [{"idea","why"}]}` (authority and social-proof actions), `rhythm = {"posts_per_week": int, "reels_per_week": int, "stories_per_week": int, "notes": str}`.

- [ ] **Step 1: Create the prompts**

`prompts/coach_draft.md`:

```
És uma coach de estratégia de redes sociais para pessoas que são elas próprias o produto (palestras, workshops, consultas, cursos ou produtos). Conversas com alguém que pode não saber nada de marketing: explica tudo em frases simples, sem jargão.

{{TONE_RULE}}

Com base no perfil, nos objectivos já pontuados e nas evidências, propõe uma estratégia completa. Responde APENAS com um objecto JSON válido, sem texto adicional, no formato:
{
 "offers": {"items": [{"name": "...", "why": "uma frase simples"}]},
 "funnel": {"stages": [{"name": "...", "description": "uma frase simples de como a pessoa avança"}]},
 "pillars": {"items": [{"name": "...", "percent": 0-100, "why": "..."}]},
 "authority": {"items": [{"idea": "...", "why": "..."}]},
 "rhythm": {"posts_per_week": 0, "reels_per_week": 0, "stories_per_week": 0, "notes": "..."}
}
Regras: 3 a 5 pilares cujas percentagens somam 100. As ofertas centram-se na própria pessoa (o utilizador é o produto). "authority" mistura acções de autoridade e prova social. Nunca copies conteúdo de perfis de referência, usa apenas os padrões.
```

`prompts/coach_refine.md`:

```
Estás a ajustar UMA secção de uma estratégia de redes sociais, seguindo o pedido da pessoa.

{{TONE_RULE}}

Secção a ajustar: {{SECTION_KIND}}
Conteúdo actual (JSON): {{SECTION_CONTENT}}
Decisões anteriores da pessoa (respeita-as; não voltes a propor o que ela recusou): {{DECISIONS}}
Pedido da pessoa: {{USER_TEXT}}

Responde APENAS com o novo conteúdo da secção em JSON válido, exactamente com o mesmo formato do conteúdo actual, sem texto adicional.
```

- [ ] **Step 2: Write the failing tests**

```python
import json
from unittest.mock import MagicMock

import pytest

import ai
import coach
import coach_store
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    coach_store.init_schema(connection)
    return connection


PROFILE = {"who": "terapeuta", "goals": ["build_authority"], "offers": ["workshop"], "sources": []}
SCORED = [{"goal": "build_authority", "rank": 1, "score": 80, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}]
DRAFT = {
    "offers": {"items": [{"name": "Workshop", "why": "w"}]},
    "funnel": {"stages": [{"name": "Descoberta", "description": "d"}]},
    "pillars": {"items": [{"name": "A", "percent": 34, "why": "x"}, {"name": "B", "percent": 33, "why": "y"}, {"name": "C", "percent": 34, "why": "z"}]},
    "authority": {"items": [{"idea": "i", "why": "w"}]},
    "rhythm": {"posts_per_week": 3, "reels_per_week": 1, "stories_per_week": 5, "notes": ""},
}


def test_normalize_pillars_sums_to_exactly_100():
    result = coach.normalize_pillars([
        {"name": "A", "percent": 33.3, "why": ""}, {"name": "B", "percent": 33.3, "why": ""}, {"name": "C", "percent": 33.3, "why": ""},
    ])
    assert sum(p["percent"] for p in result) == 100
    assert all(isinstance(p["percent"], int) for p in result)


def test_normalize_pillars_scales_when_far_from_100():
    result = coach.normalize_pillars([{"name": "A", "percent": 10, "why": ""}, {"name": "B", "percent": 10, "why": ""}])
    assert [p["percent"] for p in result] == [50, 50]


def test_validate_draft_sections_requires_all_keys_and_int_rhythm():
    assert coach.validate_draft_sections(json.loads(json.dumps(DRAFT)))["pillars"]["items"]
    broken = json.loads(json.dumps(DRAFT))
    del broken["funnel"]
    with pytest.raises(ai.InvalidAIResponseError):
        coach.validate_draft_sections(broken)
    bad_rhythm = json.loads(json.dumps(DRAFT))
    bad_rhythm["rhythm"]["posts_per_week"] = "três"
    with pytest.raises(ai.InvalidAIResponseError):
        coach.validate_draft_sections(bad_rhythm)


def test_draft_strategy_persists_all_sections_and_logs_costs(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.save_finding(conn, "brand", "https://x.pt", "website", "resumo do perfil", [])
    seen = {}

    def scorer(client, profile, evidence):
        seen["evidence"] = evidence
        return SCORED, 10, 5, 0.001

    def drafter(client, profile, scored, evidence, brand_pack):
        return json.loads(json.dumps(DRAFT)), 20, 10, 0.002

    sections = coach.draft_strategy(MagicMock(), conn, sid, "brand", 2.0, scorer=scorer, drafter=drafter)
    assert set(sections) == set(coach_store.SECTION_KINDS)
    assert sections["goals"]["content"]["ranked"][0]["goal"] == "build_authority"
    assert sections["pillars"]["content"]["items"][0]["percent"] in (34, 33)
    assert seen["evidence"]["findings"] == ["resumo do perfil"]
    assert all(s["state"] == "draft" for s in sections.values())
    functions = [r["function"] for r in conn.execute("SELECT function FROM api_calls ORDER BY id")]
    assert functions == ["score_goals", "coach_draft"]


def test_refine_section_logs_decision_and_returns_draft_state(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.set_section(conn, sid, "offers", DRAFT["offers"], state="accepted")
    captured = {}

    def refiner(client, kind, content, decisions, user_text, brand_pack):
        captured.update(kind=kind, decisions=decisions, user_text=user_text)
        return {"items": [{"name": "Consulta", "why": "c"}]}, 5, 5, 0.001

    new = coach.refine_section(MagicMock(), conn, sid, "offers", "prefiro consultas", "brand", 2.0, refiner=refiner)
    assert new["items"][0]["name"] == "Consulta"
    section = coach_store.get_sections(conn, sid)["offers"]
    assert section["state"] == "draft"
    decisions = coach_store.list_decisions(conn, sid)
    assert decisions[-1]["action"] == "edit" and decisions[-1]["user_reason"] == "prefiro consultas"
    assert captured["kind"] == "offers"


def test_refine_pillars_renormalizes(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.set_section(conn, sid, "pillars", DRAFT["pillars"])
    refiner = lambda *a, **k: ({"items": [{"name": "A", "percent": 30, "why": ""}, {"name": "B", "percent": 30, "why": ""}]}, 1, 1, 0.0)
    new = coach.refine_section(MagicMock(), conn, sid, "pillars", "menos pilares", "brand", 2.0, refiner=refiner)
    assert sum(p["percent"] for p in new["items"]) == 100


def test_accept_and_revisit_section_log_decisions(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.set_section(conn, sid, "offers", DRAFT["offers"])
    coach.revisit_section(conn, sid, "offers", "não é para mim")
    assert coach_store.get_sections(conn, sid)["offers"]["state"] == "revisit"
    coach.accept_section(conn, sid, "offers")
    assert coach_store.get_sections(conn, sid)["offers"]["state"] == "accepted"
    assert [d["action"] for d in coach_store.list_decisions(conn, sid)] == ["revisit", "accept"]


def test_accept_strategy_requires_every_section_accepted(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.set_section(conn, sid, "offers", DRAFT["offers"], state="accepted")
    with pytest.raises(coach.StrategyNotReady) as exc:
        coach.accept_strategy(conn, sid)
    assert "funnel" in exc.value.pending
    for kind in coach_store.SECTION_KINDS:
        coach_store.set_section(conn, sid, kind, {"x": 1}, state="accepted")
    coach.accept_strategy(conn, sid)
    assert coach_store.get_strategy(conn, sid)["status"] == "accepted"


def test_build_context_uses_recent_decisions_not_chat_turns(conn):
    sid = coach.start_strategy(conn, "brand", PROFILE)
    coach_store.set_section(conn, sid, "offers", DRAFT["offers"])
    for i in range(12):
        coach_store.log_decision(conn, sid, "offers", "edit", f"m{i}")
    coach_store.add_turn(conn, sid, "user", "conversa longa que não deve ser reenviada")
    context = coach.build_context(conn, sid, decisions_limit=10)
    assert len(context["decisions"]) == 10 and context["decisions"][-1]["user_reason"] == "m11"
    assert "turns" not in context and context["profile"] == PROFILE
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_coach.py -v`
Expected: FAIL (`ModuleNotFoundError: coach`).

- [ ] **Step 4: Implement `coach.py`**

```python
import json

import ai
import coach_store
import pipeline
import scoring
from tone_guard import GENTLE_TONE_RULE

DRAFT_KINDS = ("offers", "funnel", "pillars", "authority", "rhythm")
RHYTHM_KEYS = ("posts_per_week", "reels_per_week", "stories_per_week")


class StrategyNotReady(Exception):
    def __init__(self, pending):
        self.pending = list(pending)
        super().__init__(
            "Ainda faltam secções por aceitar: " + ", ".join(self.pending)
            + ". Sem pressa, quando estiveres pronta voltamos a elas."
        )


def normalize_pillars(pillars):
    total = sum(p["percent"] for p in pillars) or 1
    raw = [p["percent"] * 100 / total for p in pillars]
    floors = [int(x) for x in raw]
    remainder = 100 - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return [{**p, "percent": floors[i]} for i, p in enumerate(pillars)]


def validate_draft_sections(data):
    if not isinstance(data, dict) or any(k not in data for k in DRAFT_KINDS):
        raise ai.InvalidAIResponseError("O rascunho da estratégia não trouxe todas as secções.")
    rhythm = data["rhythm"]
    if not isinstance(rhythm, dict) or not all(isinstance(rhythm.get(k), int) for k in RHYTHM_KEYS):
        raise ai.InvalidAIResponseError("O ritmo de publicação precisa de números inteiros por semana.")
    items = data["pillars"].get("items") if isinstance(data["pillars"], dict) else None
    if not items or not all(isinstance(p.get("percent"), (int, float)) for p in items):
        raise ai.InvalidAIResponseError("Os pilares precisam de percentagens.")
    data["pillars"] = {"items": normalize_pillars(items)}
    return data


def start_strategy(conn, brand_pack, profile):
    return coach_store.create_strategy(conn, brand_pack, profile=profile)


def _overall_evidence(scored):
    levels = {g["evidence"] for g in scored}
    return "data" if "data" in levels else "pattern" if "pattern" in levels else "reasoned"


def draft_sections(client, profile, scored, evidence, brand_pack):
    prompt = ai.render_prompt(ai.load_prompt("coach_draft"), tone_rule=GENTLE_TONE_RULE)
    prompt = (
        f"{prompt}\n\n## Perfil\n{json.dumps(profile, ensure_ascii=False)}"
        f"\n\n## Objectivos pontuados\n{json.dumps(scored, ensure_ascii=False)}"
        f"\n\n## Evidências\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    data = validate_draft_sections(ai._parse_json_response(text))
    return data, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def draft_strategy(client, conn, strategy_id, brand_pack, daily_cap_usd, windsor_summary=None,
                   on_step=None, scorer=scoring.score_goals, drafter=None):
    strategy = coach_store.get_strategy(conn, strategy_id)
    profile = strategy["profile"]
    briefs = [f["brief_text"] for f in coach_store.list_findings(conn, brand_pack)]
    evidence = {"windsor": windsor_summary, "findings": briefs}
    scored = pipeline._invoke(
        conn, None, daily_cap_usd, "score_goals",
        lambda: scorer(client, profile, evidence), on_step=on_step,
    )
    coach_store.set_section(conn, strategy_id, "goals", {"ranked": scored}, evidence=_overall_evidence(scored))
    drafted = pipeline._invoke(
        conn, None, daily_cap_usd, "coach_draft",
        lambda: (drafter or draft_sections)(client, profile, scored, evidence, brand_pack), on_step=on_step,
    )
    for kind in DRAFT_KINDS:
        coach_store.set_section(conn, strategy_id, kind, drafted[kind], evidence=_overall_evidence(scored))
    return coach_store.get_sections(conn, strategy_id)


def build_context(conn, strategy_id, decisions_limit=10):
    return {
        "profile": coach_store.get_strategy(conn, strategy_id)["profile"],
        "sections": coach_store.get_sections(conn, strategy_id),
        "decisions": coach_store.list_decisions(conn, strategy_id, limit=decisions_limit),
    }


def refine_section_content(client, kind, content, decisions, user_text, brand_pack):
    prompt = ai.render_prompt(
        ai.load_prompt("coach_refine"),
        tone_rule=GENTLE_TONE_RULE, section_kind=kind,
        section_content=json.dumps(content, ensure_ascii=False),
        decisions=json.dumps(decisions, ensure_ascii=False), user_text=user_text,
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    return ai._parse_json_response(text), tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def refine_section(client, conn, strategy_id, kind, user_text, brand_pack, daily_cap_usd,
                   on_step=None, refiner=None):
    context = build_context(conn, strategy_id)
    current = context["sections"][kind]["content"]
    decisions = [{"section": d["section_kind"], "action": d["action"], "reason": d["user_reason"]}
                 for d in context["decisions"]]
    new_content = pipeline._invoke(
        conn, None, daily_cap_usd, "coach_refine",
        lambda: (refiner or refine_section_content)(client, kind, current, decisions, user_text, brand_pack),
        on_step=on_step,
    )
    if kind == "pillars":
        new_content = {"items": normalize_pillars(new_content["items"])}
    coach_store.set_section(
        conn, strategy_id, kind, new_content, state="draft",
        evidence=context["sections"][kind]["evidence"],
    )
    coach_store.log_decision(conn, strategy_id, kind, "edit", user_text)
    return new_content


def accept_section(conn, strategy_id, kind):
    coach_store.set_section_state(conn, strategy_id, kind, "accepted")
    coach_store.log_decision(conn, strategy_id, kind, "accept")


def revisit_section(conn, strategy_id, kind, reason):
    coach_store.set_section_state(conn, strategy_id, kind, "revisit")
    coach_store.log_decision(conn, strategy_id, kind, "revisit", reason)


def accept_strategy(conn, strategy_id):
    sections = coach_store.get_sections(conn, strategy_id)
    pending = [k for k in coach_store.SECTION_KINDS if sections.get(k, {}).get("state") != "accepted"]
    if pending:
        raise StrategyNotReady(pending)
    coach_store.mark_accepted(conn, strategy_id)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_coach.py -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/coach.py content-creator/prompts/coach_draft.md content-creator/prompts/coach_refine.md content-creator/tests/test_coach.py
git commit -m "feat: add coach orchestration (draft, refine, accept, context)"
```

---

### Task 10: Coach tab (Estratégia) and app wiring

**Files:**
- Create: `content-creator/ui_coach.py`
- Modify: `content-creator/app.py` (imports at lines 1-8; `db.init_db(conn)` at line 14; `STEP_LABELS` dict; tab list at line ~68; add a `with tab_strategy:` block at the end)
- Test: `content-creator/tests/test_ui_coach.py`

**Interfaces:**
- Consumes: `coach.*` (Task 9); `coach_store.init_schema`, `coach_store.latest_strategy`, `coach_store.get_sections`, `coach_store.list_findings` (Task 2); `scoring.GOAL_MENU` (Task 8); `sherlock.run.run_sherlock`, `sherlock.run.finish_upload` (Task 7); `tone_guard.find_harsh_words` (Task 1).
- Produces: `ui_coach.COPY: dict[str, str]` (all canned PT-PT UI strings; tested against the tone guard)
  - `ui_coach.describe_section(kind: str, content: dict) -> str` (pure; markdown for one section)
  - `ui_coach.evidence_label(evidence: str) -> str` (`data` → "Com dados reais", `pattern` → "Com base em perfis de referência", `reasoned` → "Raciocínio, ainda sem prova")
  - `ui_coach.render(cfg, conn, client, run_with_progress) -> None` (renders the whole tab)
  - New tab named "Estratégia" in `app.py`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from streamlit.testing.v1 import AppTest

import tone_guard
import ui_coach

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_all_canned_copy_passes_the_tone_guard():
    for key, text in ui_coach.COPY.items():
        assert tone_guard.find_harsh_words(text) == [], key


def test_evidence_labels_are_distinct_and_honest():
    labels = {ui_coach.evidence_label(e) for e in ("data", "pattern", "reasoned")}
    assert len(labels) == 3
    assert "sem prova" in ui_coach.evidence_label("reasoned")


def test_describe_section_pillars_lists_percentages():
    text = ui_coach.describe_section("pillars", {"items": [{"name": "Educar", "percent": 60, "why": "confiança"}, {"name": "Bastidores", "percent": 40, "why": "proximidade"}]})
    assert "Educar" in text and "60%" in text and "confiança" in text


def test_describe_section_rhythm_shows_weekly_counts():
    text = ui_coach.describe_section("rhythm", {"posts_per_week": 3, "reels_per_week": 1, "stories_per_week": 5, "notes": "sem pressa"})
    assert "3" in text and "reels" in text.lower() and "sem pressa" in text


def test_strategy_tab_shows_the_three_questions(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    at = AppTest.from_file(APP_PATH)
    at.run()
    assert not at.exception
    assert "Estratégia" in [t.label for t in at.tabs]
    assert any("Quem és" in ta.label for ta in at.text_area)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_coach.py -v`
Expected: FAIL (`ModuleNotFoundError: ui_coach`).

- [ ] **Step 3: Implement `ui_coach.py`**

```python
import streamlit as st

import coach
import coach_store
import scoring
from sherlock import run as sherlock_run

COPY = {
    "intro": "Vamos construir juntos uma estratégia à tua medida. São só três perguntas, e eu trato do resto.",
    "q_who": "Quem és tu e o que fazes? (o teu nicho e o teu trabalho)",
    "q_goals": "O que gostavas de conseguir nos próximos 3 meses? (escolhe até 3)",
    "q_offers": "O que podes oferecer? Se não tiveres a certeza, sugiro-te opções.",
    "q_sources": "Perfis ou páginas que admiras (opcional, um por linha, qualquer link ou @)",
    "start": "Preparar a minha estratégia",
    "too_many_goals": "Escolhe até 3 objectivos, para o plano ficar leve e possível.",
    "need_who": "Conta-me só um pouco sobre ti para eu poder começar.",
    "budget": "Por hoje já usámos o orçamento definido. Retomamos amanhã, sem pressa.",
    "ready": "A tua estratégia está pronta para ajustares ao teu gosto.",
    "accepted": "Estratégia guardada. Já podemos passar ao calendário.",
    "upload_title": "Ajuda-me com esta fonte",
}
OFFER_OPTIONS = ["Palestra", "Workshop", "Consulta", "Curso", "Produto", "Ainda não sei"]
SECTION_TITLES = {
    "goals": "Objectivos (por ordem de encaixe)", "offers": "O que podes oferecer",
    "funnel": "O caminho até ao cliente", "pillars": "Pilares de conteúdo",
    "authority": "Autoridade e prova social", "rhythm": "Ritmo de publicação",
}
SECTION_HELP = {
    "goals": "Os objectivos são o que queres alcançar. Ordenei-os pelo que faz mais sentido agora.",
    "offers": "As ofertas são o que as pessoas podem contratar ou comprar. Tu és o centro.",
    "funnel": "O funil é o caminho de quem te descobre até se tornar cliente.",
    "pillars": "Os pilares são os grandes temas de que falas, com a percentagem de cada um.",
    "authority": "Autoridade é ser vista como referência; prova social são os sinais de que outras pessoas confiam em ti.",
    "rhythm": "Quantas publicações, reels e stories por semana, a um ritmo simpático.",
}
EVIDENCE_LABELS = {
    "data": "Com dados reais",
    "pattern": "Com base em perfis de referência",
    "reasoned": "Raciocínio, ainda sem prova",
}


def evidence_label(evidence):
    return EVIDENCE_LABELS[evidence]


def describe_section(kind, content):
    if kind == "goals":
        return "\n".join(
            f"{g['rank']}. **{scoring.GOAL_MENU[g['goal']]['label']}**: {g['metric']}, meta {g['target']}. "
            + " ".join(g["reasons"]) + f" _({evidence_label(g['evidence'])})_"
            for g in content["ranked"]
        )
    if kind == "offers":
        return "\n".join(f"- **{i['name']}**: {i['why']}" for i in content["items"])
    if kind == "funnel":
        return "\n".join(f"{n}. **{s['name']}**: {s['description']}" for n, s in enumerate(content["stages"], 1))
    if kind == "pillars":
        return "\n".join(f"- **{p['name']}** ({p['percent']}%): {p['why']}" for p in content["items"])
    if kind == "authority":
        return "\n".join(f"- {i['idea']}: {i['why']}" for i in content["items"])
    return (
        f"- {content['posts_per_week']} publicações por semana\n"
        f"- {content['reels_per_week']} reels por semana\n"
        f"- {content['stories_per_week']} stories por semana\n\n{content.get('notes', '')}"
    )


def _ig_from_env():
    import os

    user_id, token = os.environ.get("IG_BUSINESS_ACCOUNT_ID"), os.environ.get("IG_ACCESS_TOKEN")
    return {"user_id": user_id, "token": token} if user_id and token else None


def _render_questions(cfg, conn, client, run_with_progress):
    st.write(COPY["intro"])
    who = st.text_area(COPY["q_who"], key="coach_who")
    goal_keys = st.multiselect(
        COPY["q_goals"], list(scoring.GOAL_MENU), format_func=lambda k: scoring.GOAL_MENU[k]["label"], key="coach_goals",
    )
    offers = st.multiselect(COPY["q_offers"], OFFER_OPTIONS, key="coach_offers")
    sources_text = st.text_area(COPY["q_sources"], key="coach_sources")
    if st.button(COPY["start"], type="primary"):
        if not who.strip():
            st.info(COPY["need_who"])
            return
        if not goal_keys or len(goal_keys) > 3:
            st.info(COPY["too_many_goals"])
            return
        sources = [s.strip() for s in sources_text.splitlines() if s.strip()]
        profile = {"who": who.strip(), "goals": goal_keys, "offers": offers, "sources": sources}
        try:
            needs = []
            if sources:
                outcome = run_with_progress(
                    sherlock_run.run_sherlock, client, conn, sources, cfg.brand_pack, who.strip(),
                    cfg.max_daily_spend_usd, ig=_ig_from_env(),
                )
                needs = outcome["needs_upload"]
            strategy_id = coach.start_strategy(conn, cfg.brand_pack, profile)
            if needs:
                st.session_state["coach_needs_upload"] = needs
            coach.draft_strategy(client, conn, strategy_id, cfg.brand_pack, cfg.max_daily_spend_usd)
        except Exception as e:  # budget cap and API problems: a calm message, details stay in the progress box
            st.info(COPY["budget"] if "daily cap" in str(e) else "Algo não correu como esperado, podemos tentar de novo quando quiseres.")
            return
        st.session_state["coach_strategy_id"] = strategy_id
        st.rerun()


def _render_uploads(cfg, conn, client, run_with_progress, niche):
    needs = st.session_state.get("coach_needs_upload", [])
    for n, need in enumerate(list(needs)):
        with st.expander(f"{COPY['upload_title']}: {need.source}", expanded=True):
            st.write(need.instructions)
            pasted = st.text_area("Texto colado", key=f"upload_text_{n}")
            files = st.file_uploader("Ficheiros (PDF ou imagens)", accept_multiple_files=True,
                                     type=["pdf", "png", "jpg", "jpeg"], key=f"upload_files_{n}")
            if st.button("Usar isto", key=f"upload_go_{n}"):
                payload = [(f.name, f.getvalue(), f.type) for f in files]
                run_with_progress(
                    sherlock_run.finish_upload, client, conn, need.source, pasted, payload,
                    cfg.brand_pack, niche, cfg.max_daily_spend_usd,
                )
                needs.pop(n)
                st.rerun()


def _render_strategy(cfg, conn, client, run_with_progress, strategy_id):
    strategy = coach_store.get_strategy(conn, strategy_id)
    sections = coach_store.get_sections(conn, strategy_id)
    _render_uploads(cfg, conn, client, run_with_progress, strategy["profile"]["who"])
    st.success(COPY["ready"])
    for kind in coach_store.SECTION_KINDS:
        section = sections.get(kind)
        if not section:
            continue
        with st.expander(f"{SECTION_TITLES[kind]} · {section['state']}", expanded=section["state"] != "accepted"):
            st.caption(SECTION_HELP[kind] + "  " + evidence_label(section["evidence"]))
            st.markdown(describe_section(kind, section["content"]))
            if kind == "goals":
                st.caption("Para ajustar a ordem, diz-me o que preferes e eu explico as consequências.")
            feedback = st.text_input("O que gostavas de mudar? (por exemplo: mais caloroso, menos reels)", key=f"fb_{kind}")
            col1, col2, col3 = st.columns(3)
            if col1.button("Aceitar", key=f"acc_{kind}", type="primary"):
                coach.accept_section(conn, strategy_id, kind)
                st.rerun()
            if col2.button("Ajustar", key=f"edit_{kind}") and feedback.strip() and kind != "goals":
                try:
                    run_with_progress(coach.refine_section, client, conn, strategy_id, kind,
                                      feedback.strip(), cfg.brand_pack, cfg.max_daily_spend_usd)
                except Exception:
                    st.info(COPY["budget"])
                else:
                    st.rerun()
            if col3.button("Não é para mim", key=f"no_{kind}"):
                coach.revisit_section(conn, strategy_id, kind, feedback.strip() or "não é para mim")
                st.rerun()
    if strategy["status"] == "accepted":
        st.success(COPY["accepted"])
    elif st.button("Guardar a estratégia", type="primary"):
        try:
            coach.accept_strategy(conn, strategy_id)
        except coach.StrategyNotReady as e:
            st.info(str(e))
        else:
            st.rerun()


def render(cfg, conn, client, run_with_progress):
    # An explicit None in session state means "user asked for a new strategy": show the questions.
    if "coach_strategy_id" in st.session_state:
        strategy_id = st.session_state["coach_strategy_id"]
    else:
        latest = coach_store.latest_strategy(conn, cfg.brand_pack)
        strategy_id = latest["id"] if latest else None
    if strategy_id is None:
        _render_questions(cfg, conn, client, run_with_progress)
    else:
        _render_strategy(cfg, conn, client, run_with_progress, strategy_id)
        if st.button("Começar uma estratégia nova"):
            st.session_state["coach_strategy_id"] = None
            st.rerun()
```

- [ ] **Step 4: Wire into `app.py`**

1. Add `import coach_store` and `import ui_coach` to the imports.
2. After `db.init_db(conn)` add `coach_store.init_schema(conn)`.
3. Extend `STEP_LABELS` with: `"sherlock_gather": "A ler as fontes de referência"`, `"sherlock_distill": "A extrair os padrões"`, `"sherlock_extract_upload": "A ler o que enviaste"`, `"score_goals": "A avaliar os objectivos"`, `"coach_draft": "A montar a estratégia"`, `"coach_refine": "A ajustar a estratégia"`.
4. Change the tab line to `tab_new, tab_images, tab_library, tab_strategy = st.tabs(["Nova Ideia", "Gerar Imagens", "Biblioteca", "Estratégia"])`.
5. At the end of the file add:

```python
with tab_strategy:
    ui_coach.render(cfg, conn, client, run_with_progress)
```

(If the look-and-feel tickets have already merged, keep their `theme.inject_theme()` / `theme.render_header(...)` calls; only the lines above change.)

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite, including the existing `test_app_smoke.py`).

- [ ] **Step 6: Commit**

```bash
git add content-creator/ui_coach.py content-creator/app.py content-creator/tests/test_ui_coach.py
git commit -m "feat: add Estratégia tab (three questions, strategy review, guided upload)"
```

---

## Final checklist (after all tasks are merged into `strategy-coach`)

- [ ] Run the whole suite: `python -m pytest tests -q` (expect all green).
- [ ] **One real, paid end-to-end run** with the real Anthropic key and one real reference website: answer the three questions, confirm Sherlock returns a brief, the strategy draft appears with six sections, refine one section, accept all, and check `api_calls` rows for `score_goals`, `coach_draft`, `sherlock_distill`. Record any real bug the mocks missed in `content-creator/docs/decisions.md`.
- [ ] Read every screen once for tone: nothing urgent, critical or blaming.
- [ ] Final whole-branch review, then merge `strategy-coach` into `main`.
