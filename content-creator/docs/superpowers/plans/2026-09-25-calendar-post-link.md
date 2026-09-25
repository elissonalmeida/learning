# Calendar ↔ Post Creator Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From any calendar slot, create the post with one click (topic, pillar, angle, funnel phase, CTA and niche date pre-filled), keep slot status in sync with the idea's progress, and let the user refine drafts in plain words.

**Architecture:** Small bridge module (`slot_bridge.py`) between `calendar_store` slots and `db` ideas; an optional `context` argument threaded through `ai.generate_draft` and `pipeline.run_generation_pipeline` (default `None` keeps existing behavior and existing tests unchanged); a feedback-revision function that re-runs the existing quality gate; a thin `ui_link.py` so `app.py` edits stay minimal.

**Tech Stack:** Python, Streamlit (`AppTest` for UI tests), SQLite, pytest + `unittest.mock`.

**Spec:** `content-creator/docs/superpowers/specs/2026-09-25-calendar-post-creator-link-design.md`

**Feature branch:** `calendar-post-link` (create from `main`; tickets branch off it as `ticket-<issue-number>`). Task 1 needs nothing from other plans and can start immediately. Tickets with a `Cross-plan` line depend on the *final ticket* of the named plan: they only unblock after that plan has been reviewed and merged into `main`, and `main` has been merged into this feature branch.

**Test command (run from `content-creator/`):** `python -m pytest tests -q`

## Global Constraints

- **Existing pipeline tests must pass unchanged.** `context` is optional everywhere and is only passed to `ai_module.generate_draft` when it is not `None` (existing fake AI modules don't accept it).
- All user-facing and AI-generated text is **PT-PT** and **gentle** (no urgency, no blame). Prompts that write user-facing feedback include `tone_guard.GENTLE_TONE_RULE`.
- Every AI call goes through `pipeline._invoke` (spend cap + cost logging). Brand-pack quality gates (`critique_draft`) still run on every revised draft.
- v1 is **one post per slot** ("Criar este post"); no bulk creation (image creation isn't polished yet).
- Streamlit cannot switch tabs programmatically: after creating the idea, the UI tells the user where to continue and pre-selects the idea there.
- Sherlock writing patterns are inspiration for structure only; never copy competitor content.
- Slot statuses: `planned`, `in_production`, `ready`, `published`. Idea → slot mapping: `idea`/`reviewed` → `in_production`; `approved`/`images_ready` → `ready`; `rejected`/`archived` (or a deleted idea) → `planned` with the idea link cleared. `published` is manual and is never overwritten.
- Slot-created ideas use `source_type="calendar"`.

---

### Task 1: Optional draft context in `ai` and `pipeline`

**Files:**
- Modify: `content-creator/ai.py` (add `build_context_block`; extend `generate_draft` at line ~154), `content-creator/pipeline.py` (extend `run_generation_pipeline` at line ~51)
- Test: `content-creator/tests/test_draft_context.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ai.build_context_block(context: dict | None) -> str` (empty string for `None`/empty; otherwise a `## Contexto do Calendário` block). Recognised keys, all optional: `angle`, `funnel_phase`, `goal`, `cta_keyword`, `niche_date` (strings), `patterns` (list of strings), `preferences` (list of strings).
  - `ai.generate_draft(client, topic, tone, pillar, brand_pack, context=None)`
  - `pipeline.run_generation_pipeline(client, conn, idea, tone, brand_pack, daily_cap_usd, ai_module=ai, on_step=None, context=None)` (passes `context=` to `ai_module.generate_draft` only when not `None`)

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import ai
import db
import pipeline


def fake_client(text='{"caption": "c", "slides": ["s"]}'):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5), stop_reason="end_turn",
    )
    return client


def test_build_context_block_is_empty_without_useful_context():
    assert ai.build_context_block(None) == ""
    assert ai.build_context_block({}) == ""
    assert ai.build_context_block({"angle": ""}) == ""


def test_build_context_block_lists_every_provided_field():
    block = ai.build_context_block({
        "angle": "guia prático", "funnel_phase": "Confiança", "goal": "build_authority",
        "cta_keyword": "GUIA", "niche_date": "Lua Nova: recomeços",
        "patterns": ["pergunta directa no início"], "preferences": ["mais caloroso"],
    })
    for expected in ("guia prático", "Confiança", "GUIA", "Lua Nova", "pergunta directa", "mais caloroso", "nunca copies"):
        assert expected in block


def test_generate_draft_includes_the_context_block_only_when_given():
    with_ctx, without_ctx = fake_client(), fake_client()
    ai.generate_draft(with_ctx, "lavanda", "Caloroso", "Educativo Integrativo", "marianabotelho-ig", context={"angle": "guia prático"})
    ai.generate_draft(without_ctx, "lavanda", "Caloroso", "Educativo Integrativo", "marianabotelho-ig")
    assert "Contexto do Calendário" in with_ctx.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Contexto do Calendário" not in without_ctx.messages.create.call_args.kwargs["messages"][0]["content"]


class _FakeAI:
    MAX_REVISION_ROUNDS = 0

    def __init__(self, accepts_context):
        self.seen = "unset"
        if accepts_context:
            self.generate_draft = self._with_context

    def _with_context(self, client, topic, tone, pillar, brand_pack, context=None):
        self.seen = context
        return {"caption": "c", "slides": ["s"]}, 1, 1, 0.0

    def generate_draft(self, client, topic, tone, pillar, brand_pack):
        self.seen = "no-context-arg"
        return {"caption": "c", "slides": ["s"]}, 1, 1, 0.0

    def critique_draft(self, client, draft, brand_pack):
        return [], 1, 1, 0.0


def _idea():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    idea_id = db.create_idea(conn, "brand", "manual", "tema", pillar="P")
    return conn, db.get_idea(conn, idea_id)


def test_pipeline_passes_context_only_when_provided():
    conn, idea = _idea()
    fake = _FakeAI(accepts_context=True)
    pipeline.run_generation_pipeline(None, conn, idea, "Tom", "brand", 5.0, ai_module=fake, context={"angle": "a"})
    assert fake.seen == {"angle": "a"}


def test_pipeline_keeps_working_with_ai_modules_that_do_not_know_context():
    conn, idea = _idea()
    fake = _FakeAI(accepts_context=False)
    pipeline.run_generation_pipeline(None, conn, idea, "Tom", "brand", 5.0, ai_module=fake)
    assert fake.seen == "no-context-arg"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_draft_context.py -v`
Expected: FAIL (`AttributeError: module 'ai' has no attribute 'build_context_block'`).

- [ ] **Step 3: Implement in `ai.py`**

Add above `generate_draft`:

```python
_CONTEXT_LABELS = (
    ("angle", "Ângulo"), ("funnel_phase", "Fase do funil"), ("goal", "Objectivo"),
    ("cta_keyword", "Palavra-chave do CTA (convida a comentar esta palavra)"), ("niche_date", "Data do nicho"),
)


def build_context_block(context):
    if not context:
        return ""
    lines = [f"- {label}: {context[key]}" for key, label in _CONTEXT_LABELS if context.get(key)]
    if context.get("patterns"):
        lines.append(
            "- Padrões de escrita observados noutros perfis (usa só como inspiração de estrutura; nunca copies conteúdo): "
            + "; ".join(context["patterns"])
        )
    if context.get("preferences"):
        lines.append("- Preferências de tom desta pessoa (respeita-as): " + "; ".join(context["preferences"]))
    if not lines:
        return ""
    return "\n\n## Contexto do Calendário\n" + "\n".join(lines)
```

Change `generate_draft` to:

```python
def generate_draft(client, topic, tone, pillar, brand_pack, context=None):
    prompt = render_prompt(
        load_prompt("generate_draft"),
        domain_framework=load_brand_doc(brand_pack, "domain-framework.md"),
        tone_of_voice=load_brand_doc(brand_pack, "tone-of-voice.md"),
    )
    prompt = f"{prompt}\n\n## Tópico\n{topic}\n\n## Pilar\n{pillar}\n\n## Tom Escolhido\n{tone}"
    prompt += build_context_block(context)
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    draft = _parse_json_response(text)
    return draft, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)
```

- [ ] **Step 4: Implement in `pipeline.py`**

Change the signature and the first `_invoke` in `run_generation_pipeline`:

```python
def run_generation_pipeline(client, conn, idea, tone, brand_pack, daily_cap_usd, ai_module=ai, on_step=None, context=None):
    idea_id = idea["id"]

    def _generate():
        if context is None:
            return ai_module.generate_draft(client, idea["topic"], tone, idea["pillar"], brand_pack)
        return ai_module.generate_draft(client, idea["topic"], tone, idea["pillar"], brand_pack, context=context)

    draft = _invoke(conn, idea_id, daily_cap_usd, "generate_draft", _generate, on_step=on_step)
```

(The rest of the function is unchanged.)

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (new tests plus every existing test, including `test_pipeline.py`).

- [ ] **Step 6: Commit**

```bash
git add content-creator/ai.py content-creator/pipeline.py content-creator/tests/test_draft_context.py
git commit -m "feat: add optional calendar context to draft generation"
```

---

### Task 2: Slot bridge (create idea from slot, status sync, slot context)

**Files:**
- Create: `content-creator/slot_bridge.py`
- Modify: `content-creator/calendar_store.py` (add `get_slot_by_idea`, `get_niche_date`)
- Test: `content-creator/tests/test_slot_bridge.py`

**Interfaces:**
- Consumes: `calendar_store.get_slot`, `set_slot_idea`, `update_slot_status`, `list_slots`, `add_slot`, `save_month_plan`, `save_niche_dates` (Content Calendar plan, Task 1); `db.create_idea`, `db.get_idea`.
- Cross-plan: content-calendar (final ticket)
- Produces: `calendar_store.get_slot_by_idea(conn, idea_id) -> dict | None`, `calendar_store.get_niche_date(conn, niche_date_id) -> dict | None` (with `ideas` list)
  - `slot_bridge.IDEA_TO_SLOT_STATUS: dict[str, str]`
  - `slot_bridge.create_idea_from_slot(conn, slot_id: int, brand_pack: str) -> int` (idempotent: reuses the linked idea unless it is missing, `rejected` or `archived`; otherwise creates an idea with `source_type="calendar"`, links it, sets the slot `in_production`)
  - `slot_bridge.sync_slot_status(conn, slot_id: int) -> str | None` (returns the new slot status, or `None` when nothing applies; never overwrites `published`; when the result is `planned` the idea link is cleared)
  - `slot_bridge.sync_month(conn, month_plan_id: int) -> int` (number of slots whose status changed)
  - `slot_bridge.slot_context(conn, slot: dict) -> dict` (only non-empty keys among `angle`, `funnel_phase`, `goal`, `cta_keyword`, `niche_date`)

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import calendar_store
import db
import slot_bridge


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    return connection


@pytest.fixture
def slot(conn):
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07")
    slot_id = calendar_store.add_slot(
        conn, plan_id, "brand", "2026-07-07", "post", "Educar", "Confiança", "build_authority",
        "3 hábitos para dormir", angle="guia prático", cta_keyword="GUIA",
    )
    return calendar_store.get_slot(conn, slot_id)


def test_create_idea_from_slot_prefills_and_links(conn, slot):
    idea_id = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    idea = db.get_idea(conn, idea_id)
    assert idea["topic"] == "3 hábitos para dormir" and idea["pillar"] == "Educar"
    assert idea["source_type"] == "calendar" and idea["status"] == "idea"
    linked = calendar_store.get_slot(conn, slot["id"])
    assert linked["idea_id"] == idea_id and linked["status"] == "in_production"
    assert calendar_store.get_slot_by_idea(conn, idea_id)["id"] == slot["id"]


def test_create_idea_from_slot_is_idempotent(conn, slot):
    first = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    second = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    assert first == second
    assert len(db.list_ideas(conn, brand_pack="brand")) == 1


def test_create_idea_from_slot_makes_a_fresh_idea_after_rejection(conn, slot):
    first = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    db.update_idea_status(conn, first, "rejected")
    second = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    assert second != first


@pytest.mark.parametrize("idea_status, expected", [
    ("idea", "in_production"), ("reviewed", "in_production"),
    ("approved", "ready"), ("images_ready", "ready"),
    ("rejected", "planned"), ("archived", "planned"),
])
def test_sync_slot_status_follows_the_idea(conn, slot, idea_status, expected):
    idea_id = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    db.update_idea_status(conn, idea_id, idea_status)
    assert slot_bridge.sync_slot_status(conn, slot["id"]) == expected
    synced = calendar_store.get_slot(conn, slot["id"])
    assert synced["status"] == expected
    assert (synced["idea_id"] is None) == (expected == "planned")


def test_sync_never_overwrites_published(conn, slot):
    idea_id = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    calendar_store.update_slot_status(conn, slot["id"], "published")
    db.update_idea_status(conn, idea_id, "approved")
    assert slot_bridge.sync_slot_status(conn, slot["id"]) is None
    assert calendar_store.get_slot(conn, slot["id"])["status"] == "published"


def test_sync_without_idea_does_nothing_and_deleted_idea_frees_the_slot(conn, slot):
    assert slot_bridge.sync_slot_status(conn, slot["id"]) is None
    idea_id = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    db.archive_idea(conn, idea_id)
    db.hard_delete_idea(conn, idea_id)
    assert slot_bridge.sync_slot_status(conn, slot["id"]) == "planned"


def test_sync_month_counts_changed_slots(conn, slot):
    idea_id = slot_bridge.create_idea_from_slot(conn, slot["id"], "brand")
    db.update_idea_status(conn, idea_id, "approved")
    assert slot_bridge.sync_month(conn, slot["month_plan_id"]) == 1
    assert slot_bridge.sync_month(conn, slot["month_plan_id"]) == 0


def test_slot_context_includes_only_filled_fields_and_niche_date(conn):
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07")
    nid = calendar_store.save_niche_dates(conn, "brand", "2026-07", [
        {"date": "2026-07-07", "name": "Portal 7/7", "why": "renovação", "ideas": [], "source": "pesquisa", "confidence": "média"},
    ])[0]
    slot_id = calendar_store.add_slot(conn, plan_id, "brand", "2026-07-07", "post", "P", "Confiança", None, "t",
                                      angle="a", niche_date_id=nid)
    ctx = slot_bridge.slot_context(conn, calendar_store.get_slot(conn, slot_id))
    assert ctx == {"angle": "a", "funnel_phase": "Confiança", "niche_date": "Portal 7/7: renovação"}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_slot_bridge.py -v`
Expected: FAIL (`ModuleNotFoundError: slot_bridge`).

- [ ] **Step 3: Add the two lookups to `calendar_store.py`**

```python
def get_slot_by_idea(conn, idea_id):
    return _slot_row(conn.execute("SELECT * FROM calendar_slots WHERE idea_id = ?", (idea_id,)).fetchone())


def get_niche_date(conn, niche_date_id):
    row = conn.execute("SELECT * FROM niche_dates WHERE id = ?", (niche_date_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["ideas"] = json.loads(item.pop("ideas_json"))
    return item
```

Note: `set_slot_idea(conn, slot_id, None)` must be allowed to clear the link (it already accepts any value).

- [ ] **Step 4: Implement `slot_bridge.py`**

```python
import calendar_store
import db

IDEA_TO_SLOT_STATUS = {
    "idea": "in_production", "reviewed": "in_production",
    "approved": "ready", "images_ready": "ready",
    "rejected": "planned", "archived": "planned",
}
_REUSABLE_IDEA_STATUSES = ("idea", "reviewed", "approved", "images_ready")


def create_idea_from_slot(conn, slot_id, brand_pack):
    slot = calendar_store.get_slot(conn, slot_id)
    if slot is None:
        raise ValueError(f"Não encontrei a publicação #{slot_id} no calendário.")
    if slot["idea_id"]:
        existing = db.get_idea(conn, slot["idea_id"])
        if existing and existing["status"] in _REUSABLE_IDEA_STATUSES:
            return existing["id"]
    idea_id = db.create_idea(conn, brand_pack, "calendar", slot["topic"], pillar=slot["pillar"])
    calendar_store.set_slot_idea(conn, slot_id, idea_id)
    calendar_store.update_slot_status(conn, slot_id, "in_production")
    return idea_id


def sync_slot_status(conn, slot_id):
    slot = calendar_store.get_slot(conn, slot_id)
    if slot is None or not slot["idea_id"] or slot["status"] == "published":
        return None
    idea = db.get_idea(conn, slot["idea_id"])
    new_status = IDEA_TO_SLOT_STATUS[idea["status"]] if idea else "planned"
    if new_status == "planned":
        calendar_store.set_slot_idea(conn, slot_id, None)
    if new_status != slot["status"] or new_status == "planned":
        calendar_store.update_slot_status(conn, slot_id, new_status)
    return new_status


def sync_month(conn, month_plan_id):
    changed = 0
    for slot in calendar_store.list_slots(conn, month_plan_id):
        before = (slot["status"], slot["idea_id"])
        sync_slot_status(conn, slot["id"])
        after = calendar_store.get_slot(conn, slot["id"])
        if (after["status"], after["idea_id"]) != before:
            changed += 1
    return changed


def slot_context(conn, slot):
    niche = calendar_store.get_niche_date(conn, slot["niche_date_id"]) if slot.get("niche_date_id") else None
    context = {
        "angle": slot.get("angle"),
        "funnel_phase": slot.get("funnel_phase"),
        "goal": slot.get("goal"),
        "cta_keyword": slot.get("cta_keyword"),
        "niche_date": f"{niche['name']}: {niche['why']}" if niche else None,
    }
    return {key: value for key, value in context.items() if value}
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add content-creator/slot_bridge.py content-creator/calendar_store.py content-creator/tests/test_slot_bridge.py
git commit -m "feat: add slot bridge (create idea from slot, status sync, slot context)"
```

---

### Task 3: Tone preferences, feedback revision and draft context builder

**Files:**
- Create: `content-creator/tone_prefs.py`, `content-creator/prompts/refine_with_feedback.md`
- Modify: `content-creator/ai.py` (add `refine_draft_with_feedback`), `content-creator/pipeline.py` (add `run_feedback_revision`), `content-creator/slot_bridge.py` (add `build_draft_context`)
- Test: `content-creator/tests/test_tone_prefs.py`, `content-creator/tests/test_feedback_revision.py`

**Interfaces:**
- Consumes: `ai.build_context_block` keys and `pipeline.run_generation_pipeline(..., context=...)` (Task 1); `slot_bridge.slot_context`, `calendar_store.get_slot_by_idea` (Task 2); `coach_store.list_findings` (Strategy Coach plan, Task 2); `tone_guard.GENTLE_TONE_RULE` (Strategy Coach plan, Task 1); `pipeline._invoke`, `db.list_drafts_for_idea`, `db.create_draft`, `db.update_draft_quality_flags`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `tone_prefs.init_schema(conn)`, `tone_prefs.add_preference(conn, brand_pack, note) -> bool` (ignores blank or duplicate notes; returns whether a row was added), `tone_prefs.list_preferences(conn, brand_pack, limit=5) -> list[str]` (the most recent `limit` notes, oldest first)
  - `ai.refine_draft_with_feedback(client, draft, feedback, preferences, brand_pack) -> tuple[dict, int, int, float]` (returns `{"caption","slides"}`)
  - `pipeline.run_feedback_revision(client, conn, idea, draft, feedback, brand_pack, daily_cap_usd, ai_module=ai, on_step=None) -> tuple[dict, list, int]` (`(revised_draft, flags, round)`; persists the new draft as the next round, re-runs `critique_draft`, stores its flags)
  - `slot_bridge.build_draft_context(conn, idea: dict) -> dict | None` (slot context + up to 6 Sherlock pattern descriptions from `coach_store.list_findings(conn, idea["brand_pack"])` + recent tone preferences; `None` when all three are empty)

- [ ] **Step 1: Create `prompts/refine_with_feedback.md`**

```
És um copywriter a ajustar um rascunho de carrossel de Instagram de acordo com o pedido da pessoa que o vai publicar.

{{TONE_RULE}}

Regras:
- Todo o output em Português Europeu (PT-PT).
- Faz apenas as alterações que o pedido exige; mantém a estrutura e o que já está bom.
- Respeita as preferências de tom da pessoa listadas abaixo.
- Responde APENAS com um objecto JSON válido, sem texto adicional, no formato:
{"caption": "...", "slides": ["...", "...", "..."]}

## Rascunho Actual
{{DRAFT_JSON}}

## Pedido da pessoa
{{FEEDBACK}}

## Preferências de tom anteriores
{{PREFERENCES}}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_tone_prefs.py`:

```python
import pytest

import db
import tone_prefs


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    tone_prefs.init_schema(connection)
    return connection


def test_add_and_list_preferences_recent_last(conn):
    for note in ("mais caloroso", "frases curtas", "menos emojis"):
        assert tone_prefs.add_preference(conn, "brand", note) is True
    assert tone_prefs.list_preferences(conn, "brand") == ["mais caloroso", "frases curtas", "menos emojis"]
    assert tone_prefs.list_preferences(conn, "brand", limit=2) == ["frases curtas", "menos emojis"]
    assert tone_prefs.list_preferences(conn, "other") == []


def test_blank_and_duplicate_notes_are_ignored(conn):
    assert tone_prefs.add_preference(conn, "brand", "   ") is False
    assert tone_prefs.add_preference(conn, "brand", "mais caloroso") is True
    assert tone_prefs.add_preference(conn, "brand", " Mais caloroso ") is False
    assert tone_prefs.list_preferences(conn, "brand") == ["mais caloroso"]
```

`tests/test_feedback_revision.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import calendar_store
import coach_store
import db
import pipeline
import slot_bridge
import tone_prefs


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    coach_store.init_schema(connection)
    tone_prefs.init_schema(connection)
    return connection


def fake_client(payload):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5), stop_reason="end_turn",
    )
    return client


def test_refine_draft_with_feedback_prompt_has_feedback_preferences_and_tone_rule():
    client = fake_client({"caption": "nova", "slides": ["a"]})
    draft, tin, tout, cost = ai.refine_draft_with_feedback(
        client, {"caption": "velha", "slides": ["x"]}, "mais caloroso", ["frases curtas"], "marianabotelho-ig",
    )
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "mais caloroso" in prompt and "frases curtas" in prompt and "velha" in prompt and "gentil" in prompt
    assert draft == {"caption": "nova", "slides": ["a"]} and cost > 0


class _FakeAI:
    MAX_REVISION_ROUNDS = 2

    def __init__(self):
        self.received = {}

    def refine_draft_with_feedback(self, client, draft, feedback, preferences, brand_pack):
        self.received.update(feedback=feedback, preferences=preferences)
        return {"caption": "revista", "slides": ["s1"]}, 5, 5, 0.001

    def critique_draft(self, client, draft, brand_pack):
        return [], 5, 5, 0.001


def test_run_feedback_revision_persists_next_round_critiques_and_uses_preferences(conn):
    idea_id = db.create_idea(conn, "brand", "manual", "tema", pillar="P")
    idea = db.get_idea(conn, idea_id)
    db.create_draft(conn, idea_id, 0, "original", ["a"], None)
    db.create_draft(conn, idea_id, 1, "primeira revisão", ["a"], None)
    tone_prefs.add_preference(conn, "brand", "frases curtas")
    fake = _FakeAI()
    draft, flags, round_ = pipeline.run_feedback_revision(
        None, conn, idea, {"caption": "primeira revisão", "slides": ["a"]}, "mais caloroso", "brand", 5.0, ai_module=fake,
    )
    assert draft["caption"] == "revista" and flags == [] and round_ == 2
    assert fake.received == {"feedback": "mais caloroso", "preferences": ["frases curtas"]}
    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert [d["round"] for d in drafts] == [0, 1, 2] and drafts[-1]["caption"] == "revista"
    functions = [r["function"] for r in conn.execute("SELECT function FROM api_calls ORDER BY id")]
    assert functions == ["refine_with_feedback", "critique_draft"]


def test_run_feedback_revision_respects_the_daily_cap(conn):
    idea_id = db.create_idea(conn, "brand", "manual", "tema")
    conn.execute("INSERT INTO api_calls (function, tokens_in, tokens_out, estimated_cost_usd, created_at) "
                 "VALUES ('x', 1, 1, 99.0, datetime('now'))")
    conn.commit()
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.run_feedback_revision(None, conn, db.get_idea(conn, idea_id), {"caption": "c", "slides": []},
                                       "x", "brand", 1.0, ai_module=_FakeAI())


def test_build_draft_context_combines_slot_patterns_and_preferences(conn):
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07")
    slot_id = calendar_store.add_slot(conn, plan_id, "brand", "2026-07-07", "post", "P", "Confiança", None, "t", angle="guia")
    idea_id = db.create_idea(conn, "brand", "calendar", "t", pillar="P")
    calendar_store.set_slot_idea(conn, slot_id, idea_id)
    coach_store.save_finding(conn, "brand", "x", "website", "resumo", [{"type": "hook", "description": "pergunta directa"}])
    tone_prefs.add_preference(conn, "brand", "mais caloroso")
    context = slot_bridge.build_draft_context(conn, db.get_idea(conn, idea_id))
    assert context["angle"] == "guia" and context["funnel_phase"] == "Confiança"
    assert context["patterns"] == ["pergunta directa"] and context["preferences"] == ["mais caloroso"]


def test_build_draft_context_is_none_when_there_is_nothing_to_add(conn):
    idea_id = db.create_idea(conn, "brand", "manual", "t")
    assert slot_bridge.build_draft_context(conn, db.get_idea(conn, idea_id)) is None
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_tone_prefs.py tests/test_feedback_revision.py -v`
Expected: FAIL (`ModuleNotFoundError: tone_prefs`).

- [ ] **Step 4: Implement `tone_prefs.py`**

```python
from datetime import datetime, timezone


def init_schema(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tone_preferences ("
        "id INTEGER PRIMARY KEY, brand_pack TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.commit()


def add_preference(conn, brand_pack, note):
    note = (note or "").strip()
    if not note:
        return False
    duplicate = conn.execute(
        "SELECT 1 FROM tone_preferences WHERE brand_pack = ? AND lower(note) = lower(?)", (brand_pack, note)
    ).fetchone()
    if duplicate:
        return False
    conn.execute(
        "INSERT INTO tone_preferences (brand_pack, note, created_at) VALUES (?, ?, ?)",
        (brand_pack, note, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return True


def list_preferences(conn, brand_pack, limit=5):
    rows = conn.execute(
        "SELECT note FROM (SELECT id, note FROM tone_preferences WHERE brand_pack = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
        (brand_pack, limit),
    ).fetchall()
    return [r["note"] for r in rows]
```

- [ ] **Step 5: Add `refine_draft_with_feedback` to `ai.py`** (add `from tone_guard import GENTLE_TONE_RULE` to the imports)

```python
def refine_draft_with_feedback(client, draft, feedback, preferences, brand_pack):
    prompt = render_prompt(
        load_prompt("refine_with_feedback"),
        tone_rule=GENTLE_TONE_RULE,
        draft_json=json.dumps(draft, ensure_ascii=False),
        feedback=feedback,
        preferences="; ".join(preferences) if preferences else "nenhuma ainda",
    )
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    revised = _parse_json_response(text)
    return revised, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)
```

- [ ] **Step 6: Add `run_feedback_revision` to `pipeline.py`** (add `import tone_prefs` to the imports)

```python
def run_feedback_revision(client, conn, idea, draft, feedback, brand_pack, daily_cap_usd, ai_module=ai, on_step=None):
    idea_id = idea["id"]
    preferences = tone_prefs.list_preferences(conn, brand_pack)
    revised = _invoke(
        conn, idea_id, daily_cap_usd, "refine_with_feedback",
        lambda: ai_module.refine_draft_with_feedback(client, draft, feedback, preferences, brand_pack),
        on_step=on_step,
    )
    previous_rounds = [d["round"] for d in db.list_drafts_for_idea(conn, idea_id)]
    round_ = (max(previous_rounds) + 1) if previous_rounds else 0
    draft_id = db.create_draft(conn, idea_id, round_, revised["caption"], revised["slides"], None)
    flags = _invoke(
        conn, idea_id, daily_cap_usd, "critique_draft",
        lambda: ai_module.critique_draft(client, revised, brand_pack),
        on_step=on_step,
    )
    db.update_draft_quality_flags(conn, draft_id, flags)
    return revised, flags, round_
```

- [ ] **Step 7: Add `build_draft_context` to `slot_bridge.py`** (add `import coach_store` and `import tone_prefs`)

```python
MAX_PATTERNS = 6


def build_draft_context(conn, idea):
    slot = calendar_store.get_slot_by_idea(conn, idea["id"])
    context = slot_context(conn, slot) if slot else {}
    patterns = [
        p["description"]
        for finding in coach_store.list_findings(conn, idea["brand_pack"])
        for p in finding["patterns"]
    ][:MAX_PATTERNS]
    if patterns:
        context["patterns"] = patterns
    preferences = tone_prefs.list_preferences(conn, idea["brand_pack"])
    if preferences:
        context["preferences"] = preferences
    return context or None
```

- [ ] **Step 8: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite).

- [ ] **Step 9: Commit**

```bash
git add content-creator/tone_prefs.py content-creator/prompts/refine_with_feedback.md content-creator/ai.py content-creator/pipeline.py content-creator/slot_bridge.py content-creator/tests/test_tone_prefs.py content-creator/tests/test_feedback_revision.py
git commit -m "feat: add tone preferences, feedback revision and draft context builder"
```

---

### Task 4: UI wiring ("Criar este post", pre-selection, feedback box, library dates)

**Files:**
- Create: `content-creator/ui_link.py`
- Modify: `content-creator/ui_calendar.py` (`_render_month_list`), `content-creator/app.py` (imports; schema init; the "Gerar rascunho" block ~lines 89-129; the result block ~lines 131-159; the Biblioteca expander label ~line 254)
- Test: `content-creator/tests/test_ui_link.py`

**Interfaces:**
- Consumes: `slot_bridge.create_idea_from_slot`, `slot_bridge.sync_month`, `slot_bridge.build_draft_context` (Task 2), (Task 3); `pipeline.run_feedback_revision`, `pipeline.run_generation_pipeline(..., context=)` (Task 1), (Task 3); `tone_prefs.add_preference`, `tone_prefs.init_schema` (Task 3); `calendar_store.get_slot_by_idea` (Task 2); `ui_calendar._render_month_list`, `ui_calendar.COPY` (Content Calendar plan, Task 6); `tone_guard.find_harsh_words`.
- Cross-plan: content-calendar (final ticket)
- Produces: `ui_link.COPY: dict[str, str]`
  - `ui_link.preselected_index(option_idea_ids: list[int], preselect_id: int | None) -> int` (index of `preselect_id` in the list, else `0`)
  - `ui_link.create_post_for_slot(conn, brand_pack: str, slot_id: int) -> int` (creates/reuses the idea and stores `st.session_state["preselect_idea_id"]`)
  - `ui_link.render_feedback_box(conn, cfg, client, run_with_progress, idea: dict, draft: dict) -> dict | None` (returns `{"draft","flags","rounds"}` after a revision, else `None`; appends the feedback text to `st.session_state["session_feedback"]`)
  - `ui_link.save_session_preferences(conn, brand_pack: str) -> None` (stores this session's feedback notes as tone preferences and clears them; call on approval)
  - `ui_link.slot_date_label(conn, idea_id: int) -> str` (`" · publicar a dd/mm"` when the idea belongs to a slot, else `""`)

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import calendar_store
import coach_store
import db
import tone_guard
import tone_prefs
import ui_link

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_copy_passes_the_tone_guard():
    for key, text in ui_link.COPY.items():
        assert tone_guard.find_harsh_words(text) == [], key


def test_preselected_index():
    assert ui_link.preselected_index([5, 7, 9], 7) == 1
    assert ui_link.preselected_index([5, 7, 9], 42) == 0
    assert ui_link.preselected_index([5, 7, 9], None) == 0
    assert ui_link.preselected_index([], 7) == 0


def test_slot_date_label_and_save_preferences():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    calendar_store.init_schema(conn)
    tone_prefs.init_schema(conn)
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    slot = calendar_store.add_slot(conn, plan, "brand", "2026-07-07", "post", "P", "F", None, "t")
    idea = db.create_idea(conn, "brand", "calendar", "t")
    calendar_store.set_slot_idea(conn, slot, idea)
    assert ui_link.slot_date_label(conn, idea) == " · publicar a 07/07"
    other = db.create_idea(conn, "brand", "manual", "x")
    assert ui_link.slot_date_label(conn, other) == ""


@pytest.fixture
def seeded_app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    conn = db.get_connection(db_path)
    db.init_db(conn)
    coach_store.init_schema(conn)
    calendar_store.init_schema(conn)
    tone_prefs.init_schema(conn)
    strategy = coach_store.create_strategy(conn, "marianabotelho-ig", profile={"who": "terapeuta", "goals": [], "offers": [], "sources": []})
    for kind in coach_store.SECTION_KINDS:
        coach_store.set_section(conn, strategy, kind, {"x": 1}, state="accepted")
    coach_store.mark_accepted(conn, strategy)
    month = date.today().strftime("%Y-%m")
    plan = calendar_store.save_month_plan(conn, "marianabotelho-ig", month, strategy_id=strategy, theme="Calma")
    slot = calendar_store.add_slot(conn, plan, "marianabotelho-ig", f"{month}-15", "post", "Educar", "Confiança", None, "3 hábitos para dormir")
    return conn, slot


def test_create_this_post_button_creates_the_idea_and_links_the_slot(seeded_app):
    conn, slot_id = seeded_app
    at = AppTest.from_file(APP_PATH)
    at.run()
    assert not at.exception
    at.button(key=f"create_post_{slot_id}").click().run()
    assert not at.exception
    slot = calendar_store.get_slot(conn, slot_id)
    assert slot["idea_id"] is not None and slot["status"] == "in_production"
    assert db.get_idea(conn, slot["idea_id"])["topic"] == "3 hábitos para dormir"
    assert at.session_state["preselect_idea_id"] == slot["idea_id"]


def test_new_idea_tab_preselects_the_idea_created_from_a_slot(seeded_app):
    conn, slot_id = seeded_app
    wanted = db.create_idea(conn, "marianabotelho-ig", "manual", "tema escolhido")
    db.create_idea(conn, "marianabotelho-ig", "manual", "outro tema")  # newer, so it is listed first by default
    at = AppTest.from_file(APP_PATH)
    at.session_state["preselect_idea_id"] = wanted
    at.run()
    assert not at.exception
    select = next(s for s in at.selectbox if s.label == "Ideia a rascunhar")
    assert select.value.startswith(f"#{wanted}")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_link.py -v`
Expected: FAIL (`ModuleNotFoundError: ui_link`).

- [ ] **Step 3: Implement `ui_link.py`**

```python
from datetime import date

import streamlit as st

import calendar_store
import pipeline
import slot_bridge
import tone_prefs

COPY = {
    "create_post": "Criar este post",
    "created": "Pronto! A ideia já está criada. Continua na aba Nova Ideia, no passo 3, onde ela já aparece escolhida.",
    "in_production": "Já está em produção. Podes continuar na aba Nova Ideia ou Gerar Imagens.",
    "feedback_label": "Queres ajustar alguma coisa? (por exemplo: mais caloroso, mais curto, com a minha voz)",
    "feedback_button": "Ajustar o rascunho",
    "budget": "Por hoje já usámos o orçamento definido. Retomamos amanhã, sem pressa.",
    "retry": "Não consegui ajustar desta vez. Podemos tentar de novo quando quiseres.",
}


def preselected_index(option_idea_ids, preselect_id):
    return option_idea_ids.index(preselect_id) if preselect_id in option_idea_ids else 0


def create_post_for_slot(conn, brand_pack, slot_id):
    idea_id = slot_bridge.create_idea_from_slot(conn, slot_id, brand_pack)
    st.session_state["preselect_idea_id"] = idea_id
    return idea_id


def slot_date_label(conn, idea_id):
    slot = calendar_store.get_slot_by_idea(conn, idea_id)
    if not slot:
        return ""
    return f" · publicar a {date.fromisoformat(slot['date']).strftime('%d/%m')}"


def save_session_preferences(conn, brand_pack):
    for note in st.session_state.pop("session_feedback", []):
        tone_prefs.add_preference(conn, brand_pack, note)


def render_feedback_box(conn, cfg, client, run_with_progress, idea, draft):
    feedback = st.text_input(COPY["feedback_label"], key=f"feedback_{idea['id']}")
    if st.button(COPY["feedback_button"], key=f"feedback_go_{idea['id']}") and feedback.strip():
        try:
            revised, flags, round_ = run_with_progress(
                pipeline.run_feedback_revision, client, conn, idea, draft, feedback.strip(),
                cfg.brand_pack, cfg.max_daily_spend_usd,
            )
        except pipeline.DailyBudgetExceededError:
            st.info(COPY["budget"])
            return None
        except Exception:
            st.info(COPY["retry"])
            return None
        st.session_state.setdefault("session_feedback", []).append(feedback.strip())
        return {"draft": revised, "flags": flags, "rounds": round_}
    return None
```

- [ ] **Step 4: Modify `ui_calendar._render_month_list`**

Add `import slot_bridge` and `import ui_link` at the top of `ui_calendar.py`. At the start of `_render_month_list`, after `plan = ...`, add `slot_bridge.sync_month(conn, plan["id"])`. Change the slot loop to (the function needs `brand_pack`, which it already receives):

```python
        for slot in group["slots"]:
            st.markdown(_describe_slot(slot))
            if slot["status"] == "planned":
                if st.button(ui_link.COPY["create_post"], key=f"create_post_{slot['id']}"):
                    ui_link.create_post_for_slot(conn, brand_pack, slot["id"])
                    st.success(ui_link.COPY["created"])
            elif slot["status"] == "in_production":
                st.caption(ui_link.COPY["in_production"])
```

Because `sync_month` runs before listing, slots are re-read via `calendar_store.list_slots` after the sync (keep the `list_slots` call after `sync_month`).

- [ ] **Step 5: Modify `app.py`**

1. Imports: add `import calendar_store`, `import slot_bridge`, `import tone_prefs`, `import ui_link` (skip any already present).
2. After the other `init_schema` calls add `tone_prefs.init_schema(conn)`.
3. In the "Gerar rascunho" block, replace the selectbox line with:

```python
        chosen_label = st.selectbox(
            "Ideia a rascunhar", list(options.keys()),
            index=ui_link.preselected_index([i["id"] for i in options.values()], st.session_state.get("preselect_idea_id")),
        )
```

4. In the same block change the pipeline call to also pass `context=slot_bridge.build_draft_context(conn, chosen_idea)` (a keyword argument on `run_with_progress(pipeline.run_generation_pipeline, client, conn, chosen_idea, tone, cfg.brand_pack, cfg.max_daily_spend_usd, context=...)`).
5. In the result block, after the flags warning and before the Aprovar/Rejeitar buttons, add:

```python
        revision = ui_link.render_feedback_box(conn, cfg, client, run_with_progress, idea, draft)
        if revision:
            st.session_state["current_result"] = {**result, **revision}
            st.rerun()
```

and inside the existing `if col1.button("Aprovar"):` branch, before `del st.session_state["current_result"]`, add `ui_link.save_session_preferences(conn, cfg.brand_pack)`.
6. In the Biblioteca expander label, append `+ ui_link.slot_date_label(conn, idea["id"])` inside the f-string label expression (if the look-and-feel status-pill change has already merged, keep the pill and only append the slot label).
7. Extend `STEP_LABELS` with `"refine_with_feedback": "A ajustar o rascunho"`.

- [ ] **Step 6: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite, including `test_app_smoke.py`).

- [ ] **Step 7: Commit**

```bash
git add content-creator/ui_link.py content-creator/ui_calendar.py content-creator/app.py content-creator/tests/test_ui_link.py
git commit -m "feat: link calendar slots to the post creator (create post, preselect, feedback, dates)"
```

---

## Final checklist (after all tasks are merged into `calendar-post-link`)

- [ ] Run the whole suite: `python -m pytest tests -q`.
- [ ] **One real, paid end-to-end run**: from a real calendar slot click "Criar este post", generate the draft in Nova Ideia (confirm the context block reaches the prompt), give plain-language feedback once, approve, generate images, and confirm the slot turns `ready` in the calendar. Record any bug the mocks missed in `content-creator/docs/decisions.md`.
- [ ] Read every new message for tone (gentle, no urgency).
- [ ] Final whole-branch review, then merge `calendar-post-link` into `main`.
