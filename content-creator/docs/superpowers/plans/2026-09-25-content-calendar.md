# Content Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the accepted strategy into a monthly content calendar (list view) with niche-date research, and let the user refine it in plain words.

**Architecture:** Flat modules at the `content-creator/` root. A deterministic layer (`calendar_plan.py`) builds the month skeleton (dates, formats, pillar and funnel-phase assignment, niche-date anchors); the AI only fills topics/angles/CTAs into that skeleton, so structure is always valid. State lives in `calendar_store.py` (own `init_schema`). Niche dates combine trustworthy computed astronomy data (`astronomy.py`, library `ephem`) with AI research that decides which kinds of dates matter for the user's niche.

**Tech Stack:** Python, Streamlit, Anthropic SDK, SQLite, `ephem`, pytest + `unittest.mock`.

**Spec:** `content-creator/docs/superpowers/specs/2026-09-25-content-calendar-design.md`

**Feature branch:** `content-calendar` (create from `main`; tickets branch off it as `ticket-<issue-number>`). Tasks 1-2 need nothing from other plans and can start immediately. Tickets with a `Cross-plan` line depend on the *final ticket* of the named plan: they only unblock after that plan has been reviewed and merged into `main`, and `main` has been merged into this feature branch.

**Test command (run from `content-creator/`):** `python -m pytest tests -q`

## Global Constraints

- All user-facing and AI-generated text is **PT-PT** and **gentle**: no urgency or blame; an empty week is an invitation, never an alarm. AI prompts that write user-facing text include `tone_guard.GENTLE_TONE_RULE`.
- Every AI call goes through `pipeline._invoke` (spend cap + cost logging).
- Nothing niche-specific is hard-coded: moon phases, portals and zodiac dates were only examples for a holistic niche. The AI decides which date types matter for the user's niche.
- Astronomy facts are computed, never invented by the AI; the AI only interprets relevance.
- v1 calendar UI is a **list view** (month grid is deferred; see backlog). No Markdown export.
- Formats: `post`, `carousel`, `reel`, `story`. Slot statuses: `planned`, `in_production`, `ready`, `published`. Month format is the string `YYYY-MM`; dates are ISO `YYYY-MM-DD` strings.
- Offer-heavy slots are capped per month (default 2).
- Accepted-strategy content shapes come from the Strategy Coach plan: `pillars = {"items": [{"name","percent","why"}]}`, `funnel = {"stages": [{"name","description"}]}`, `offers = {"items": [{"name","why"}]}`, `goals = {"ranked": [{"goal","rank","metric","target",...}]}`, `rhythm = {"posts_per_week","reels_per_week","stories_per_week","notes"}` (each section is wrapped as `{"content","state","evidence"}` by `coach_store.get_sections`).
- Do not modify existing `db.py` tables; new tables live in `calendar_store.py`.

---

### Task 1: Calendar store

**Files:**
- Create: `content-creator/calendar_store.py`
- Test: `content-creator/tests/test_calendar_store.py`

**Interfaces:**
- Consumes: nothing (a `sqlite3.Connection` from `db.get_connection`).
- Produces: `calendar_store.FORMATS = ("post","carousel","reel","story")`, `calendar_store.STATUSES = ("planned","in_production","ready","published")`
  - `calendar_store.init_schema(conn) -> None`
  - `calendar_store.save_month_plan(conn, brand_pack, month, strategy_id=None, theme=None, featured_offer=None, north_star=None) -> int` (upsert on `(brand_pack, month)`, returns id)
  - `calendar_store.get_month_plan(conn, brand_pack, month) -> dict | None`
  - `calendar_store.add_slot(conn, month_plan_id, brand_pack, date, format, pillar, funnel_phase, goal, topic, angle=None, cta_category=None, cta_keyword=None, offer_related=False, niche_date_id=None, notes=None) -> int`
  - `calendar_store.get_slot(conn, slot_id) -> dict | None`, `calendar_store.list_slots(conn, month_plan_id) -> list[dict]` (ordered by date then id; `offer_related` returned as `bool`)
  - `calendar_store.update_slot(conn, slot_id, **fields) -> None` (allowed fields: `date, format, pillar, funnel_phase, goal, topic, angle, cta_category, cta_keyword, offer_related, notes`; anything else raises `ValueError`)
  - `calendar_store.update_slot_status(conn, slot_id, status) -> None`, `calendar_store.set_slot_idea(conn, slot_id, idea_id) -> None`
  - `calendar_store.delete_slots(conn, month_plan_id, only_status=None) -> int`
  - `calendar_store.save_niche_dates(conn, brand_pack, month, dates) -> list[int]` (replaces existing rows for that brand+month whose decision is `proposed`; `dates` items: `{"date","name","why","ideas","source","confidence"}`)
  - `calendar_store.list_niche_dates(conn, brand_pack, month) -> list[dict]` (keys incl. `id`, `ideas: list`, `decision`)
  - `calendar_store.set_niche_date_decision(conn, niche_date_id, decision) -> None` (`proposed|accepted|skipped`)
  - `calendar_store.log_decision(conn, month_plan_id, action, reason=None, slot_id=None) -> None`, `calendar_store.list_decisions(conn, month_plan_id, limit=None) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import calendar_store
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    calendar_store.init_schema(connection)
    return connection


def make_slot(conn, plan_id, date="2026-07-07", **kw):
    args = dict(format="post", pillar="Educar", funnel_phase="consistência", goal="build_authority", topic="tema")
    args.update(kw)
    return calendar_store.add_slot(conn, plan_id, "brand", date, **args)


def test_save_month_plan_upserts_per_brand_and_month(conn):
    first = calendar_store.save_month_plan(conn, "brand", "2026-07", theme="Renascer")
    second = calendar_store.save_month_plan(conn, "brand", "2026-07", theme="Calma")
    assert first == second
    assert calendar_store.get_month_plan(conn, "brand", "2026-07")["theme"] == "Calma"
    assert calendar_store.get_month_plan(conn, "brand", "2026-08") is None


def test_slots_roundtrip_ordered_by_date_with_bool_offer_flag(conn):
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    make_slot(conn, plan, "2026-07-09", offer_related=True)
    make_slot(conn, plan, "2026-07-02")
    slots = calendar_store.list_slots(conn, plan)
    assert [s["date"] for s in slots] == ["2026-07-02", "2026-07-09"]
    assert slots[1]["offer_related"] is True and slots[0]["status"] == "planned"


def test_update_slot_only_allows_known_fields(conn):
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    sid = make_slot(conn, plan)
    calendar_store.update_slot(conn, sid, topic="novo tema", date="2026-07-10")
    assert calendar_store.get_slot(conn, sid)["topic"] == "novo tema"
    with pytest.raises(ValueError):
        calendar_store.update_slot(conn, sid, status="ready")
    with pytest.raises(ValueError):
        calendar_store.update_slot(conn, sid, id=99)


def test_status_and_idea_link(conn):
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    sid = make_slot(conn, plan)
    calendar_store.update_slot_status(conn, sid, "in_production")
    calendar_store.set_slot_idea(conn, sid, 42)
    slot = calendar_store.get_slot(conn, sid)
    assert slot["status"] == "in_production" and slot["idea_id"] == 42
    with pytest.raises(ValueError):
        calendar_store.update_slot_status(conn, sid, "nonsense")


def test_delete_slots_can_keep_non_planned(conn):
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    keep = make_slot(conn, plan)
    make_slot(conn, plan)
    calendar_store.update_slot_status(conn, keep, "in_production")
    assert calendar_store.delete_slots(conn, plan, only_status="planned") == 1
    assert [s["id"] for s in calendar_store.list_slots(conn, plan)] == [keep]


def test_niche_dates_replace_proposed_but_keep_decided(conn):
    dates = [{"date": "2026-07-07", "name": "Portal 7/7", "why": "energia", "ideas": ["a", "b"], "source": "pesquisa", "confidence": "média"}]
    ids = calendar_store.save_niche_dates(conn, "brand", "2026-07", dates)
    calendar_store.set_niche_date_decision(conn, ids[0], "accepted")
    calendar_store.save_niche_dates(conn, "brand", "2026-07", [
        {"date": "2026-07-14", "name": "Lua Nova", "why": "recomeços", "ideas": [], "source": "calculado", "confidence": "alta"},
    ])
    names = {d["name"]: d["decision"] for d in calendar_store.list_niche_dates(conn, "brand", "2026-07")}
    assert names == {"Portal 7/7": "accepted", "Lua Nova": "proposed"}
    assert calendar_store.list_niche_dates(conn, "brand", "2026-07")[0]["ideas"] == ["a", "b"]
    with pytest.raises(ValueError):
        calendar_store.set_niche_date_decision(conn, ids[0], "maybe")


def test_decisions_log(conn):
    plan = calendar_store.save_month_plan(conn, "brand", "2026-07")
    for i in range(3):
        calendar_store.log_decision(conn, plan, "edit", f"m{i}")
    assert [d["reason"] for d in calendar_store.list_decisions(conn, plan, limit=2)] == ["m1", "m2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_calendar_store.py -v`
Expected: FAIL (`ModuleNotFoundError: calendar_store`).

- [ ] **Step 3: Implement**

```python
import json
from datetime import datetime, timezone

FORMATS = ("post", "carousel", "reel", "story")
STATUSES = ("planned", "in_production", "ready", "published")
DECISIONS = ("proposed", "accepted", "skipped")
EDITABLE_FIELDS = (
    "date", "format", "pillar", "funnel_phase", "goal", "topic", "angle",
    "cta_category", "cta_keyword", "offer_related", "notes",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS month_plans (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            month TEXT NOT NULL,
            strategy_id INTEGER,
            theme TEXT,
            featured_offer TEXT,
            north_star TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (brand_pack, month)
        );
        CREATE TABLE IF NOT EXISTS calendar_slots (
            id INTEGER PRIMARY KEY,
            month_plan_id INTEGER NOT NULL REFERENCES month_plans(id),
            brand_pack TEXT NOT NULL,
            date TEXT NOT NULL,
            format TEXT NOT NULL,
            pillar TEXT,
            funnel_phase TEXT,
            goal TEXT,
            topic TEXT NOT NULL,
            angle TEXT,
            cta_category TEXT,
            cta_keyword TEXT,
            offer_related INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned',
            idea_id INTEGER,
            niche_date_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS niche_dates (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            month TEXT NOT NULL,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            why TEXT,
            ideas_json TEXT NOT NULL,
            source TEXT,
            confidence TEXT,
            decision TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS calendar_decisions (
            id INTEGER PRIMARY KEY,
            month_plan_id INTEGER NOT NULL REFERENCES month_plans(id),
            slot_id INTEGER,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def save_month_plan(conn, brand_pack, month, strategy_id=None, theme=None, featured_offer=None, north_star=None):
    conn.execute(
        "INSERT INTO month_plans (brand_pack, month, strategy_id, theme, featured_offer, north_star, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(brand_pack, month) DO UPDATE SET strategy_id = excluded.strategy_id, "
        "theme = excluded.theme, featured_offer = excluded.featured_offer, north_star = excluded.north_star",
        (brand_pack, month, strategy_id, theme, featured_offer, north_star, _now()),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM month_plans WHERE brand_pack = ? AND month = ?", (brand_pack, month)
    ).fetchone()["id"]


def get_month_plan(conn, brand_pack, month):
    row = conn.execute(
        "SELECT * FROM month_plans WHERE brand_pack = ? AND month = ?", (brand_pack, month)
    ).fetchone()
    return dict(row) if row else None


def add_slot(conn, month_plan_id, brand_pack, date, format, pillar, funnel_phase, goal, topic,
             angle=None, cta_category=None, cta_keyword=None, offer_related=False,
             niche_date_id=None, notes=None):
    if format not in FORMATS:
        raise ValueError(f"Unknown format: {format}")
    cursor = conn.execute(
        "INSERT INTO calendar_slots (month_plan_id, brand_pack, date, format, pillar, funnel_phase, goal, "
        "topic, angle, cta_category, cta_keyword, offer_related, niche_date_id, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (month_plan_id, brand_pack, date, format, pillar, funnel_phase, goal, topic, angle, cta_category,
         cta_keyword, 1 if offer_related else 0, niche_date_id, notes, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def _slot_row(row):
    if row is None:
        return None
    slot = dict(row)
    slot["offer_related"] = bool(slot["offer_related"])
    return slot


def get_slot(conn, slot_id):
    return _slot_row(conn.execute("SELECT * FROM calendar_slots WHERE id = ?", (slot_id,)).fetchone())


def list_slots(conn, month_plan_id):
    rows = conn.execute(
        "SELECT * FROM calendar_slots WHERE month_plan_id = ? ORDER BY date, id", (month_plan_id,)
    ).fetchall()
    return [_slot_row(r) for r in rows]


def update_slot(conn, slot_id, **fields):
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Fields not editable: {sorted(unknown)}")
    if not fields:
        return
    if "offer_related" in fields:
        fields["offer_related"] = 1 if fields["offer_related"] else 0
    assignments = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE calendar_slots SET {assignments} WHERE id = ?", (*fields.values(), slot_id))
    conn.commit()


def update_slot_status(conn, slot_id, status):
    if status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    conn.execute("UPDATE calendar_slots SET status = ? WHERE id = ?", (status, slot_id))
    conn.commit()


def set_slot_idea(conn, slot_id, idea_id):
    conn.execute("UPDATE calendar_slots SET idea_id = ? WHERE id = ?", (idea_id, slot_id))
    conn.commit()


def delete_slots(conn, month_plan_id, only_status=None):
    query, params = "DELETE FROM calendar_slots WHERE month_plan_id = ?", [month_plan_id]
    if only_status:
        query += " AND status = ?"
        params.append(only_status)
    cursor = conn.execute(query, params)
    conn.commit()
    return cursor.rowcount


def save_niche_dates(conn, brand_pack, month, dates):
    conn.execute(
        "DELETE FROM niche_dates WHERE brand_pack = ? AND month = ? AND decision = 'proposed'",
        (brand_pack, month),
    )
    ids = []
    for d in dates:
        cursor = conn.execute(
            "INSERT INTO niche_dates (brand_pack, month, date, name, why, ideas_json, source, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (brand_pack, month, d["date"], d["name"], d.get("why"), json.dumps(d.get("ideas", []), ensure_ascii=False),
             d.get("source"), d.get("confidence"), _now()),
        )
        ids.append(cursor.lastrowid)
    conn.commit()
    return ids


def list_niche_dates(conn, brand_pack, month):
    rows = conn.execute(
        "SELECT * FROM niche_dates WHERE brand_pack = ? AND month = ? ORDER BY date, id", (brand_pack, month)
    ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["ideas"] = json.loads(item.pop("ideas_json"))
        result.append(item)
    return result


def set_niche_date_decision(conn, niche_date_id, decision):
    if decision not in DECISIONS:
        raise ValueError(f"Unknown decision: {decision}")
    conn.execute("UPDATE niche_dates SET decision = ? WHERE id = ?", (decision, niche_date_id))
    conn.commit()


def log_decision(conn, month_plan_id, action, reason=None, slot_id=None):
    conn.execute(
        "INSERT INTO calendar_decisions (month_plan_id, slot_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (month_plan_id, slot_id, action, reason, _now()),
    )
    conn.commit()


def list_decisions(conn, month_plan_id, limit=None):
    if limit is None:
        rows = conn.execute(
            "SELECT * FROM calendar_decisions WHERE month_plan_id = ? ORDER BY id", (month_plan_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM calendar_decisions WHERE month_plan_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (month_plan_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_calendar_store.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/calendar_store.py content-creator/tests/test_calendar_store.py
git commit -m "feat: add calendar_store (month plans, slots, niche dates, decisions)"
```

---

### Task 2: Calendar planning maths (pure functions)

**Files:**
- Create: `content-creator/calendar_plan.py`
- Test: `content-creator/tests/test_calendar_plan.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `calendar_plan.DEFAULT_OFFER_CAP = 2`
  - `calendar_plan.month_days(month: str) -> list[date]`, `calendar_plan.weeks_of_month(month) -> list[list[date]]` (Mon-Sun weeks trimmed to the month)
  - `calendar_plan.build_skeleton(month: str, rhythm: dict) -> list[dict]` (each `{"date": ISO, "format": "post"|"reel"|"story"}`, sorted by date)
  - `calendar_plan.place_anchors(slots: list[dict], niche_dates: list[dict]) -> list[dict]` (`niche_dates` items need `id` and `date`; anchored slots get `niche_date_id`)
  - `calendar_plan.pillar_counts(n: int, pillars: list[dict]) -> dict[str, int]`, `calendar_plan.assign_pillars(slots, pillars) -> list[dict]` (adds `pillar`)
  - `calendar_plan.assign_funnel_phases(slots, stage_names: list[str]) -> list[dict]` (adds `funnel_phase`)
  - `calendar_plan.pick_featured_offer(offers: list[dict], month: str) -> str | None` (rotates quarterly)
  - `calendar_plan.north_star_metric(goals_content: dict) -> str | None`
  - `calendar_plan.count_offer_slots(slots) -> int`
  - `calendar_plan.upcoming_months(today: date, n: int = 3) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date

import calendar_plan

RHYTHM = {"posts_per_week": 3, "reels_per_week": 1, "stories_per_week": 5}


def test_month_days_and_weeks():
    days = calendar_plan.month_days("2026-07")
    assert len(days) == 31 and days[0] == date(2026, 7, 1)
    weeks = calendar_plan.weeks_of_month("2026-07")
    assert sum(len(w) for w in weeks) == 31
    assert weeks[0][0] == date(2026, 7, 1) and weeks[0][-1].weekday() == 6  # first week ends on Sunday
    assert all(d.month == 7 for w in weeks for d in w)


def test_skeleton_respects_weekly_rhythm_in_a_full_week():
    skeleton = calendar_plan.build_skeleton("2026-07", RHYTHM)
    full_week = [s for s in skeleton if "2026-07-06" <= s["date"] <= "2026-07-12"]
    counts = {f: sum(1 for s in full_week if s["format"] == f) for f in ("post", "reel", "story")}
    assert counts == {"post": 3, "reel": 1, "story": 5}
    assert all(s["date"].startswith("2026-07") for s in skeleton)
    assert skeleton == sorted(skeleton, key=lambda s: s["date"])


def test_skeleton_has_no_duplicate_date_and_format():
    skeleton = calendar_plan.build_skeleton("2026-07", RHYTHM)
    keys = [(s["date"], s["format"]) for s in skeleton]
    assert len(keys) == len(set(keys))


def test_place_anchors_moves_nearest_slot_onto_niche_date_and_keeps_count():
    skeleton = calendar_plan.build_skeleton("2026-07", RHYTHM)
    anchored = calendar_plan.place_anchors(skeleton, [{"id": 7, "date": "2026-07-07"}])
    assert len(anchored) == len(skeleton)
    on_day = [s for s in anchored if s["date"] == "2026-07-07"]
    assert any(s.get("niche_date_id") == 7 for s in on_day)
    assert anchored == sorted(anchored, key=lambda s: s["date"])


def test_place_anchors_does_not_anchor_two_dates_to_the_same_slot():
    skeleton = [{"date": "2026-07-01", "format": "post"}, {"date": "2026-07-02", "format": "post"}]
    anchored = calendar_plan.place_anchors(skeleton, [{"id": 1, "date": "2026-07-01"}, {"id": 2, "date": "2026-07-01"}])
    assert sorted(s["niche_date_id"] for s in anchored) == [1, 2]


def test_pillar_counts_follow_percentages_and_sum_to_n():
    pillars = [{"name": "A", "percent": 50}, {"name": "B", "percent": 30}, {"name": "C", "percent": 20}]
    assert calendar_plan.pillar_counts(10, pillars) == {"A": 5, "B": 3, "C": 2}
    assert sum(calendar_plan.pillar_counts(7, pillars).values()) == 7


def test_assign_pillars_matches_counts_and_avoids_long_runs():
    pillars = [{"name": "A", "percent": 50}, {"name": "B", "percent": 50}]
    slots = [{"date": f"2026-07-{d:02d}", "format": "post"} for d in range(1, 9)]
    assigned = calendar_plan.assign_pillars(slots, pillars)
    names = [s["pillar"] for s in assigned]
    assert names.count("A") == 4 and names.count("B") == 4
    assert all(names[i] != names[i + 1] for i in range(len(names) - 1))


def test_assign_funnel_phases_progress_through_the_month():
    slots = [{"date": f"2026-07-{d:02d}", "format": "post"} for d in range(1, 10)]
    phased = calendar_plan.assign_funnel_phases(slots, ["Descoberta", "Confiança", "Conversão"])
    assert [s["funnel_phase"] for s in phased] == ["Descoberta"] * 3 + ["Confiança"] * 3 + ["Conversão"] * 3
    assert calendar_plan.assign_funnel_phases([], ["x"]) == []


def test_pick_featured_offer_rotates_by_quarter():
    offers = [{"name": "Workshop"}, {"name": "Consulta"}]
    assert calendar_plan.pick_featured_offer(offers, "2026-02") == "Workshop"   # Q1
    assert calendar_plan.pick_featured_offer(offers, "2026-05") == "Consulta"   # Q2
    assert calendar_plan.pick_featured_offer(offers, "2026-08") == "Workshop"   # Q3
    assert calendar_plan.pick_featured_offer([], "2026-08") is None


def test_north_star_metric_uses_top_ranked_goal():
    goals = {"ranked": [{"rank": 1, "metric": "guardados por publicação", "target": "+40%"}]}
    assert calendar_plan.north_star_metric(goals) == "guardados por publicação (meta: +40%)"
    assert calendar_plan.north_star_metric({"ranked": []}) is None


def test_count_offer_slots_and_upcoming_months():
    assert calendar_plan.count_offer_slots([{"offer_related": True}, {"offer_related": False}, {}]) == 1
    assert calendar_plan.upcoming_months(date(2026, 11, 20), 3) == ["2026-11", "2026-12", "2027-01"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_calendar_plan.py -v`
Expected: FAIL (`ModuleNotFoundError: calendar_plan`).

- [ ] **Step 3: Implement**

```python
import calendar
from datetime import date

DEFAULT_OFFER_CAP = 2
FORMAT_ORDER = ("post", "carousel", "reel", "story")


def month_days(month):
    year, mon = (int(x) for x in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return [date(year, mon, d) for d in range(1, last + 1)]


def weeks_of_month(month):
    weeks, current = [], []
    for d in month_days(month):
        current.append(d)
        if d.weekday() == 6:
            weeks.append(current)
            current = []
    if current:
        weeks.append(current)
    return weeks


def _spread(days, count):
    count = max(0, min(count, len(days)))
    return [days[int((i + 0.5) * len(days) / count)] for i in range(count)]


def build_skeleton(month, rhythm):
    slots = []
    for week in weeks_of_month(month):
        scale = len(week) / 7
        for fmt, key, rotate in (
            ("post", "posts_per_week", 0), ("reel", "reels_per_week", 1), ("story", "stories_per_week", 0),
        ):
            days = week[rotate:] + week[:rotate]  # rotate reels so they don't always share days with posts
            for d in _spread(days, round(rhythm[key] * scale)):
                slots.append({"date": d.isoformat(), "format": fmt})
    return sorted(slots, key=lambda s: (s["date"], FORMAT_ORDER.index(s["format"])))


def place_anchors(slots, niche_dates):
    slots = [dict(s) for s in slots]
    taken = set()
    for nd in sorted(niche_dates, key=lambda d: d["date"]):
        target = date.fromisoformat(nd["date"])
        free = [i for i in range(len(slots)) if i not in taken]
        if not free:
            break
        same_day = [i for i in free if slots[i]["date"] == nd["date"]]
        pool = same_day or free
        best = min(pool, key=lambda i: abs((date.fromisoformat(slots[i]["date"]) - target).days))
        slots[best]["date"] = nd["date"]
        slots[best]["niche_date_id"] = nd["id"]
        taken.add(best)
    return sorted(slots, key=lambda s: (s["date"], FORMAT_ORDER.index(s["format"])))


def pillar_counts(n, pillars):
    raw = [p["percent"] * n / 100 for p in pillars]
    floors = [int(x) for x in raw]
    remainder = n - sum(floors)
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)[:remainder]:
        floors[i] += 1
    return {p["name"]: floors[i] for i, p in enumerate(pillars)}


def assign_pillars(slots, pillars):
    remaining = pillar_counts(len(slots), pillars)
    assigned, last = [], None
    for slot in slots:
        name = max(remaining, key=lambda k: (remaining[k], k != last))
        remaining[name] -= 1
        last = name
        assigned.append({**slot, "pillar": name})
    return assigned


def assign_funnel_phases(slots, stage_names):
    n = len(slots)
    return [
        {**s, "funnel_phase": stage_names[min(int(i * len(stage_names) / n), len(stage_names) - 1)]}
        for i, s in enumerate(slots)
    ]


def pick_featured_offer(offers, month):
    if not offers:
        return None
    quarter = (int(month.split("-")[1]) - 1) // 3
    return offers[quarter % len(offers)]["name"]


def north_star_metric(goals_content):
    ranked = goals_content.get("ranked") or []
    if not ranked:
        return None
    top = min(ranked, key=lambda g: g["rank"])
    return f"{top['metric']} (meta: {top['target']})"


def count_offer_slots(slots):
    return sum(1 for s in slots if s.get("offer_related"))


def upcoming_months(today, n=3):
    months, year, mon = [], today.year, today.month
    for _ in range(n):
        months.append(f"{year:04d}-{mon:02d}")
        mon += 1
        if mon > 12:
            mon, year = 1, year + 1
    return months
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_calendar_plan.py -v`
Expected: PASS (11 tests). If `test_skeleton_respects_weekly_rhythm_in_a_full_week` fails, fix the implementation (the rhythm counts per full week must be exact), not the test.

- [ ] **Step 5: Commit**

```bash
git add content-creator/calendar_plan.py content-creator/tests/test_calendar_plan.py
git commit -m "feat: add calendar planning maths (skeleton, anchors, pillars, funnel phases)"
```

---

### Task 3: Niche dates (computed astronomy + AI research)

**Files:**
- Create: `content-creator/astronomy.py`, `content-creator/niche_dates.py`, `content-creator/prompts/niche_dates.md`
- Modify: `content-creator/requirements.txt` (add `ephem>=4.1`)
- Test: `content-creator/tests/test_astronomy.py`, `content-creator/tests/test_niche_dates.py`

**Interfaces:**
- Consumes: `calendar_store.save_niche_dates`, `calendar_store.list_niche_dates` (Task 1); `tone_guard.GENTLE_TONE_RULE` (Strategy Coach plan, Task 1); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `astronomy.events_for_month(month: str) -> list[dict]` (each `{"date": ISO, "name": PT-PT name, "kind": "astronomy"}`; moon phases (`Lua Nova`, `Lua Cheia`, `Quarto Crescente`, `Quarto Minguante`), equinoxes (`Equinócio da Primavera`/`Equinócio de Outono`) and solstices (`Solstício de Verão`/`Solstício de Inverno`), northern hemisphere naming, dates in UTC)
  - `niche_dates.validate_niche_dates(items: list, month: str) -> list[dict]` (each `{"date","name","why","ideas": list[str],"source": "calculado"|"pesquisa","confidence": "alta"|"média"|"baixa"}`; dates must be inside the month)
  - `niche_dates.research_niche_dates(client, niche: str, month: str, computed: list[dict], brand_pack: str) -> tuple[list[dict], int, int, float]`
  - `niche_dates.propose_niche_dates(client, conn, brand_pack: str, niche: str, month: str, daily_cap_usd: float, refresh: bool = False, on_step=None, researcher=None, astronomy_fn=astronomy.events_for_month) -> list[dict]` (returns rows from `calendar_store.list_niche_dates`; cached per brand+month, no AI call when rows already exist unless `refresh=True`)

- [ ] **Step 1: Create `prompts/niche_dates.md`**

```
És uma investigadora de datas relevantes para o nicho de uma criadora de conteúdo. Nicho: {{NICHE}}. Mês: {{MONTH}} (formato AAAA-MM).

{{TONE_RULE}}

Primeiro decide que TIPOS de datas importam para este nicho (por exemplo: feriados, dias mundiais e de sensibilização, eventos do sector, estações do ano; e, se fizer sentido para o nicho, datas astrológicas ou energéticas como fases da lua, portais e trânsitos). Não assumas nenhum tipo à partida: só incluis o que for relevante para ESTE nicho.

Abaixo tens factos astronómicos calculados e fiáveis. Usa-os quando forem relevantes para o nicho (source "calculado") e nunca os inventes nem alteres as datas. Para tudo o resto usa source "pesquisa" e indica a tua confiança.

Factos calculados:
{{COMPUTED}}

Responde APENAS com um array JSON válido, sem texto adicional, com 3 a 10 itens:
[{"date": "AAAA-MM-DD", "name": "...", "why": "uma frase simples sobre porque importa a este nicho", "ideas": ["ideia de publicação 1", "ideia 2"], "source": "calculado" | "pesquisa", "confidence": "alta" | "média" | "baixa"}]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_astronomy.py`:

```python
import astronomy


def test_july_2026_has_new_and_full_moons_inside_the_month():
    events = astronomy.events_for_month("2026-07")
    names = {e["name"] for e in events}
    assert {"Lua Nova", "Lua Cheia"} <= names
    assert all(e["date"].startswith("2026-07") and e["kind"] == "astronomy" for e in events)


def test_june_2026_has_the_summer_solstice_around_the_21st():
    events = astronomy.events_for_month("2026-06")
    solstice = [e for e in events if e["name"] == "Solstício de Verão"]
    assert len(solstice) == 1 and solstice[0]["date"] in ("2026-06-20", "2026-06-21", "2026-06-22")


def test_september_2026_has_the_autumn_equinox():
    events = astronomy.events_for_month("2026-09")
    assert any(e["name"] == "Equinócio de Outono" for e in events)


def test_events_are_sorted_by_date():
    events = astronomy.events_for_month("2026-07")
    assert [e["date"] for e in events] == sorted(e["date"] for e in events)
```

`tests/test_niche_dates.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import calendar_store
import db
import niche_dates


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    return connection


ITEM = {"date": "2026-07-07", "name": "Portal 7/7", "why": "energia de renovação", "ideas": ["ritual simples"], "source": "pesquisa", "confidence": "média"}


def fake_client(payload):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=100, output_tokens=60), stop_reason="end_turn",
    )
    return client


def test_validate_accepts_good_items_and_rejects_dates_outside_month():
    assert niche_dates.validate_niche_dates([ITEM], "2026-07")[0]["name"] == "Portal 7/7"
    with pytest.raises(ai.InvalidAIResponseError):
        niche_dates.validate_niche_dates([{**ITEM, "date": "2026-08-01"}], "2026-07")


@pytest.mark.parametrize("patch", [{"source": "internet"}, {"confidence": "certa"}, {"ideas": "texto"}, {"name": ""}])
def test_validate_rejects_malformed_fields(patch):
    with pytest.raises(ai.InvalidAIResponseError):
        niche_dates.validate_niche_dates([{**ITEM, **patch}], "2026-07")


def test_research_prompt_contains_niche_computed_facts_and_tone_rule():
    client = fake_client([ITEM])
    computed = [{"date": "2026-07-14", "name": "Lua Nova", "kind": "astronomy"}]
    items, tin, tout, cost = niche_dates.research_niche_dates(client, "terapias holísticas", "2026-07", computed, "brand")
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "terapias holísticas" in prompt and "Lua Nova" in prompt and "gentil" in prompt
    assert items[0]["name"] == "Portal 7/7" and tin == 100 and cost > 0


def test_propose_saves_and_caches_per_month(conn):
    calls = []

    def researcher(client, niche, month, computed, brand_pack):
        calls.append(month)
        return [ITEM], 10, 5, 0.001

    kwargs = dict(researcher=researcher, astronomy_fn=lambda m: [])
    first = niche_dates.propose_niche_dates(MagicMock(), conn, "brand", "nicho", "2026-07", 2.0, **kwargs)
    second = niche_dates.propose_niche_dates(MagicMock(), conn, "brand", "nicho", "2026-07", 2.0, **kwargs)
    assert calls == ["2026-07"]
    assert [d["name"] for d in first] == [d["name"] for d in second] == ["Portal 7/7"]
    niche_dates.propose_niche_dates(MagicMock(), conn, "brand", "nicho", "2026-07", 2.0, refresh=True, **kwargs)
    assert calls == ["2026-07", "2026-07"]
    assert conn.execute("SELECT COUNT(*) FROM api_calls WHERE function = 'niche_dates'").fetchone()[0] == 2
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_astronomy.py tests/test_niche_dates.py -v`
Expected: FAIL (`ModuleNotFoundError: astronomy`). If `ephem` is missing run `pip install ephem` first (Step 4 adds it to requirements).

- [ ] **Step 4: Implement `astronomy.py` and add the dependency**

Append `ephem>=4.1` to `requirements.txt`.

```python
import calendar

import ephem

_MOON_PHASES = (
    ("Lua Nova", ephem.next_new_moon),
    ("Quarto Crescente", ephem.next_first_quarter_moon),
    ("Lua Cheia", ephem.next_full_moon),
    ("Quarto Minguante", ephem.next_last_quarter_moon),
)


def _iso(ephem_date):
    return ephem_date.datetime().date().isoformat()


def _range(month):
    year, mon = (int(x) for x in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-01", f"{year:04d}-{mon:02d}-{last:02d}", year, mon


def events_for_month(month):
    """Astronomical facts for the month (UTC dates, northern-hemisphere season names).
    Computed, never invented: the AI only decides whether they matter for a niche."""
    first, last, year, mon = _range(month)
    start = ephem.Date(ephem.Date(f"{year}/{mon}/1") - 1)  # day before, so nothing on day 1 is missed
    events = []
    for name, finder in _MOON_PHASES:
        cursor = start
        while True:
            cursor = finder(cursor)
            iso = _iso(cursor)
            if iso > last:
                break
            if iso >= first:
                events.append({"date": iso, "name": name, "kind": "astronomy"})
    for finder, names in (
        (ephem.next_equinox, {3: "Equinócio da Primavera", 9: "Equinócio de Outono"}),
        (ephem.next_solstice, {6: "Solstício de Verão", 12: "Solstício de Inverno"}),
    ):
        moment = finder(start)
        iso = _iso(moment)
        if first <= iso <= last and moment.datetime().month in names:
            events.append({"date": iso, "name": names[moment.datetime().month], "kind": "astronomy"})
    return sorted(events, key=lambda e: (e["date"], e["name"]))
```

- [ ] **Step 5: Implement `niche_dates.py`**

```python
import json

import ai
import astronomy
import calendar_store
import pipeline
from tone_guard import GENTLE_TONE_RULE

SOURCES = ("calculado", "pesquisa")
CONFIDENCES = ("alta", "média", "baixa")


def validate_niche_dates(items, month):
    if not isinstance(items, list):
        raise ai.InvalidAIResponseError("A pesquisa de datas não veio como uma lista.")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ai.InvalidAIResponseError("Uma das datas não tem nome.")
        if not isinstance(item.get("date"), str) or not item["date"].startswith(month):
            raise ai.InvalidAIResponseError(f"A data {item.get('date')!r} não está dentro do mês {month}.")
        if item.get("source") not in SOURCES or item.get("confidence") not in CONFIDENCES:
            raise ai.InvalidAIResponseError("A fonte ou a confiança de uma data é inválida.")
        if not isinstance(item.get("ideas"), list) or not all(isinstance(i, str) for i in item["ideas"]):
            raise ai.InvalidAIResponseError("As ideias de uma data têm de ser uma lista de textos.")
        item.setdefault("why", "")
    return items


def research_niche_dates(client, niche, month, computed, brand_pack):
    prompt = ai.render_prompt(
        ai.load_prompt("niche_dates"),
        niche=niche, month=month, tone_rule=GENTLE_TONE_RULE,
        computed=json.dumps(computed, ensure_ascii=False),
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    items = validate_niche_dates(ai._parse_json_response(text), month)
    return items, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def propose_niche_dates(client, conn, brand_pack, niche, month, daily_cap_usd, refresh=False,
                        on_step=None, researcher=None, astronomy_fn=astronomy.events_for_month):
    existing = calendar_store.list_niche_dates(conn, brand_pack, month)
    if existing and not refresh:
        return existing
    computed = astronomy_fn(month)
    items = pipeline._invoke(
        conn, None, daily_cap_usd, "niche_dates",
        lambda: (researcher or research_niche_dates)(client, niche, month, computed, brand_pack),
        on_step=on_step,
    )
    calendar_store.save_niche_dates(conn, brand_pack, month, items)
    return calendar_store.list_niche_dates(conn, brand_pack, month)
```

- [ ] **Step 6: Run to verify pass**

Run: `python -m pytest tests/test_astronomy.py tests/test_niche_dates.py -v`
Expected: PASS (4 + 7 tests). Also run the astronomy sanity check by eye once: `python -c "import astronomy; print(astronomy.events_for_month('2026-07'))"` and confirm the moon dates look plausible against any online moon calendar.

- [ ] **Step 7: Commit**

```bash
git add content-creator/astronomy.py content-creator/niche_dates.py content-creator/prompts/niche_dates.md content-creator/requirements.txt content-creator/tests/test_astronomy.py content-creator/tests/test_niche_dates.py
git commit -m "feat: add niche-date research (computed astronomy + AI relevance)"
```

---

### Task 4: Month generation

**Files:**
- Create: `content-creator/calendar_generate.py`, `content-creator/prompts/calendar_fill.md`
- Test: `content-creator/tests/test_calendar_generate.py`

**Interfaces:**
- Consumes: `calendar_store.*` (Task 1); `calendar_plan.*` (Task 2); niche-date dict shape `{"id","date","name","why","ideas","decision"}` (Task 3); `tone_guard.GENTLE_TONE_RULE` (Strategy Coach plan, Task 1); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `calendar_generate.CTA_CATEGORIES = ("services","education","community","products")`
  - `calendar_generate.MonthAlreadyPlanned(Exception)` with `.month`
  - `calendar_generate.validate_fill(data: dict, n_slots: int, offer_cap: int) -> dict` (raises `ai.InvalidAIResponseError`)
  - `calendar_generate.generate_month(client, conn, brand_pack: str, month: str, strategy_id: int, sections: dict, daily_cap_usd: float, niche_dates: list | None = None, findings: list | None = None, performance: dict | None = None, replace: bool = False, offer_cap: int = 2, on_step=None, filler=None) -> int` (returns `month_plan_id`; `sections` is the `coach_store.get_sections` shape; only `accepted` niche dates are anchored; with `replace=True` only `planned` slots are deleted)
  - `calendar_generate.add_niche_date_slot(conn, month_plan_id: int, brand_pack: str, niche_date: dict) -> int` (adds one `planned` slot on the niche date using its first idea as the topic)

- [ ] **Step 1: Create `prompts/calendar_fill.md`**

```
És uma estratega de conteúdo para redes sociais. Vais preencher o calendário de {{MONTH}} para uma pessoa que é ela própria o produto.

{{TONE_RULE}}

Recebes a estratégia aceite, os dados do mês e um esqueleto de publicações já com data, formato, pilar e fase do funil. NÃO alteres datas, formatos, pilares nem fases. Para cada publicação (identificada pelo seu "index") propõe tema, ângulo e CTA, e sugere um tema do mês.

Regras:
- Publicações ligadas a uma data do nicho ("niche_date") devem aproveitar essa data.
- Máximo de {{OFFER_CAP}} publicações com "offer_related": true no mês inteiro (as que promovem directamente uma oferta). A oferta em destaque do trimestre é: {{FEATURED_OFFER}}.
- O que o mês procura melhorar (métrica principal): {{NORTH_STAR}}.
- Usa os padrões de perfis de referência apenas como inspiração de estrutura; nunca copies conteúdo.
- "cta_category" é um de: services, education, community, products. "cta_keyword" é uma palavra curta que a pessoa pode comentar para receber mais informação.
- "goal" é uma das chaves de objectivo da estratégia.

Responde APENAS com um objecto JSON válido, sem texto adicional:
{"theme": "tema do mês", "slots": [{"index": 0, "topic": "...", "angle": "...", "cta_category": "...", "cta_keyword": "...", "goal": "...", "offer_related": false}]}
```

- [ ] **Step 2: Write the failing tests**

```python
import json
from unittest.mock import MagicMock

import pytest

import ai
import calendar_generate
import calendar_store
import db

SECTIONS = {
    "goals": {"content": {"ranked": [{"goal": "build_authority", "rank": 1, "metric": "guardados", "target": "+40%"}]}, "state": "accepted", "evidence": "reasoned"},
    "offers": {"content": {"items": [{"name": "Workshop", "why": "w"}, {"name": "Consulta", "why": "c"}]}, "state": "accepted", "evidence": "reasoned"},
    "funnel": {"content": {"stages": [{"name": "Descoberta", "description": "d"}, {"name": "Conversão", "description": "c"}]}, "state": "accepted", "evidence": "reasoned"},
    "pillars": {"content": {"items": [{"name": "Educar", "percent": 60, "why": ""}, {"name": "Bastidores", "percent": 40, "why": ""}]}, "state": "accepted", "evidence": "reasoned"},
    "authority": {"content": {"items": []}, "state": "accepted", "evidence": "reasoned"},
    "rhythm": {"content": {"posts_per_week": 2, "reels_per_week": 1, "stories_per_week": 0, "notes": ""}, "state": "accepted", "evidence": "reasoned"},
}


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    return connection


def make_filler(offer_flags=None):
    seen = {}

    def filler(client, brand_pack, month, sections, skeleton, meta, niche_dates, findings, performance):
        seen.update(skeleton=skeleton, meta=meta, niche=niche_dates, performance=performance)
        flags = offer_flags or [False] * len(skeleton)
        return {
            "theme": "Recomeços",
            "slots": [
                {"index": i, "topic": f"tema {i}", "angle": "a", "cta_category": "education",
                 "cta_keyword": "GUIA", "goal": "build_authority", "offer_related": flags[i]}
                for i in range(len(skeleton))
            ],
        }, 100, 50, 0.002

    return filler, seen


def test_validate_fill_checks_indices_categories_and_offer_cap():
    good = {"theme": "t", "slots": [{"index": 0, "topic": "x", "angle": "a", "cta_category": "services", "cta_keyword": "K", "goal": "g", "offer_related": True}]}
    assert calendar_generate.validate_fill(good, 1, 2) is good
    with pytest.raises(ai.InvalidAIResponseError):
        calendar_generate.validate_fill(good, 2, 2)  # wrong slot count
    bad_cat = json.loads(json.dumps(good)); bad_cat["slots"][0]["cta_category"] = "spam"
    with pytest.raises(ai.InvalidAIResponseError):
        calendar_generate.validate_fill(bad_cat, 1, 2)
    over = {"theme": "t", "slots": [
        {"index": i, "topic": "x", "angle": "a", "cta_category": "services", "cta_keyword": "K", "goal": "g", "offer_related": True} for i in range(3)]}
    with pytest.raises(ai.InvalidAIResponseError):
        calendar_generate.validate_fill(over, 3, 2)


def test_generate_month_persists_plan_and_slots_from_skeleton(conn):
    filler, seen = make_filler()
    plan_id = calendar_generate.generate_month(
        MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, filler=filler,
    )
    plan = calendar_store.get_month_plan(conn, "brand", "2026-07")
    assert plan["id"] == plan_id and plan["theme"] == "Recomeços"
    assert plan["featured_offer"] == "Workshop"  # July is Q3 -> index 2 % 2 = 0
    assert plan["north_star"] == "guardados (meta: +40%)"
    slots = calendar_store.list_slots(conn, plan_id)
    assert len(slots) == len(seen["skeleton"]) and all(s["status"] == "planned" for s in slots)
    assert {s["pillar"] for s in slots} == {"Educar", "Bastidores"}
    assert {s["funnel_phase"] for s in slots} == {"Descoberta", "Conversão"}
    assert conn.execute("SELECT COUNT(*) FROM api_calls WHERE function = 'calendar_fill'").fetchone()[0] == 1


def test_generate_month_anchors_only_accepted_niche_dates(conn):
    filler, seen = make_filler()
    niche = [
        {"id": 1, "date": "2026-07-07", "name": "Portal 7/7", "why": "w", "ideas": [], "decision": "accepted"},
        {"id": 2, "date": "2026-07-20", "name": "Outra", "why": "w", "ideas": [], "decision": "skipped"},
    ]
    calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, niche_dates=niche, filler=filler)
    anchored = [s for s in seen["skeleton"] if s.get("niche_date_id")]
    assert [s["niche_date_id"] for s in anchored] == [1] and anchored[0]["date"] == "2026-07-07"


def test_generate_month_refuses_to_overwrite_unless_replace(conn):
    filler, _ = make_filler()
    calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, filler=filler)
    with pytest.raises(calendar_generate.MonthAlreadyPlanned):
        calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, filler=filler)


def test_replace_keeps_slots_already_in_production(conn):
    filler, _ = make_filler()
    plan_id = calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, filler=filler)
    locked = calendar_store.list_slots(conn, plan_id)[0]["id"]
    calendar_store.update_slot_status(conn, locked, "in_production")
    calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0, replace=True, filler=filler)
    statuses = [s["status"] for s in calendar_store.list_slots(conn, plan_id)]
    assert statuses.count("in_production") == 1


def test_performance_hints_reach_the_filler(conn):
    filler, seen = make_filler()
    calendar_generate.generate_month(MagicMock(), conn, "brand", "2026-07", 1, SECTIONS, 2.0,
                                     performance={"best_pillar": "Educar"}, filler=filler)
    assert seen["performance"] == {"best_pillar": "Educar"}


def test_add_niche_date_slot_uses_first_idea(conn):
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07")
    slot_id = calendar_generate.add_niche_date_slot(
        conn, plan_id, "brand", {"id": 5, "date": "2026-07-07", "name": "Portal 7/7", "ideas": ["ritual simples"]},
    )
    slot = calendar_store.get_slot(conn, slot_id)
    assert slot["topic"] == "ritual simples" and slot["niche_date_id"] == 5 and slot["date"] == "2026-07-07"
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_calendar_generate.py -v`
Expected: FAIL (`ModuleNotFoundError: calendar_generate`).

- [ ] **Step 4: Implement `calendar_generate.py`**

```python
import json

import ai
import calendar_plan
import calendar_store
import pipeline
from tone_guard import GENTLE_TONE_RULE

CTA_CATEGORIES = ("services", "education", "community", "products")


class MonthAlreadyPlanned(Exception):
    def __init__(self, month):
        self.month = month
        super().__init__(f"O mês {month} já tem um plano. Podemos ajustá-lo ou recomeçar as publicações ainda por fazer.")


def validate_fill(data, n_slots, offer_cap):
    if not isinstance(data, dict) or not isinstance(data.get("theme"), str) or not isinstance(data.get("slots"), list):
        raise ai.InvalidAIResponseError("O plano do mês não veio no formato esperado.")
    slots = data["slots"]
    if sorted(s.get("index") for s in slots if isinstance(s, dict)) != list(range(n_slots)):
        raise ai.InvalidAIResponseError("O plano não trouxe uma proposta para cada publicação.")
    for s in slots:
        if not isinstance(s.get("topic"), str) or not s["topic"].strip():
            raise ai.InvalidAIResponseError("Uma publicação ficou sem tema.")
        if s.get("cta_category") not in CTA_CATEGORIES:
            raise ai.InvalidAIResponseError("Uma publicação tem uma categoria de CTA inválida.")
        if not isinstance(s.get("offer_related"), bool):
            raise ai.InvalidAIResponseError("Falta indicar se a publicação promove uma oferta.")
    if sum(1 for s in slots if s["offer_related"]) > offer_cap:
        raise ai.InvalidAIResponseError(f"O plano tem mais de {offer_cap} publicações de oferta neste mês.")
    return data


def fill_slots(client, brand_pack, month, sections, skeleton, meta, niche_dates, findings, performance):
    prompt = ai.render_prompt(
        ai.load_prompt("calendar_fill"),
        month=month, tone_rule=GENTLE_TONE_RULE, offer_cap=str(meta["offer_cap"]),
        featured_offer=meta["featured_offer"] or "nenhuma", north_star=meta["north_star"] or "não definida",
    )
    strategy = {kind: sections[kind]["content"] for kind in sections}
    numbered = [{"index": i, **s} for i, s in enumerate(skeleton)]
    niche_by_id = {d["id"]: {"name": d["name"], "why": d.get("why"), "ideas": d.get("ideas", [])} for d in niche_dates}
    for s in numbered:
        if s.get("niche_date_id") in niche_by_id:
            s["niche_date"] = niche_by_id[s["niche_date_id"]]
    prompt = (
        f"{prompt}\n\n## Estratégia aceite\n{json.dumps(strategy, ensure_ascii=False)}"
        f"\n\n## Esqueleto do mês\n{json.dumps(numbered, ensure_ascii=False)}"
        f"\n\n## Padrões de perfis de referência\n{json.dumps(findings, ensure_ascii=False)}"
        f"\n\n## O que funcionou no mês anterior\n{json.dumps(performance, ensure_ascii=False)}"
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    data = validate_fill(ai._parse_json_response(text), len(skeleton), meta["offer_cap"])
    return data, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def generate_month(client, conn, brand_pack, month, strategy_id, sections, daily_cap_usd,
                   niche_dates=None, findings=None, performance=None, replace=False,
                   offer_cap=calendar_plan.DEFAULT_OFFER_CAP, on_step=None, filler=None):
    existing = calendar_store.get_month_plan(conn, brand_pack, month)
    if existing and calendar_store.list_slots(conn, existing["id"]) and not replace:
        raise MonthAlreadyPlanned(month)

    accepted = [d for d in (niche_dates or []) if d.get("decision") == "accepted"]
    pillars = sections["pillars"]["content"]["items"]
    stages = [s["name"] for s in sections["funnel"]["content"]["stages"]]
    skeleton = calendar_plan.build_skeleton(month, sections["rhythm"]["content"])
    skeleton = calendar_plan.place_anchors(skeleton, accepted)
    skeleton = calendar_plan.assign_pillars(skeleton, pillars)
    skeleton = calendar_plan.assign_funnel_phases(skeleton, stages)
    meta = {
        "featured_offer": calendar_plan.pick_featured_offer(sections["offers"]["content"]["items"], month),
        "north_star": calendar_plan.north_star_metric(sections["goals"]["content"]),
        "offer_cap": offer_cap,
    }
    fill = pipeline._invoke(
        conn, None, daily_cap_usd, "calendar_fill",
        lambda: (filler or fill_slots)(client, brand_pack, month, sections, skeleton, meta, accepted,
                                       findings or [], performance),
        on_step=on_step,
    )
    plan_id = calendar_store.save_month_plan(
        conn, brand_pack, month, strategy_id=strategy_id, theme=fill["theme"],
        featured_offer=meta["featured_offer"], north_star=meta["north_star"],
    )
    if replace:
        calendar_store.delete_slots(conn, plan_id, only_status="planned")
    by_index = {s["index"]: s for s in fill["slots"]}
    for i, slot in enumerate(skeleton):
        filled = by_index[i]
        calendar_store.add_slot(
            conn, plan_id, brand_pack, slot["date"], slot["format"], slot["pillar"], slot["funnel_phase"],
            filled.get("goal"), filled["topic"], angle=filled.get("angle"),
            cta_category=filled["cta_category"], cta_keyword=filled.get("cta_keyword"),
            offer_related=filled["offer_related"], niche_date_id=slot.get("niche_date_id"),
        )
    return plan_id


def add_niche_date_slot(conn, month_plan_id, brand_pack, niche_date):
    ideas = niche_date.get("ideas") or []
    return calendar_store.add_slot(
        conn, month_plan_id, brand_pack, niche_date["date"], "post", None, None, None,
        ideas[0] if ideas else niche_date["name"], angle=niche_date.get("why"),
        niche_date_id=niche_date["id"],
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_calendar_generate.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/calendar_generate.py content-creator/prompts/calendar_fill.md content-creator/tests/test_calendar_generate.py
git commit -m "feat: add month generation (deterministic skeleton + AI-filled topics)"
```

---

### Task 5: Calendar refinement loop

**Files:**
- Create: `content-creator/calendar_refine.py`, `content-creator/prompts/calendar_refine.md`
- Test: `content-creator/tests/test_calendar_refine.py`

**Interfaces:**
- Consumes: `calendar_store.*` (Task 1); `calendar_plan.month_days` (Task 2); `tone_guard.GENTLE_TONE_RULE` (Strategy Coach plan, Task 1); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `calendar_refine.validate_changes(data: dict, editable_ids: set[int], month: str) -> dict` (raises `ai.InvalidAIResponseError`)
  - `calendar_refine.refine_month(client, conn, brand_pack: str, month: str, user_text: str, daily_cap_usd: float, on_step=None, reviser=None) -> list[int]` (ids of changed slots; only `planned` slots can change; logs a decision; may update the theme)

- [ ] **Step 1: Create `prompts/calendar_refine.md`**

```
Estás a ajustar o calendário de conteúdo de {{MONTH}} de acordo com o pedido da pessoa.

{{TONE_RULE}}

Só podes alterar as publicações listadas em "editáveis" (as outras já estão em produção e ficam como estão). Mantém as alterações mínimas: muda apenas o que o pedido exige. Respeita as decisões anteriores da pessoa.

Pedido: {{USER_TEXT}}
Decisões anteriores: {{DECISIONS}}

Responde APENAS com um objecto JSON válido, sem texto adicional:
{"theme": "novo tema do mês ou null", "changes": [{"id": 12, "date": "AAAA-MM-DD", "format": "post|carousel|reel|story", "pillar": "...", "topic": "...", "angle": "...", "cta_keyword": "..."}]}
Em cada alteração inclui "id" e apenas os campos que mudam.
```

- [ ] **Step 2: Write the failing tests**

```python
from unittest.mock import MagicMock

import pytest

import ai
import calendar_refine
import calendar_store
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    return connection


@pytest.fixture
def plan(conn):
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07", theme="Recomeços")
    ids = [
        calendar_store.add_slot(conn, plan_id, "brand", f"2026-07-{d:02d}", "post", "Educar", "Descoberta", "g", f"tema {d}")
        for d in (2, 9, 16)
    ]
    return plan_id, ids


def test_validate_changes_rejects_unknown_ids_bad_dates_and_bad_formats():
    ok = {"theme": None, "changes": [{"id": 1, "topic": "novo"}]}
    assert calendar_refine.validate_changes(ok, {1, 2}, "2026-07") is ok
    for bad in (
        {"theme": None, "changes": [{"id": 3, "topic": "x"}]},
        {"theme": None, "changes": [{"id": 1, "date": "2026-08-01"}]},
        {"theme": None, "changes": [{"id": 1, "format": "podcast"}]},
        {"theme": None, "changes": [{"id": 1, "status": "ready"}]},
        {"changes": "nada"},
    ):
        with pytest.raises(ai.InvalidAIResponseError):
            calendar_refine.validate_changes(bad, {1, 2}, "2026-07")


def test_refine_month_applies_changes_theme_and_logs_decision(conn, plan):
    plan_id, ids = plan

    def reviser(client, month, editable, decisions, user_text, brand_pack):
        assert user_text == "menos posts nesta semana" and len(editable) == 3
        return {"theme": "Calma", "changes": [{"id": ids[1], "format": "reel", "topic": "novo tema"}]}, 10, 5, 0.001

    changed = calendar_refine.refine_month(MagicMock(), conn, "brand", "2026-07", "menos posts nesta semana", 2.0, reviser=reviser)
    assert changed == [ids[1]]
    slot = calendar_store.get_slot(conn, ids[1])
    assert slot["format"] == "reel" and slot["topic"] == "novo tema"
    assert calendar_store.get_month_plan(conn, "brand", "2026-07")["theme"] == "Calma"
    assert calendar_store.list_decisions(conn, plan_id)[-1]["reason"] == "menos posts nesta semana"


def test_refine_month_never_touches_slots_in_production(conn, plan):
    plan_id, ids = plan
    calendar_store.update_slot_status(conn, ids[0], "in_production")
    seen = {}

    def reviser(client, month, editable, decisions, user_text, brand_pack):
        seen["editable"] = [s["id"] for s in editable]
        return {"theme": None, "changes": [{"id": ids[0], "topic": "tentar mudar"}]}, 1, 1, 0.0

    with pytest.raises(ai.InvalidAIResponseError):
        calendar_refine.refine_month(MagicMock(), conn, "brand", "2026-07", "muda tudo", 2.0, reviser=reviser)
    assert ids[0] not in seen["editable"]
    assert calendar_store.get_slot(conn, ids[0])["topic"] == "tema 2"


def test_refine_month_without_a_plan_raises_a_friendly_error(conn):
    with pytest.raises(ValueError):
        calendar_refine.refine_month(MagicMock(), conn, "brand", "2026-07", "x", 2.0, reviser=lambda *a: None)
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_calendar_refine.py -v`
Expected: FAIL (`ModuleNotFoundError: calendar_refine`).

- [ ] **Step 4: Implement `calendar_refine.py`**

```python
import json

import ai
import calendar_plan
import calendar_store
import pipeline
from tone_guard import GENTLE_TONE_RULE

CHANGE_FIELDS = {"id", "date", "format", "pillar", "topic", "angle", "cta_keyword"}


def validate_changes(data, editable_ids, month):
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise ai.InvalidAIResponseError("O ajuste ao calendário não veio no formato esperado.")
    valid_dates = {d.isoformat() for d in calendar_plan.month_days(month)}
    for change in data["changes"]:
        if not isinstance(change, dict) or change.get("id") not in editable_ids:
            raise ai.InvalidAIResponseError("O ajuste refere-se a uma publicação que não pode ser alterada.")
        if set(change) - CHANGE_FIELDS:
            raise ai.InvalidAIResponseError("O ajuste tenta mudar um campo que não é editável.")
        if "date" in change and change["date"] not in valid_dates:
            raise ai.InvalidAIResponseError("O ajuste usa uma data fora do mês.")
        if "format" in change and change["format"] not in calendar_store.FORMATS:
            raise ai.InvalidAIResponseError("O ajuste usa um formato desconhecido.")
    return data


def revise_slots(client, month, editable, decisions, user_text, brand_pack):
    prompt = ai.render_prompt(
        ai.load_prompt("calendar_refine"),
        month=month, tone_rule=GENTLE_TONE_RULE, user_text=user_text,
        decisions=json.dumps(decisions, ensure_ascii=False),
    )
    slim = [{k: s[k] for k in ("id", "date", "format", "pillar", "funnel_phase", "topic", "angle", "cta_keyword")} for s in editable]
    prompt = f"{prompt}\n\n## Editáveis\n{json.dumps(slim, ensure_ascii=False)}"
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    data = ai._parse_json_response(text)
    return data, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def refine_month(client, conn, brand_pack, month, user_text, daily_cap_usd, on_step=None, reviser=None):
    plan = calendar_store.get_month_plan(conn, brand_pack, month)
    if plan is None:
        raise ValueError("Ainda não há um plano para este mês. Vamos criá-lo primeiro.")
    editable = [s for s in calendar_store.list_slots(conn, plan["id"]) if s["status"] == "planned"]
    decisions = [
        {"action": d["action"], "reason": d["reason"]}
        for d in calendar_store.list_decisions(conn, plan["id"], limit=10)
    ]
    data = pipeline._invoke(
        conn, None, daily_cap_usd, "calendar_refine",
        lambda: (reviser or revise_slots)(client, month, editable, decisions, user_text, brand_pack),
        on_step=on_step,
    )
    validate_changes(data, {s["id"] for s in editable}, month)
    changed = []
    for change in data["changes"]:
        fields = {k: v for k, v in change.items() if k != "id"}
        calendar_store.update_slot(conn, change["id"], **fields)
        changed.append(change["id"])
    if data.get("theme"):
        calendar_store.save_month_plan(
            conn, brand_pack, month, strategy_id=plan["strategy_id"], theme=data["theme"],
            featured_offer=plan["featured_offer"], north_star=plan["north_star"],
        )
    calendar_store.log_decision(conn, plan["id"], "edit", user_text)
    return changed
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_calendar_refine.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/calendar_refine.py content-creator/prompts/calendar_refine.md content-creator/tests/test_calendar_refine.py
git commit -m "feat: add calendar refinement loop (plain-language changes to planned slots)"
```

---

### Task 6: Calendar tab (list view) and app wiring

**Files:**
- Create: `content-creator/ui_calendar.py`
- Modify: `content-creator/app.py` (imports; init schema after `db.init_db(conn)`; `STEP_LABELS`; tab list; tab block at end)
- Test: `content-creator/tests/test_ui_calendar.py`

**Interfaces:**
- Consumes: `calendar_store.*` (Task 1); `calendar_plan.upcoming_months`, `calendar_plan.weeks_of_month` (Task 2); `calendar_generate.generate_month`, `calendar_generate.MonthAlreadyPlanned` (Task 4); `calendar_refine.refine_month` (Task 5); `coach_store.latest_strategy`, `coach_store.get_sections`, `coach_store.list_findings` (Strategy Coach plan, Task 2); `tone_guard.find_harsh_words`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `ui_calendar.COPY: dict[str, str]`, `ui_calendar.STATUS_LABELS`, `ui_calendar.STATUS_COLORS`
  - `ui_calendar.status_pill(status: str) -> str` (colored-markdown directive, e.g. `":green-background[pronto]"`; unknown status raises `KeyError`)
  - `ui_calendar.group_slots_by_week(slots: list[dict], month: str) -> list[dict]` (each `{"label": "Semana de 06/07", "slots": [...]}`; only weeks that contain slots... empty weeks are kept with `slots == []` so the UI can show a gentle "semana livre")
  - `ui_calendar.render(cfg, conn, client, run_with_progress) -> None`
  - New tab "Calendário" in `app.py`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import tone_guard
import ui_calendar

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_all_calendar_copy_passes_the_tone_guard():
    for key, text in ui_calendar.COPY.items():
        assert tone_guard.find_harsh_words(text) == [], key


def test_status_pill_covers_every_slot_status():
    import calendar_store

    for status in calendar_store.STATUSES:
        assert ui_calendar.status_pill(status).startswith(":")
    with pytest.raises(KeyError):
        ui_calendar.status_pill("nonsense")


def test_group_slots_by_week_keeps_empty_weeks_and_orders_slots():
    slots = [
        {"date": "2026-07-09", "id": 2}, {"date": "2026-07-02", "id": 1}, {"date": "2026-07-22", "id": 3},
    ]
    groups = ui_calendar.group_slots_by_week(slots, "2026-07")
    assert [g["label"] for g in groups][0] == "Semana de 01/07"
    by_label = {g["label"]: [s["id"] for s in g["slots"]] for g in groups}
    assert by_label["Semana de 01/07"] == [1]
    assert by_label["Semana de 06/07"] == [2]
    assert by_label["Semana de 13/07"] == []          # an open week is kept, not hidden
    assert by_label["Semana de 20/07"] == [3]


def test_calendar_tab_invites_the_user_to_build_a_strategy_first(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    at = AppTest.from_file(APP_PATH)
    at.run()
    assert not at.exception
    assert "Calendário" in [t.label for t in at.tabs]
    assert any("estratégia" in i.value.lower() for i in at.info)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_calendar.py -v`
Expected: FAIL (`ModuleNotFoundError: ui_calendar`).

- [ ] **Step 3: Implement `ui_calendar.py`**

```python
from datetime import date

import streamlit as st

import calendar_generate
import calendar_plan
import calendar_refine
import calendar_store
import coach_store

COPY = {
    "need_strategy": "Primeiro vamos criar e guardar a tua estratégia na aba Estratégia. Depois o calendário monta-se com base nela.",
    "no_plan": "Este mês ainda está em branco. Quando quiseres, preparo uma proposta para veres e ajustares.",
    "create": "Criar o plano do mês",
    "free_week": "Semana livre. Se te apetecer, posso sugerir algo leve.",
    "refine_label": "O que gostavas de ajustar neste mês? (por exemplo: menos publicações na primeira semana)",
    "refine_button": "Ajustar o plano",
    "budget": "Por hoje já usámos o orçamento definido. Retomamos amanhã, sem pressa.",
    "retry": "Não consegui montar isto desta vez. Podemos tentar de novo quando quiseres.",
    "already": "Este mês já tem plano. Se quiseres, posso recomeçar só as publicações que ainda não estão em produção.",
    "restart": "Recomeçar as publicações por fazer",
    "niche_title": "Datas do teu nicho",
    "niche_button": "Sugerir datas do nicho",
    "niche_help": "Vou procurar datas que façam sentido para o teu nicho neste mês. Aceita as que gostares.",
}
STATUS_LABELS = {"planned": "planeado", "in_production": "em produção", "ready": "pronto", "published": "publicado"}
STATUS_COLORS = {"planned": "gray", "in_production": "orange", "ready": "green", "published": "violet"}
FORMAT_LABELS = {"post": "publicação", "carousel": "carrossel", "reel": "reel", "story": "story"}


def status_pill(status):
    return f":{STATUS_COLORS[status]}-background[{STATUS_LABELS[status]}]"


def group_slots_by_week(slots, month):
    groups = []
    for week in calendar_plan.weeks_of_month(month):
        first, last = week[0].isoformat(), week[-1].isoformat()
        groups.append({
            "label": f"Semana de {week[0].strftime('%d/%m')}",
            "slots": sorted((s for s in slots if first <= s["date"] <= last), key=lambda s: s["date"]),
        })
    return groups


def _describe_slot(slot):
    day = date.fromisoformat(slot["date"]).strftime("%d/%m")
    parts = [f"**{day}** · {FORMAT_LABELS[slot['format']]} · {slot.get('pillar') or 'sem pilar'} {status_pill(slot['status'])}",
             f"{slot['topic']}"]
    if slot.get("angle"):
        parts.append(f"_{slot['angle']}_")
    if slot.get("cta_keyword"):
        parts.append(f"CTA: comenta **{slot['cta_keyword']}**")
    return "  \n".join(parts)


def _render_month_list(conn, brand_pack, month):
    plan = calendar_store.get_month_plan(conn, brand_pack, month)
    st.markdown(f"**Tema do mês:** {plan['theme']}")
    if plan["north_star"]:
        st.caption(f"O que este mês procura melhorar: {plan['north_star']}. Oferta em destaque: {plan['featured_offer'] or 'nenhuma'}.")
    for group in group_slots_by_week(calendar_store.list_slots(conn, plan["id"]), month):
        st.markdown(f"#### {group['label']}")
        if not group["slots"]:
            st.caption(COPY["free_week"])
        for slot in group["slots"]:
            st.markdown(_describe_slot(slot))


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        st.info(COPY["budget"] if "daily cap" in str(e) else COPY["retry"])
        return None


def render(cfg, conn, client, run_with_progress):
    strategy = coach_store.latest_strategy(conn, cfg.brand_pack, status="accepted")
    if strategy is None:
        st.info(COPY["need_strategy"])
        return
    sections = coach_store.get_sections(conn, strategy["id"])
    month = st.selectbox("Mês", calendar_plan.upcoming_months(date.today()), key="calendar_month")
    niche = strategy["profile"]["who"]

    plan = calendar_store.get_month_plan(conn, cfg.brand_pack, month)
    has_slots = bool(plan and calendar_store.list_slots(conn, plan["id"]))
    if not has_slots:
        st.write(COPY["no_plan"])
    if st.button(COPY["restart"] if has_slots else COPY["create"], type="primary"):
        findings = [f["patterns"] for f in coach_store.list_findings(conn, cfg.brand_pack)]
        result = _guard(
            run_with_progress, calendar_generate.generate_month, client, conn, cfg.brand_pack, month,
            strategy["id"], sections, cfg.max_daily_spend_usd,
            niche_dates=calendar_store.list_niche_dates(conn, cfg.brand_pack, month),
            findings=findings, replace=has_slots,
        )
        if result is not None:
            st.rerun()

    if has_slots:
        _render_month_list(conn, cfg.brand_pack, month)
        feedback = st.text_input(COPY["refine_label"], key="calendar_feedback")
        if st.button(COPY["refine_button"]) and feedback.strip():
            changed = _guard(
                run_with_progress, calendar_refine.refine_month, client, conn, cfg.brand_pack, month,
                feedback.strip(), cfg.max_daily_spend_usd,
            )
            if changed is not None:
                st.rerun()
```

- [ ] **Step 4: Wire into `app.py`**

1. Add `import calendar_store` and `import ui_calendar` to the imports.
2. After `db.init_db(conn)` add `calendar_store.init_schema(conn)`.
3. Extend `STEP_LABELS` with `"calendar_fill": "A montar o calendário"`, `"calendar_refine": "A ajustar o calendário"`, `"niche_dates": "A procurar datas do teu nicho"`.
4. Add `"Calendário"` to the `st.tabs([...])` list and unpack a new variable `tab_calendar` (append after the existing tabs; if the Strategy Coach tab is already present, append after "Estratégia").
5. At the end of the file add:

```python
with tab_calendar:
    ui_calendar.render(cfg, conn, client, run_with_progress)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite).

- [ ] **Step 6: Commit**

```bash
git add content-creator/ui_calendar.py content-creator/app.py content-creator/tests/test_ui_calendar.py
git commit -m "feat: add Calendário tab (list view, generate and refine the month)"
```

---

### Task 7: Niche-date panel (accept or skip)

**Files:**
- Modify: `content-creator/ui_calendar.py` (add `render_niche_dates` and call it from `render` above the month list)
- Test: `content-creator/tests/test_ui_calendar_niche.py`

**Interfaces:**
- Consumes: `niche_dates.propose_niche_dates` (Task 3); `calendar_store.list_niche_dates`, `calendar_store.set_niche_date_decision`, `calendar_store.get_month_plan` (Task 1); `calendar_generate.add_niche_date_slot` (Task 4); `ui_calendar.COPY`, `ui_calendar.render` (Task 6).
- Produces: `ui_calendar.accept_niche_date(conn, brand_pack: str, month: str, niche_date_id: int) -> int | None` (sets decision `accepted`; if the month already has a plan, adds a `planned` slot via `add_niche_date_slot` and returns its id, otherwise returns `None`), `ui_calendar.skip_niche_date(conn, niche_date_id: int) -> None`, `ui_calendar.render_niche_dates(cfg, conn, client, run_with_progress, month: str, niche: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import calendar_store
import db
import ui_calendar


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    calendar_store.init_schema(connection)
    return connection


def seed_niche_date(conn):
    return calendar_store.save_niche_dates(conn, "brand", "2026-07", [
        {"date": "2026-07-07", "name": "Portal 7/7", "why": "renovação", "ideas": ["ritual simples"], "source": "pesquisa", "confidence": "média"},
    ])[0]


def test_accept_without_plan_only_records_the_decision(conn):
    nid = seed_niche_date(conn)
    assert ui_calendar.accept_niche_date(conn, "brand", "2026-07", nid) is None
    assert calendar_store.list_niche_dates(conn, "brand", "2026-07")[0]["decision"] == "accepted"


def test_accept_with_existing_plan_adds_a_planned_slot(conn):
    nid = seed_niche_date(conn)
    plan_id = calendar_store.save_month_plan(conn, "brand", "2026-07")
    slot_id = ui_calendar.accept_niche_date(conn, "brand", "2026-07", nid)
    slot = calendar_store.get_slot(conn, slot_id)
    assert slot["niche_date_id"] == nid and slot["date"] == "2026-07-07" and slot["status"] == "planned"
    assert [s["id"] for s in calendar_store.list_slots(conn, plan_id)] == [slot_id]


def test_skip_records_the_decision(conn):
    nid = seed_niche_date(conn)
    ui_calendar.skip_niche_date(conn, nid)
    assert calendar_store.list_niche_dates(conn, "brand", "2026-07")[0]["decision"] == "skipped"


def test_accepting_twice_does_not_add_a_second_slot(conn):
    nid = seed_niche_date(conn)
    calendar_store.save_month_plan(conn, "brand", "2026-07")
    first = ui_calendar.accept_niche_date(conn, "brand", "2026-07", nid)
    second = ui_calendar.accept_niche_date(conn, "brand", "2026-07", nid)
    assert first is not None and second is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_calendar_niche.py -v`
Expected: FAIL (`AttributeError: module 'ui_calendar' has no attribute 'accept_niche_date'`).

- [ ] **Step 3: Implement (add to `ui_calendar.py`; add `import niche_dates` at the top)**

```python
def accept_niche_date(conn, brand_pack, month, niche_date_id):
    niche_date = next(d for d in calendar_store.list_niche_dates(conn, brand_pack, month) if d["id"] == niche_date_id)
    if niche_date["decision"] == "accepted":
        return None
    calendar_store.set_niche_date_decision(conn, niche_date_id, "accepted")
    plan = calendar_store.get_month_plan(conn, brand_pack, month)
    if plan is None:
        return None
    return calendar_generate.add_niche_date_slot(conn, plan["id"], brand_pack, niche_date)


def skip_niche_date(conn, niche_date_id):
    calendar_store.set_niche_date_decision(conn, niche_date_id, "skipped")


def render_niche_dates(cfg, conn, client, run_with_progress, month, niche):
    st.markdown(f"### {COPY['niche_title']}")
    st.caption(COPY["niche_help"])
    existing = calendar_store.list_niche_dates(conn, cfg.brand_pack, month)
    if st.button(COPY["niche_button"] if not existing else "Procurar de novo", key="niche_search"):
        result = _guard(
            run_with_progress, niche_dates.propose_niche_dates, client, conn, cfg.brand_pack, niche, month,
            cfg.max_daily_spend_usd, refresh=bool(existing),
        )
        if result is not None:
            st.rerun()
    for item in existing:
        with st.container(border=True):
            st.markdown(f"**{item['date'][8:]}/{item['date'][5:7]} · {item['name']}** _(confiança {item['confidence']}, {item['source']})_")
            st.write(item["why"])
            for idea in item["ideas"]:
                st.caption(f"Ideia: {idea}")
            if item["decision"] == "proposed":
                col1, col2 = st.columns(2)
                if col1.button("Aceitar", key=f"nd_yes_{item['id']}", type="primary"):
                    accept_niche_date(conn, cfg.brand_pack, month, item["id"])
                    st.rerun()
                if col2.button("Saltar", key=f"nd_no_{item['id']}"):
                    skip_niche_date(conn, item["id"])
                    st.rerun()
            else:
                st.caption("Aceite" if item["decision"] == "accepted" else "Saltada")
```

Then, inside `render` (Task 6), insert `render_niche_dates(cfg, conn, client, run_with_progress, month, niche)` right after the month selector and before the "create plan" button.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite).

- [ ] **Step 5: Commit**

```bash
git add content-creator/ui_calendar.py content-creator/tests/test_ui_calendar_niche.py
git commit -m "feat: add niche-date panel with accept/skip and slot creation"
```

---

## Final checklist (after all tasks are merged into `content-calendar`)

- [ ] Run the whole suite: `python -m pytest tests -q`.
- [ ] **One real, paid end-to-end run**: with an accepted strategy, suggest niche dates for a real month, accept two, create the plan, refine it once in plain words. Verify `api_calls` rows for `niche_dates`, `calendar_fill`, `calendar_refine`, and that the moon phases shown match an independent moon calendar. Record any bug the mocks missed in `content-creator/docs/decisions.md`.
- [ ] Read every screen once for tone (no urgency, no blame; empty weeks are invitations).
- [ ] Final whole-branch review, then merge `content-calendar` into `main`.
