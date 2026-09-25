# Windsor Analytics and Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the user's real Windsor.ai Instagram data per brand, show it in a calm Resultados tab with a manual Refresh button, and feed what performed back into the Coach and the next month's calendar.

**Architecture:** Flat modules at the `content-creator/` root. `windsor.py` is a thin HTTP client with injectable HTTP and a canonical-field map (so Windsor's real field names live in one place). `analytics_store.py` caches snapshots, posts and per-brand settings in SQLite. `analytics_refresh.py` fetches on demand (no background polling). `insights.py` is pure maths; AI is used only to phrase insights kindly, with a deterministic gentle fallback. `windsor_bridge.py` turns stored analytics into the `windsor_summary` (Coach) and `performance` (Calendar) inputs those modules already accept.

**Tech Stack:** Python, Streamlit, SQLite, stdlib `urllib`, Anthropic SDK (phrasing only), pytest + `unittest.mock`.

**Spec:** `content-creator/docs/superpowers/specs/2026-09-25-windsor-feedback-loop-design.md`

**Feature branch:** `windsor-results` (create from `main`; tickets branch off it as `ticket-<issue-number>`). Tasks 1-4 need nothing from the other plans and can start immediately. Tickets with a `Cross-plan` line depend on the *final ticket* of the named plan: they only unblock after that plan has been reviewed and merged into `main`, and `main` has been merged into this feature branch.

**Test command (run from `content-creator/`):** `python -m pytest tests -q`

## Global Constraints

- One brand pack = one Instagram profile = one Windsor connection (multi-profile/other networks are in the backlog).
- The Windsor API key is a secret: read from `WINDSOR_API_KEY` in `.env`, never stored in the DB or code. The chosen Windsor account id is stored per brand in `brand_settings` (key `windsor_account_id`).
- Refresh is user-triggered only (no background polling). Repeated clicks within `reuse_seconds` (default 60) reuse the just-fetched data. The tab always shows "última actualização".
- All user-facing and AI-generated text is **PT-PT** and **gentle**: no urgency, no blame, never "critical" or "failed". Missing data is explained warmly with how to connect. Errors always say what to do next.
- Fetching costs no AI budget. Phrasing calls go through `pipeline._invoke` (spend cap + cost logging) and fall back to deterministic gentle text if the AI call fails or the cap is reached.
- Windsor's field names must be verified against the user's real connector (Task 1, Step 1). All field names live in `windsor.ACCOUNT_FIELD_MAP` and `windsor.POST_FIELD_MAP`; tests build rows from those maps so they keep passing after the maps are corrected.
- Canonical post dict (used everywhere after `windsor.normalize_post`): `{"post_id": str, "published_at": ISO str, "format": "post"|"carousel"|"reel"|"story", "caption": str, "likes": int, "comments": int, "saves": int, "shares": int, "reach": int, "impressions": int}`. Canonical snapshot dict: `{"followers": int, "follower_change": int, "reach": int, "impressions": int, "profile_views": int}`.
- Do not modify existing `db.py` tables; new tables live in `analytics_store.py`.

---

### Task 1: Windsor client

**Files:**
- Create: `content-creator/windsor.py`
- Test: `content-creator/tests/test_windsor.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `windsor.WindsorError(Exception)` (messages are gentle PT-PT)
  - `windsor.ACCOUNT_FIELD_MAP`, `windsor.POST_FIELD_MAP` (canonical name → Windsor field name)
  - `windsor.build_url(api_key, fields: list[str], date_from=None, date_to=None, date_preset=None, account_id=None) -> str`
  - `windsor.normalize_format(raw: str | None) -> str`
  - `windsor.normalize_post(row: dict) -> dict` (canonical post dict), `windsor.normalize_account(rows: list[dict]) -> dict` (canonical snapshot dict; `followers` = last row's value, `follower_change` = last minus first, other metrics summed)
  - `windsor.fetch_account(api_key, account_id, date_from: str, date_to: str, get_json=<default>) -> dict` (canonical snapshot)
  - `windsor.fetch_posts(api_key, account_id, date_from: str, date_to: str, get_json=<default>) -> list[dict]` (canonical posts)

- [ ] **Step 1: Verify the real API shape (manual, needs the user's key)**

Windsor's connector endpoint is expected to look like `https://connectors.windsor.ai/instagram?api_key=...&fields=...&date_preset=last_7d` returning `{"data": [...]}`. Confirm this and the exact Instagram **account** and **media** field names and the account-selection parameter in Windsor's docs and in the Windsor dashboard's data preview for the user's connector. Then, with `WINDSOR_API_KEY` in `content-creator/.env`, run:

```
python -c "import os, json, windsor; from dotenv import load_dotenv; load_dotenv(); print(json.dumps(windsor._http_get_json(windsor.build_url(os.environ['WINDSOR_API_KEY'], ['date', 'followers_count'], date_preset='last_7d')), indent=1)[:1500])"
```

(Run it after Step 4 creates the module.) Correct `BASE_URL`, `CONNECTOR`, `ACCOUNT_FIELD_MAP`, `POST_FIELD_MAP` and the account-selection parameter name in `build_url` to match reality. If no key is available yet, keep the defaults below and record "field names unverified" in the commit message and in the final report; do not block the task.

- [ ] **Step 2: Write the failing tests**

```python
import io
import json
import urllib.error
import urllib.parse

import pytest

import windsor


def post_row(**overrides):
    row = {
        windsor.POST_FIELD_MAP["post_id"]: "p1",
        windsor.POST_FIELD_MAP["published_at"]: "2026-07-07T10:00:00+0000",
        windsor.POST_FIELD_MAP["format"]: "CAROUSEL_ALBUM",
        windsor.POST_FIELD_MAP["caption"]: "Como dormir melhor",
        windsor.POST_FIELD_MAP["likes"]: 120,
        windsor.POST_FIELD_MAP["comments"]: "8",
        windsor.POST_FIELD_MAP["saves"]: 30,
        windsor.POST_FIELD_MAP["shares"]: 4,
        windsor.POST_FIELD_MAP["reach"]: 2500,
        windsor.POST_FIELD_MAP["impressions"]: 3100,
    }
    row.update(overrides)
    return row


def account_row(date, followers, reach=100, impressions=150, profile_views=10):
    return {
        windsor.ACCOUNT_FIELD_MAP["date"]: date,
        windsor.ACCOUNT_FIELD_MAP["followers"]: followers,
        windsor.ACCOUNT_FIELD_MAP["reach"]: reach,
        windsor.ACCOUNT_FIELD_MAP["impressions"]: impressions,
        windsor.ACCOUNT_FIELD_MAP["profile_views"]: profile_views,
    }


def test_build_url_contains_key_fields_dates_and_account():
    url = windsor.build_url("KEY", ["a", "b"], date_from="2026-07-01", date_to="2026-07-31", account_id="acc1")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert params["api_key"] == ["KEY"] and params["fields"] == ["a,b"]
    assert params["date_from"] == ["2026-07-01"] and params["date_to"] == ["2026-07-31"]
    assert "acc1" in sum(params.values(), [])


def test_build_url_supports_date_preset_and_no_account():
    params = urllib.parse.parse_qs(urllib.parse.urlparse(windsor.build_url("K", ["a"], date_preset="last_30d")).query)
    assert params["date_preset"] == ["last_30d"] and "date_from" not in params


def test_normalize_format_maps_instagram_types():
    assert windsor.normalize_format("CAROUSEL_ALBUM") == "carousel"
    assert windsor.normalize_format("VIDEO") == "reel"
    assert windsor.normalize_format("REELS") == "reel"
    assert windsor.normalize_format("IMAGE") == "post"
    assert windsor.normalize_format("STORY") == "story"
    assert windsor.normalize_format(None) == "post"


def test_normalize_post_coerces_numbers_and_format():
    post = windsor.normalize_post(post_row())
    assert post == {
        "post_id": "p1", "published_at": "2026-07-07T10:00:00+0000", "format": "carousel",
        "caption": "Como dormir melhor", "likes": 120, "comments": 8, "saves": 30, "shares": 4,
        "reach": 2500, "impressions": 3100,
    }


def test_normalize_post_treats_missing_metrics_as_zero_and_missing_caption_as_empty():
    row = post_row()
    del row[windsor.POST_FIELD_MAP["saves"]]
    row[windsor.POST_FIELD_MAP["caption"]] = None
    post = windsor.normalize_post(row)
    assert post["saves"] == 0 and post["caption"] == ""


def test_normalize_account_uses_last_followers_change_and_summed_metrics():
    rows = [account_row("2026-07-02", 1010, reach=200), account_row("2026-07-01", 1000, reach=100), account_row("2026-07-03", 1030, reach=300)]
    snapshot = windsor.normalize_account(rows)
    assert snapshot["followers"] == 1030 and snapshot["follower_change"] == 30
    assert snapshot["reach"] == 600 and snapshot["profile_views"] == 30


def test_normalize_account_with_no_rows_is_all_zero():
    assert windsor.normalize_account([]) == {"followers": 0, "follower_change": 0, "reach": 0, "impressions": 0, "profile_views": 0}


def test_fetch_posts_and_account_use_injected_http_and_accept_both_payload_shapes():
    seen = []

    def get_json(url):
        seen.append(url)
        return {"data": [post_row()]} if "media" in url or windsor.POST_FIELD_MAP["post_id"] in url else [account_row("2026-07-01", 5)]

    posts = windsor.fetch_posts("K", "acc", "2026-07-01", "2026-07-31", get_json=get_json)
    snapshot = windsor.fetch_account("K", "acc", "2026-07-01", "2026-07-31", get_json=get_json)
    assert posts[0]["post_id"] == "p1" and snapshot["followers"] == 5
    assert len(seen) == 2


def test_fetch_rows_rejects_unexpected_payloads_gently():
    with pytest.raises(windsor.WindsorError):
        windsor.fetch_posts("K", "acc", "2026-07-01", "2026-07-31", get_json=lambda url: {"unexpected": True})


def test_http_errors_become_gentle_windsor_errors(monkeypatch):
    def boom(url, timeout=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr(windsor.urllib.request, "urlopen", boom)
    with pytest.raises(windsor.WindsorError) as exc:
        windsor._http_get_json("https://connectors.windsor.ai/instagram?x=1")
    assert "chave" in str(exc.value).lower()

    def unreachable(url, timeout=None):
        raise urllib.error.URLError("dns")

    monkeypatch.setattr(windsor.urllib.request, "urlopen", unreachable)
    with pytest.raises(windsor.WindsorError):
        windsor._http_get_json("https://connectors.windsor.ai/instagram?x=1")
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_windsor.py -v`
Expected: FAIL (`ModuleNotFoundError: windsor`).

- [ ] **Step 4: Implement `windsor.py`**

```python
import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://connectors.windsor.ai"
CONNECTOR = "instagram"

# canonical name -> Windsor field name. VERIFY against the user's real connector (see Step 1).
ACCOUNT_FIELD_MAP = {
    "date": "date",
    "followers": "followers_count",
    "reach": "reach",
    "impressions": "impressions",
    "profile_views": "profile_views",
}
POST_FIELD_MAP = {
    "post_id": "media_id",
    "published_at": "media_timestamp",
    "format": "media_type",
    "caption": "media_caption",
    "likes": "media_like_count",
    "comments": "media_comments_count",
    "saves": "media_saved",
    "shares": "media_shares",
    "reach": "media_reach",
    "impressions": "media_impressions",
}


class WindsorError(Exception):
    pass


def _http_get_json(url, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise WindsorError(
                "O Windsor não aceitou a chave. Quando puderes, confirma a chave nas Definições e tentamos outra vez."
            ) from e
        raise WindsorError(f"O Windsor respondeu com o código {e.code}. Podemos tentar de novo daqui a pouco.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise WindsorError("Não consegui falar com o Windsor agora. Podemos tentar de novo daqui a pouco.") from e


def build_url(api_key, fields, date_from=None, date_to=None, date_preset=None, account_id=None):
    params = {"api_key": api_key, "fields": ",".join(fields)}
    if date_preset:
        params["date_preset"] = date_preset
    else:
        params["date_from"], params["date_to"] = date_from, date_to
    if account_id:
        params["select_accounts"] = account_id  # VERIFY the parameter name (see Step 1)
    return f"{BASE_URL}/{CONNECTOR}?{urllib.parse.urlencode(params)}"


def _num(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


_FORMATS = {"CAROUSEL_ALBUM": "carousel", "VIDEO": "reel", "REELS": "reel", "REEL": "reel", "STORY": "story", "IMAGE": "post"}


def normalize_format(raw):
    return _FORMATS.get((raw or "").upper(), "post")


def normalize_post(row):
    m = POST_FIELD_MAP
    return {
        "post_id": str(row.get(m["post_id"], "")),
        "published_at": row.get(m["published_at"]) or "",
        "format": normalize_format(row.get(m["format"])),
        "caption": row.get(m["caption"]) or "",
        "likes": _num(row.get(m["likes"])),
        "comments": _num(row.get(m["comments"])),
        "saves": _num(row.get(m["saves"])),
        "shares": _num(row.get(m["shares"])),
        "reach": _num(row.get(m["reach"])),
        "impressions": _num(row.get(m["impressions"])),
    }


def normalize_account(rows):
    if not rows:
        return {"followers": 0, "follower_change": 0, "reach": 0, "impressions": 0, "profile_views": 0}
    m = ACCOUNT_FIELD_MAP
    ordered = sorted(rows, key=lambda r: str(r.get(m["date"], "")))
    first, last = _num(ordered[0].get(m["followers"])), _num(ordered[-1].get(m["followers"]))
    return {
        "followers": last,
        "follower_change": last - first,
        "reach": sum(_num(r.get(m["reach"])) for r in ordered),
        "impressions": sum(_num(r.get(m["impressions"])) for r in ordered),
        "profile_views": sum(_num(r.get(m["profile_views"])) for r in ordered),
    }


def _rows(payload):
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise WindsorError("O Windsor devolveu dados num formato inesperado. Podemos tentar de novo daqui a pouco.")
    return rows


def fetch_account(api_key, account_id, date_from, date_to, get_json=_http_get_json):
    url = build_url(api_key, list(ACCOUNT_FIELD_MAP.values()), date_from=date_from, date_to=date_to, account_id=account_id)
    return normalize_account(_rows(get_json(url)))


def fetch_posts(api_key, account_id, date_from, date_to, get_json=_http_get_json):
    url = build_url(api_key, list(POST_FIELD_MAP.values()), date_from=date_from, date_to=date_to, account_id=account_id)
    return [normalize_post(row) for row in _rows(get_json(url))]
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_windsor.py -v`
Expected: PASS (10 tests). If `test_fetch_posts_and_account_use_injected_http...` fails because of how it tells the two URLs apart, adjust the test's discriminator (for example test for a POST field name inside `url`), not the implementation.

- [ ] **Step 6: Commit**

```bash
git add content-creator/windsor.py content-creator/tests/test_windsor.py
git commit -m "feat: add Windsor client with canonical field maps (field names verified: yes/no)"
```

---

### Task 2: Analytics store (snapshots, posts, brand settings)

**Files:**
- Create: `content-creator/analytics_store.py`
- Test: `content-creator/tests/test_analytics_store.py`

**Interfaces:**
- Consumes: canonical post and snapshot dict shapes (see Global Constraints; produced by Task 1's `windsor.normalize_*`).
- Produces: `analytics_store.init_schema(conn) -> None`
  - `analytics_store.save_snapshot(conn, brand_pack, snapshot: dict, period_start: str, period_end: str, fetched_at: str) -> int`
  - `analytics_store.latest_snapshot(conn, brand_pack) -> dict | None` (canonical keys plus `fetched_at`, `period_start`, `period_end`)
  - `analytics_store.snapshot_before(conn, brand_pack, fetched_before: str) -> dict | None` (latest snapshot with `fetched_at <= fetched_before`)
  - `analytics_store.last_fetched_at(conn, brand_pack) -> str | None`
  - `analytics_store.upsert_posts(conn, brand_pack, posts: list[dict], fetched_at: str) -> int` (unique per `(brand_pack, post_id)`; later fetches update metrics)
  - `analytics_store.list_posts(conn, brand_pack, since: str | None = None) -> list[dict]` (canonical post dicts, newest first; `since` is an ISO date compared with `published_at`)
  - `analytics_store.set_setting(conn, brand_pack, key, value) -> None`, `analytics_store.get_setting(conn, brand_pack, key, default=None) -> str | None`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import analytics_store
import db

SNAP = {"followers": 1030, "follower_change": 30, "reach": 600, "impressions": 900, "profile_views": 30}


def post(post_id="p1", published_at="2026-07-07T10:00:00+0000", **kw):
    base = {"post_id": post_id, "published_at": published_at, "format": "carousel", "caption": "c",
            "likes": 10, "comments": 1, "saves": 2, "shares": 0, "reach": 100, "impressions": 120}
    base.update(kw)
    return base


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    analytics_store.init_schema(connection)
    return connection


def test_snapshots_latest_and_before(conn):
    analytics_store.save_snapshot(conn, "b", SNAP, "2026-06-01", "2026-06-30", "2026-06-30T12:00:00+00:00")
    analytics_store.save_snapshot(conn, "b", {**SNAP, "followers": 1100}, "2026-07-01", "2026-07-15", "2026-07-15T12:00:00+00:00")
    assert analytics_store.latest_snapshot(conn, "b")["followers"] == 1100
    assert analytics_store.snapshot_before(conn, "b", "2026-07-01T00:00:00+00:00")["followers"] == 1030
    assert analytics_store.snapshot_before(conn, "b", "2026-01-01T00:00:00+00:00") is None
    assert analytics_store.last_fetched_at(conn, "b") == "2026-07-15T12:00:00+00:00"
    assert analytics_store.latest_snapshot(conn, "other") is None and analytics_store.last_fetched_at(conn, "other") is None


def test_upsert_posts_updates_existing_metrics_and_is_brand_scoped(conn):
    assert analytics_store.upsert_posts(conn, "b", [post(), post("p2", likes=50)], "2026-07-10T00:00:00+00:00") == 2
    analytics_store.upsert_posts(conn, "b", [post(likes=99)], "2026-07-20T00:00:00+00:00")
    by_id = {p["post_id"]: p for p in analytics_store.list_posts(conn, "b")}
    assert by_id["p1"]["likes"] == 99 and by_id["p2"]["likes"] == 50 and len(by_id) == 2
    assert analytics_store.list_posts(conn, "other") == []


def test_list_posts_newest_first_and_since_filter(conn):
    analytics_store.upsert_posts(conn, "b", [post("old", "2026-05-01T10:00:00+0000"), post("new", "2026-07-07T10:00:00+0000")], "t")
    assert [p["post_id"] for p in analytics_store.list_posts(conn, "b")] == ["new", "old"]
    assert [p["post_id"] for p in analytics_store.list_posts(conn, "b", since="2026-06-01")] == ["new"]


def test_settings_roundtrip_and_default(conn):
    assert analytics_store.get_setting(conn, "b", "windsor_account_id") is None
    assert analytics_store.get_setting(conn, "b", "x", default="d") == "d"
    analytics_store.set_setting(conn, "b", "windsor_account_id", "acc1")
    analytics_store.set_setting(conn, "b", "windsor_account_id", "acc2")
    assert analytics_store.get_setting(conn, "b", "windsor_account_id") == "acc2"
    assert analytics_store.get_setting(conn, "other", "windsor_account_id") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_analytics_store.py -v`
Expected: FAIL (`ModuleNotFoundError: analytics_store`).

- [ ] **Step 3: Implement**

```python
def init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            followers INTEGER NOT NULL,
            follower_change INTEGER NOT NULL,
            reach INTEGER NOT NULL,
            impressions INTEGER NOT NULL,
            profile_views INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS post_metrics (
            id INTEGER PRIMARY KEY,
            brand_pack TEXT NOT NULL,
            post_id TEXT NOT NULL,
            published_at TEXT NOT NULL,
            format TEXT NOT NULL,
            caption TEXT NOT NULL,
            likes INTEGER NOT NULL,
            comments INTEGER NOT NULL,
            saves INTEGER NOT NULL,
            shares INTEGER NOT NULL,
            reach INTEGER NOT NULL,
            impressions INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE (brand_pack, post_id)
        );
        CREATE TABLE IF NOT EXISTS brand_settings (
            brand_pack TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (brand_pack, key)
        );
        """
    )
    conn.commit()


_SNAPSHOT_KEYS = ("followers", "follower_change", "reach", "impressions", "profile_views")
_POST_KEYS = ("post_id", "published_at", "format", "caption", "likes", "comments", "saves", "shares", "reach", "impressions")


def save_snapshot(conn, brand_pack, snapshot, period_start, period_end, fetched_at):
    cursor = conn.execute(
        "INSERT INTO analytics_snapshots (brand_pack, fetched_at, period_start, period_end, "
        "followers, follower_change, reach, impressions, profile_views) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (brand_pack, fetched_at, period_start, period_end, *(snapshot[k] for k in _SNAPSHOT_KEYS)),
    )
    conn.commit()
    return cursor.lastrowid


def latest_snapshot(conn, brand_pack):
    row = conn.execute(
        "SELECT * FROM analytics_snapshots WHERE brand_pack = ? ORDER BY fetched_at DESC, id DESC LIMIT 1", (brand_pack,)
    ).fetchone()
    return dict(row) if row else None


def snapshot_before(conn, brand_pack, fetched_before):
    row = conn.execute(
        "SELECT * FROM analytics_snapshots WHERE brand_pack = ? AND fetched_at <= ? "
        "ORDER BY fetched_at DESC, id DESC LIMIT 1", (brand_pack, fetched_before),
    ).fetchone()
    return dict(row) if row else None


def last_fetched_at(conn, brand_pack):
    row = conn.execute(
        "SELECT MAX(fetched_at) AS t FROM analytics_snapshots WHERE brand_pack = ?", (brand_pack,)
    ).fetchone()
    return row["t"]


def upsert_posts(conn, brand_pack, posts, fetched_at):
    for p in posts:
        conn.execute(
            "INSERT INTO post_metrics (brand_pack, post_id, published_at, format, caption, likes, comments, saves, "
            "shares, reach, impressions, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(brand_pack, post_id) DO UPDATE SET published_at = excluded.published_at, "
            "format = excluded.format, caption = excluded.caption, likes = excluded.likes, "
            "comments = excluded.comments, saves = excluded.saves, shares = excluded.shares, "
            "reach = excluded.reach, impressions = excluded.impressions, fetched_at = excluded.fetched_at",
            (brand_pack, *(p[k] for k in _POST_KEYS), fetched_at),
        )
    conn.commit()
    return len(posts)


def list_posts(conn, brand_pack, since=None):
    query, params = "SELECT * FROM post_metrics WHERE brand_pack = ?", [brand_pack]
    if since:
        query += " AND published_at >= ?"
        params.append(since)
    query += " ORDER BY published_at DESC"
    return [{k: row[k] for k in _POST_KEYS} for row in conn.execute(query, params).fetchall()]


def set_setting(conn, brand_pack, key, value):
    conn.execute(
        "INSERT INTO brand_settings (brand_pack, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(brand_pack, key) DO UPDATE SET value = excluded.value",
        (brand_pack, key, value),
    )
    conn.commit()


def get_setting(conn, brand_pack, key, default=None):
    row = conn.execute(
        "SELECT value FROM brand_settings WHERE brand_pack = ? AND key = ?", (brand_pack, key)
    ).fetchone()
    return row["value"] if row and row["value"] is not None else default
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_analytics_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/analytics_store.py content-creator/tests/test_analytics_store.py
git commit -m "feat: add analytics_store (snapshots, post metrics, brand settings)"
```

---

### Task 3: On-demand refresh

**Files:**
- Create: `content-creator/analytics_refresh.py`
- Test: `content-creator/tests/test_analytics_refresh.py`

**Interfaces:**
- Consumes: `windsor.fetch_account`, `windsor.fetch_posts`, `windsor.WindsorError` (Task 1); `analytics_store.last_fetched_at`, `save_snapshot`, `upsert_posts` (Task 2).
- Produces: `analytics_refresh.refresh(conn, brand_pack, api_key, account_id, now=None, force=False, reuse_seconds=60, history_days=90, account_fetcher=windsor.fetch_account, posts_fetcher=windsor.fetch_posts) -> dict` returning `{"fetched": bool, "fetched_at": str, "posts": int}` (`posts` only when fetched). When the last fetch is younger than `reuse_seconds` and `force` is false, nothing is fetched. `WindsorError` propagates unchanged.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta, timezone

import pytest

import analytics_refresh
import analytics_store
import db
import windsor

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
SNAP = {"followers": 1030, "follower_change": 30, "reach": 600, "impressions": 900, "profile_views": 30}
POST = {"post_id": "p1", "published_at": "2026-07-07T10:00:00+0000", "format": "post", "caption": "c",
        "likes": 1, "comments": 0, "saves": 0, "shares": 0, "reach": 10, "impressions": 12}


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    analytics_store.init_schema(connection)
    return connection


def fakes(calls):
    def account(api_key, account_id, date_from, date_to):
        calls.append(("account", api_key, account_id, date_from, date_to))
        return dict(SNAP)

    def posts(api_key, account_id, date_from, date_to):
        calls.append(("posts", date_from, date_to))
        return [dict(POST)]

    return account, posts


def test_refresh_fetches_and_stores_snapshot_and_posts(conn):
    calls = []
    account, posts = fakes(calls)
    result = analytics_refresh.refresh(conn, "b", "KEY", "acc", now=NOW, account_fetcher=account, posts_fetcher=posts)
    assert result == {"fetched": True, "fetched_at": NOW.isoformat(), "posts": 1}
    assert analytics_store.latest_snapshot(conn, "b")["followers"] == 1030
    assert analytics_store.list_posts(conn, "b")[0]["post_id"] == "p1"
    assert calls[0] == ("account", "KEY", "acc", "2026-04-16", "2026-07-15")  # 90 days of history


def test_recent_refresh_is_reused_unless_forced(conn):
    calls = []
    account, posts = fakes(calls)
    analytics_refresh.refresh(conn, "b", "K", "acc", now=NOW, account_fetcher=account, posts_fetcher=posts)
    again = analytics_refresh.refresh(conn, "b", "K", "acc", now=NOW + timedelta(seconds=30), account_fetcher=account, posts_fetcher=posts)
    assert again == {"fetched": False, "fetched_at": NOW.isoformat()} and len(calls) == 2
    forced = analytics_refresh.refresh(conn, "b", "K", "acc", now=NOW + timedelta(seconds=30), force=True, account_fetcher=account, posts_fetcher=posts)
    later = analytics_refresh.refresh(conn, "b", "K", "acc", now=NOW + timedelta(minutes=5), account_fetcher=account, posts_fetcher=posts)
    assert forced["fetched"] is True and later["fetched"] is True and len(calls) == 6


def test_windsor_errors_propagate_and_nothing_is_stored(conn):
    def account(*args):
        raise windsor.WindsorError("sem ligação")

    with pytest.raises(windsor.WindsorError):
        analytics_refresh.refresh(conn, "b", "K", "acc", now=NOW, account_fetcher=account, posts_fetcher=lambda *a: [])
    assert analytics_store.latest_snapshot(conn, "b") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_analytics_refresh.py -v`
Expected: FAIL (`ModuleNotFoundError: analytics_refresh`).

- [ ] **Step 3: Implement**

```python
from datetime import datetime, timedelta, timezone

import analytics_store
import windsor


def refresh(conn, brand_pack, api_key, account_id, now=None, force=False, reuse_seconds=60,
            history_days=90, account_fetcher=windsor.fetch_account, posts_fetcher=windsor.fetch_posts):
    now = now or datetime.now(timezone.utc)
    last = analytics_store.last_fetched_at(conn, brand_pack)
    if last and not force and (now - datetime.fromisoformat(last)).total_seconds() < reuse_seconds:
        return {"fetched": False, "fetched_at": last}
    date_to = now.date()
    date_from = date_to - timedelta(days=history_days)
    snapshot = account_fetcher(api_key, account_id, date_from.isoformat(), date_to.isoformat())
    posts = posts_fetcher(api_key, account_id, date_from.isoformat(), date_to.isoformat())
    stamp = now.isoformat()
    analytics_store.save_snapshot(conn, brand_pack, snapshot, date_from.isoformat(), date_to.isoformat(), stamp)
    analytics_store.upsert_posts(conn, brand_pack, posts, stamp)
    return {"fetched": True, "fetched_at": stamp, "posts": len(posts)}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_analytics_refresh.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/analytics_refresh.py content-creator/tests/test_analytics_refresh.py
git commit -m "feat: add on-demand analytics refresh with short reuse window"
```

---

### Task 4: Insights (pure maths)

**Files:**
- Create: `content-creator/insights.py`
- Test: `content-creator/tests/test_insights.py`

**Interfaces:**
- Consumes: the canonical post and snapshot dict shapes (Global Constraints; the same shapes `analytics_store.list_posts` / `latest_snapshot` return, Task 2). Calendar slot dicts (from `calendar_store.list_slots`) only need keys `id`, `date`, `format`, `pillar`, `funnel_phase`, `cta_category`.
- Produces: `insights.engagement(post: dict) -> int` (likes + comments + saves + shares)
  - `insights.published_date(post: dict) -> str` (`YYYY-MM-DD`)
  - `insights.match_posts_to_slots(posts, slots) -> list[dict]` (adds `slot_id`, `pillar`, `funnel_phase`, `cta_category`; same-day slot with the same format wins, else any same-day slot, else `None`s)
  - `insights.performance_by(posts, key: str) -> list[dict]` (`key` is a post key such as `"format"`, `"pillar"`, `"funnel_phase"`, `"cta_category"`, or the special `"weekday"`; rows `{"key","count","avg_engagement","avg_saves","avg_reach"}` sorted by `avg_engagement` desc then key; posts whose value is `None` are skipped)
  - `insights.top_posts(posts, n=3) -> list[dict]`, `insights.bottom_posts(posts, n=3) -> list[dict]` (by engagement)
  - `insights.month_over_month(posts, month: str, previous_month: str) -> dict` (`{"posts"|"avg_engagement"|"avg_saves": {"current","previous","change_pct"}}`; `change_pct` is `None` when previous is 0)
  - `insights.summarize_for_coach(snapshot: dict | None, posts: list[dict]) -> dict | None` (`{"followers","follower_change","post_count","avg_engagement","avg_saves","best_format"}` or `None` when there is neither snapshot nor posts)
  - `insights.performance_hints(matched_posts: list[dict]) -> dict | None` (`{"best_pillar","best_format","best_weekday"}` with `None` for unknown; `None` if there are no posts)

- [ ] **Step 1: Write the failing tests**

```python
import insights


def post(post_id, published_at, fmt="post", likes=0, comments=0, saves=0, shares=0, reach=100, **extra):
    return {"post_id": post_id, "published_at": published_at, "format": fmt, "caption": post_id,
            "likes": likes, "comments": comments, "saves": saves, "shares": shares, "reach": reach,
            "impressions": reach, **extra}


P1 = post("a", "2026-07-06T10:00:00+0000", "carousel", likes=100, saves=40)   # Monday
P2 = post("b", "2026-07-08T10:00:00+0000", "reel", likes=10, comments=2)      # Wednesday
P3 = post("c", "2026-06-10T10:00:00+0000", "post", likes=20, saves=5)


def test_engagement_and_published_date():
    assert insights.engagement(P1) == 140
    assert insights.published_date(P1) == "2026-07-06"


def test_match_posts_to_slots_prefers_same_format_and_leaves_unmatched_empty():
    slots = [
        {"id": 1, "date": "2026-07-06", "format": "reel", "pillar": "Bastidores", "funnel_phase": "X", "cta_category": "community"},
        {"id": 2, "date": "2026-07-06", "format": "carousel", "pillar": "Educar", "funnel_phase": "Y", "cta_category": "education"},
    ]
    matched = insights.match_posts_to_slots([P1, P2], slots)
    assert matched[0]["slot_id"] == 2 and matched[0]["pillar"] == "Educar"
    assert matched[1]["slot_id"] is None and matched[1]["pillar"] is None
    assert "slot_id" not in P1  # inputs are not mutated


def test_match_falls_back_to_any_same_day_slot():
    slots = [{"id": 9, "date": "2026-07-06", "format": "story", "pillar": "Educar", "funnel_phase": "Y", "cta_category": None}]
    assert insights.match_posts_to_slots([P1], slots)[0]["slot_id"] == 9


def test_performance_by_format_sorted_by_engagement():
    rows = insights.performance_by([P1, P2, P3], "format")
    assert [r["key"] for r in rows] == ["carousel", "post", "reel"]
    assert rows[0] == {"key": "carousel", "count": 1, "avg_engagement": 140.0, "avg_saves": 40.0, "avg_reach": 100.0}


def test_performance_by_weekday_uses_portuguese_names_and_skips_none_keys():
    rows = insights.performance_by([P1, P2], "weekday")
    assert {r["key"] for r in rows} == {"segunda", "quarta"}
    assert insights.performance_by([{**P1, "pillar": None}], "pillar") == []


def test_top_and_bottom_posts():
    assert [p["post_id"] for p in insights.top_posts([P2, P1, P3], n=2)] == ["a", "c"]
    assert [p["post_id"] for p in insights.bottom_posts([P2, P1, P3], n=1)] == ["b"]


def test_month_over_month_counts_and_percent_change():
    result = insights.month_over_month([P1, P2, P3], "2026-07", "2026-06")
    assert result["posts"] == {"current": 2, "previous": 1, "change_pct": 100.0}
    assert result["avg_engagement"]["current"] == 76.0 and result["avg_engagement"]["previous"] == 25.0
    empty_previous = insights.month_over_month([P1], "2026-07", "2026-06")
    assert empty_previous["posts"]["change_pct"] is None


def test_summarize_for_coach():
    assert insights.summarize_for_coach(None, []) is None
    summary = insights.summarize_for_coach(
        {"followers": 1030, "follower_change": 30, "reach": 1, "impressions": 1, "profile_views": 1}, [P1, P2],
    )
    assert summary["followers"] == 1030 and summary["post_count"] == 2
    assert summary["best_format"] == "carousel" and summary["avg_engagement"] == 76.0


def test_performance_hints():
    assert insights.performance_hints([]) is None
    matched = [{**P1, "pillar": "Educar"}, {**P2, "pillar": "Bastidores"}]
    hints = insights.performance_hints(matched)
    assert hints == {"best_pillar": "Educar", "best_format": "carousel", "best_weekday": "segunda"}
    assert insights.performance_hints([P1])["best_pillar"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_insights.py -v`
Expected: FAIL (`ModuleNotFoundError: insights`).

- [ ] **Step 3: Implement**

```python
from collections import defaultdict
from datetime import date
from statistics import mean

WEEKDAYS_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def engagement(post):
    return post["likes"] + post["comments"] + post["saves"] + post["shares"]


def published_date(post):
    return post["published_at"][:10]


def match_posts_to_slots(posts, slots):
    by_date = defaultdict(list)
    for slot in slots:
        by_date[slot["date"]].append(slot)
    matched = []
    for post in posts:
        candidates = by_date.get(published_date(post), [])
        slot = next((s for s in candidates if s["format"] == post["format"]), candidates[0] if candidates else None)
        matched.append({
            **post,
            "slot_id": slot["id"] if slot else None,
            "pillar": slot["pillar"] if slot else None,
            "funnel_phase": slot["funnel_phase"] if slot else None,
            "cta_category": slot["cta_category"] if slot else None,
        })
    return matched


def performance_by(posts, key):
    groups = defaultdict(list)
    for post in posts:
        value = WEEKDAYS_PT[date.fromisoformat(published_date(post)).weekday()] if key == "weekday" else post.get(key)
        if value is not None:
            groups[value].append(post)
    rows = [
        {
            "key": value,
            "count": len(items),
            "avg_engagement": round(mean(engagement(p) for p in items), 1),
            "avg_saves": round(mean(p["saves"] for p in items), 1),
            "avg_reach": round(mean(p["reach"] for p in items), 1),
        }
        for value, items in groups.items()
    ]
    return sorted(rows, key=lambda r: (-r["avg_engagement"], r["key"]))


def top_posts(posts, n=3):
    return sorted(posts, key=engagement, reverse=True)[:n]


def bottom_posts(posts, n=3):
    return sorted(posts, key=engagement)[:n]


def _month_stats(posts, month):
    items = [p for p in posts if p["published_at"][:7] == month]
    return {
        "posts": len(items),
        "avg_engagement": round(mean(engagement(p) for p in items), 1) if items else 0,
        "avg_saves": round(mean(p["saves"] for p in items), 1) if items else 0,
    }


def month_over_month(posts, month, previous_month):
    current, previous = _month_stats(posts, month), _month_stats(posts, previous_month)
    result = {}
    for metric in ("posts", "avg_engagement", "avg_saves"):
        prev = previous[metric]
        change = round((current[metric] - prev) * 100 / prev, 1) if prev else None
        result[metric] = {"current": current[metric], "previous": prev, "change_pct": change}
    return result


def summarize_for_coach(snapshot, posts):
    if snapshot is None and not posts:
        return None
    summary = {
        "followers": snapshot["followers"] if snapshot else None,
        "follower_change": snapshot["follower_change"] if snapshot else None,
        "post_count": len(posts),
        "avg_engagement": round(mean(engagement(p) for p in posts), 1) if posts else None,
        "avg_saves": round(mean(p["saves"] for p in posts), 1) if posts else None,
        "best_format": None,
    }
    by_format = performance_by(posts, "format")
    if by_format:
        summary["best_format"] = by_format[0]["key"]
    return summary


def performance_hints(matched_posts):
    if not matched_posts:
        return None

    def best(key):
        rows = performance_by(matched_posts, key)
        return rows[0]["key"] if rows else None

    return {"best_pillar": best("pillar"), "best_format": best("format"), "best_weekday": best("weekday")}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_insights.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add content-creator/insights.py content-creator/tests/test_insights.py
git commit -m "feat: add insights (performance by pillar/format/weekday, top posts, month over month)"
```

---

### Task 5: Gentle recap (deterministic fallback plus AI phrasing)

**Files:**
- Create: `content-creator/recap.py`, `content-creator/prompts/insight_phrase.md`
- Test: `content-creator/tests/test_recap.py`

**Interfaces:**
- Consumes: `insights.performance_by`, `insights.top_posts`, `insights.month_over_month`, `insights.engagement` (Task 4); `tone_guard.GENTLE_TONE_RULE`, `tone_guard.find_harsh_words` (Strategy Coach plan, Task 1); `pipeline._invoke`, `ai._call_claude`, `ai._parse_json_response`, `ai.calculate_cost`, `ai.render_prompt`, `ai.load_prompt`, `ai.InvalidAIResponseError`.
- Cross-plan: strategy-coach (final ticket)
- Produces: `recap.build_recap(matched_posts: list[dict], month: str, previous_month: str) -> dict` (`{"month","post_count","best_pillar","best_format","best_weekday","top_post": {"caption","engagement"} | None,"change": <month_over_month result>}`; `matched_posts` may lack pillars)
  - `recap.fallback_phrases(recap: dict) -> dict` (`{"headline": str, "highlights": list[str], "suggestions": list[str]}`; deterministic, gentle, PT-PT, never blames)
  - `recap.validate_phrases(data: dict) -> dict` (raises `ai.InvalidAIResponseError` on bad shape or any word flagged by `tone_guard.find_harsh_words`)
  - `recap.phrase_recap(client, recap: dict, brand_pack: str) -> tuple[dict, int, int, float]`
  - `recap.recap_phrases(client, conn, recap, brand_pack, daily_cap_usd, on_step=None, phraser=None) -> dict` (tries the AI through `pipeline._invoke`; on any exception, including the spend cap, returns `fallback_phrases(recap)`)

- [ ] **Step 1: Create `prompts/insight_phrase.md`**

```
Vais transformar números de desempenho de redes sociais numa pequena mensagem de resumo do mês, para uma pessoa que trabalha sozinha e pode estar cansada ou desmotivada.

{{TONE_RULE}}

Regras:
- Começa sempre pelo que correu bem, mesmo que seja pouco (a constância também conta).
- Nunca uses palavras de alarme, culpa ou urgência. Lacunas são convites: "se te apetecer...", "quando fizer sentido para ti...".
- Não inventes números: usa apenas os que recebes.
- Responde APENAS com um objecto JSON válido, sem texto adicional:
{"headline": "uma frase acolhedora", "highlights": ["2 a 3 frases sobre o que resultou"], "suggestions": ["1 a 3 sugestões leves e opcionais para o próximo mês"]}
```

- [ ] **Step 2: Write the failing tests**

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import analytics_store
import db
import recap
import tone_guard


def post(post_id, published_at, fmt, likes, saves=0, pillar=None):
    return {"post_id": post_id, "published_at": published_at, "format": fmt, "caption": f"legenda {post_id}",
            "likes": likes, "comments": 0, "saves": saves, "shares": 0, "reach": 100, "impressions": 100, "pillar": pillar}


POSTS = [
    post("a", "2026-07-06T10:00:00+0000", "carousel", 100, saves=40, pillar="Educar"),
    post("b", "2026-07-08T10:00:00+0000", "reel", 10, pillar="Bastidores"),
    post("c", "2026-06-10T10:00:00+0000", "post", 20, pillar="Educar"),
]


def test_build_recap_summarises_best_groups_and_top_post():
    r = recap.build_recap(POSTS, "2026-07", "2026-06")
    assert r["month"] == "2026-07" and r["post_count"] == 2
    assert r["best_pillar"] == "Educar" and r["best_format"] == "carousel"
    assert r["top_post"] == {"caption": "legenda a", "engagement": 140}
    assert r["change"]["posts"]["current"] == 2


def test_build_recap_with_no_posts_this_month_is_still_valid():
    r = recap.build_recap([], "2026-07", "2026-06")
    assert r["post_count"] == 0 and r["top_post"] is None and r["best_pillar"] is None


def test_fallback_phrases_are_gentle_for_busy_and_for_empty_months():
    for data in (recap.build_recap(POSTS, "2026-07", "2026-06"), recap.build_recap([], "2026-07", "2026-06")):
        phrases = recap.fallback_phrases(data)
        text = " ".join([phrases["headline"], *phrases["highlights"], *phrases["suggestions"]])
        assert tone_guard.find_harsh_words(text) == [] and phrases["headline"]
        assert isinstance(phrases["highlights"], list) and isinstance(phrases["suggestions"], list)


def test_fallback_for_an_empty_month_is_an_invitation_not_a_warning():
    phrases = recap.fallback_phrases(recap.build_recap([], "2026-07", "2026-06"))
    assert "quando te apetecer" in " ".join(phrases["suggestions"]).lower() or "se te apetecer" in " ".join(phrases["suggestions"]).lower()


def test_validate_phrases_rejects_harsh_wording_and_bad_shapes():
    good = {"headline": "Que mês bonito", "highlights": ["Foste constante."], "suggestions": ["Se te apetecer, mais reels."]}
    assert recap.validate_phrases(good) is good
    with pytest.raises(ai.InvalidAIResponseError):
        recap.validate_phrases({**good, "headline": "Situação crítica"})
    with pytest.raises(ai.InvalidAIResponseError):
        recap.validate_phrases({"headline": "x", "highlights": "não é lista", "suggestions": []})


def fake_client(payload):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=100, output_tokens=50), stop_reason="end_turn",
    )
    return client


def test_phrase_recap_prompt_has_numbers_and_tone_rule():
    client = fake_client({"headline": "Bom mês", "highlights": ["a"], "suggestions": ["b"]})
    data = recap.build_recap(POSTS, "2026-07", "2026-06")
    phrases, tin, tout, cost = recap.phrase_recap(client, data, "brand")
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "gentil" in prompt and "Educar" in prompt and phrases["headline"] == "Bom mês" and cost > 0


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


def test_recap_phrases_uses_ai_and_logs_cost(conn):
    data = recap.build_recap(POSTS, "2026-07", "2026-06")
    phraser = lambda client, r, brand: ({"headline": "Bom mês", "highlights": ["a"], "suggestions": ["b"]}, 10, 5, 0.001)
    phrases = recap.recap_phrases(MagicMock(), conn, data, "brand", 2.0, phraser=phraser)
    assert phrases["headline"] == "Bom mês"
    assert conn.execute("SELECT COUNT(*) FROM api_calls WHERE function = 'recap_phrases'").fetchone()[0] == 1


def test_recap_phrases_falls_back_when_the_ai_fails_or_the_cap_is_hit(conn):
    data = recap.build_recap(POSTS, "2026-07", "2026-06")

    def broken(client, r, brand):
        raise RuntimeError("api em baixo")

    assert recap.recap_phrases(MagicMock(), conn, data, "brand", 2.0, phraser=broken) == recap.fallback_phrases(data)
    conn.execute("INSERT INTO api_calls (function, tokens_in, tokens_out, estimated_cost_usd, created_at) VALUES ('x',1,1,99,datetime('now'))")
    conn.commit()
    phraser = lambda client, r, brand: ({"headline": "x", "highlights": [], "suggestions": []}, 1, 1, 0.0)
    assert recap.recap_phrases(MagicMock(), conn, data, "brand", 1.0, phraser=phraser) == recap.fallback_phrases(data)
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_recap.py -v`
Expected: FAIL (`ModuleNotFoundError: recap`).

- [ ] **Step 4: Implement `recap.py`**

```python
import json

import ai
import insights
import pipeline
from tone_guard import GENTLE_TONE_RULE, find_harsh_words

_FORMAT_PT = {"post": "publicações", "carousel": "carrosséis", "reel": "reels", "story": "stories"}


def build_recap(matched_posts, month, previous_month):
    current = [p for p in matched_posts if p["published_at"][:7] == month]
    top = insights.top_posts(current, n=1)
    by_pillar = insights.performance_by(current, "pillar")
    by_format = insights.performance_by(current, "format")
    by_weekday = insights.performance_by(current, "weekday")
    return {
        "month": month,
        "post_count": len(current),
        "best_pillar": by_pillar[0]["key"] if by_pillar else None,
        "best_format": by_format[0]["key"] if by_format else None,
        "best_weekday": by_weekday[0]["key"] if by_weekday else None,
        "top_post": {"caption": top[0]["caption"][:80], "engagement": insights.engagement(top[0])} if top else None,
        "change": insights.month_over_month(matched_posts, month, previous_month),
    }


def fallback_phrases(recap):
    if recap["post_count"] == 0:
        return {
            "headline": "Este mês foi de pausa, e está tudo bem.",
            "highlights": ["Os teus dados continuam aqui à tua espera, sem pressa."],
            "suggestions": ["Quando te apetecer, posso sugerir uma ideia leve para voltares ao teu ritmo."],
        }
    highlights = [f"Publicaste {recap['post_count']} vez(es) este mês. Obrigada pela tua constância."]
    if recap["best_pillar"]:
        highlights.append(f"As publicações de {recap['best_pillar']} foram as que mais interacção tiveram, um bom sinal.")
    if recap["top_post"]:
        highlights.append(f"A publicação «{recap['top_post']['caption']}» foi a que mais pessoas tocou.")
    suggestions = []
    if recap["best_format"]:
        suggestions.append(f"Se te apetecer, o próximo mês pode ter mais {_FORMAT_PT[recap['best_format']]}.")
    if recap["best_weekday"]:
        suggestions.append(f"A {recap['best_weekday']} parece ser um dia simpático para publicares.")
    return {"headline": "Que bom olhar para o teu mês.", "highlights": highlights, "suggestions": suggestions}


def validate_phrases(data):
    if (
        not isinstance(data, dict) or not isinstance(data.get("headline"), str)
        or not isinstance(data.get("highlights"), list) or not isinstance(data.get("suggestions"), list)
    ):
        raise ai.InvalidAIResponseError("O resumo do mês não veio no formato esperado.")
    text = " ".join([data["headline"], *map(str, data["highlights"]), *map(str, data["suggestions"])])
    if find_harsh_words(text):
        raise ai.InvalidAIResponseError("O resumo do mês usou palavras demasiado duras.")
    return data


def phrase_recap(client, recap, brand_pack):
    prompt = ai.render_prompt(ai.load_prompt("insight_phrase"), tone_rule=GENTLE_TONE_RULE)
    prompt = f"{prompt}\n\n## Números do mês\n{json.dumps(recap, ensure_ascii=False)}"
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    return validate_phrases(ai._parse_json_response(text)), tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)


def recap_phrases(client, conn, recap, brand_pack, daily_cap_usd, on_step=None, phraser=None):
    try:
        return pipeline._invoke(
            conn, None, daily_cap_usd, "recap_phrases",
            lambda: (phraser or phrase_recap)(client, recap, brand_pack), on_step=on_step,
        )
    except Exception:
        return fallback_phrases(recap)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_recap.py -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add content-creator/recap.py content-creator/prompts/insight_phrase.md content-creator/tests/test_recap.py
git commit -m "feat: add gentle monthly recap with deterministic fallback"
```

---

### Task 6: Definições tab (Contas ligadas)

**Files:**
- Create: `content-creator/ui_settings.py`
- Modify: `content-creator/app.py` (imports; schema init; tab list; tab block at end)
- Test: `content-creator/tests/test_ui_settings.py`

**Interfaces:**
- Consumes: `analytics_store.init_schema`, `set_setting`, `get_setting` (Task 2); `windsor.fetch_account`, `windsor.WindsorError` (Task 1); `tone_guard.find_harsh_words` (Strategy Coach plan, Task 1).
- Cross-plan: strategy-coach (final ticket)
- Produces: `ui_settings.ACCOUNT_KEY = "windsor_account_id"`, `ui_settings.COPY: dict[str, str]`
  - `ui_settings.windsor_status(conn, brand_pack: str, env: Mapping) -> str` (`"no_key"` when `WINDSOR_API_KEY` is missing/empty, else `"no_account"` when no account id is saved, else `"ready"`)
  - `ui_settings.get_windsor_credentials(conn, brand_pack, env=os.environ) -> tuple[str, str] | None` (`(api_key, account_id)` when status is `ready`)
  - `ui_settings.check_connection(api_key, account_id, today=None, fetcher=windsor.fetch_account) -> tuple[bool, str]` (gentle message either way; never raises)
  - `ui_settings.render(cfg, conn) -> None`
  - New tab "Definições" in `app.py`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from pathlib import Path

import analytics_store
import db
import tone_guard
import ui_settings
import windsor
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def make_conn():
    conn = db.get_connection(":memory:")
    analytics_store.init_schema(conn)
    return conn


def test_copy_passes_the_tone_guard():
    for key, text in ui_settings.COPY.items():
        assert tone_guard.find_harsh_words(text) == [], key


def test_windsor_status_progression():
    conn = make_conn()
    assert ui_settings.windsor_status(conn, "b", {}) == "no_key"
    assert ui_settings.windsor_status(conn, "b", {"WINDSOR_API_KEY": ""}) == "no_key"
    assert ui_settings.windsor_status(conn, "b", {"WINDSOR_API_KEY": "K"}) == "no_account"
    analytics_store.set_setting(conn, "b", ui_settings.ACCOUNT_KEY, "acc1")
    assert ui_settings.windsor_status(conn, "b", {"WINDSOR_API_KEY": "K"}) == "ready"


def test_get_windsor_credentials_only_when_ready():
    conn = make_conn()
    assert ui_settings.get_windsor_credentials(conn, "b", {"WINDSOR_API_KEY": "K"}) is None
    analytics_store.set_setting(conn, "b", ui_settings.ACCOUNT_KEY, "acc1")
    assert ui_settings.get_windsor_credentials(conn, "b", {"WINDSOR_API_KEY": "K"}) == ("K", "acc1")


def test_check_connection_success_and_failure_messages_are_gentle():
    ok, message = ui_settings.check_connection("K", "acc", today=date(2026, 7, 15), fetcher=lambda *a: {"followers": 5})
    assert ok is True and tone_guard.find_harsh_words(message) == []

    def boom(*args):
        raise windsor.WindsorError("Não consegui falar com o Windsor agora.")

    ok, message = ui_settings.check_connection("K", "acc", today=date(2026, 7, 15), fetcher=boom)
    assert ok is False and "Windsor" in message and tone_guard.find_harsh_words(message) == []


def test_settings_tab_explains_how_to_connect_when_there_is_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    monkeypatch.delenv("WINDSOR_API_KEY", raising=False)
    at = AppTest.from_file(APP_PATH)
    at.run()
    assert not at.exception
    assert "Definições" in [t.label for t in at.tabs]
    assert any("WINDSOR_API_KEY" in m.value for m in at.markdown) or any("WINDSOR_API_KEY" in i.value for i in at.info)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_settings.py -v`
Expected: FAIL (`ModuleNotFoundError: ui_settings`).

- [ ] **Step 3: Implement `ui_settings.py`**

```python
import os
from datetime import date, timedelta

import streamlit as st

import analytics_store
import windsor

ACCOUNT_KEY = "windsor_account_id"

COPY = {
    "title": "Contas ligadas",
    "no_key": "Para ligarmos o Windsor, adiciona a chave ao ficheiro .env como WINDSOR_API_KEY=a_tua_chave e reinicia a app. É só uma vez.",
    "no_account": "A chave já está pronta. Falta só dizeres qual é a conta do Windsor a usar.",
    "ready": "Tudo pronto: o Windsor está ligado a este perfil.",
    "account_label": "Conta do Windsor para este perfil",
    "save": "Guardar",
    "test": "Testar a ligação",
    "test_ok": "Tudo pronto! Consegui ler os teus dados do Windsor.",
    "test_retry": "Ainda não consegui ler os dados. Podemos tentar de novo quando quiseres.",
    "later": "Mais tarde poderás ligar outras redes sociais a partir daqui.",
}


def windsor_status(conn, brand_pack, env):
    if not env.get("WINDSOR_API_KEY"):
        return "no_key"
    if not analytics_store.get_setting(conn, brand_pack, ACCOUNT_KEY):
        return "no_account"
    return "ready"


def get_windsor_credentials(conn, brand_pack, env=None):
    env = env if env is not None else os.environ
    if windsor_status(conn, brand_pack, env) != "ready":
        return None
    return env["WINDSOR_API_KEY"], analytics_store.get_setting(conn, brand_pack, ACCOUNT_KEY)


def check_connection(api_key, account_id, today=None, fetcher=windsor.fetch_account):
    today = today or date.today()
    try:
        fetcher(api_key, account_id, (today - timedelta(days=7)).isoformat(), today.isoformat())
    except windsor.WindsorError as e:
        return False, f"{e} {COPY['test_retry']}"
    except Exception:
        return False, COPY["test_retry"]
    return True, COPY["test_ok"]


def render(cfg, conn):
    st.subheader(COPY["title"])
    status = windsor_status(conn, cfg.brand_pack, os.environ)
    if status == "no_key":
        st.info(COPY["no_key"])
    account = st.text_input(
        COPY["account_label"], value=analytics_store.get_setting(conn, cfg.brand_pack, ACCOUNT_KEY, ""),
        key="windsor_account_input",
    )
    if st.button(COPY["save"], key="windsor_account_save") and account.strip():
        analytics_store.set_setting(conn, cfg.brand_pack, ACCOUNT_KEY, account.strip())
        st.rerun()
    if status == "no_account":
        st.info(COPY["no_account"])
    if status == "ready":
        st.success(COPY["ready"])
        if st.button(COPY["test"], key="windsor_test"):
            api_key, account_id = get_windsor_credentials(conn, cfg.brand_pack)
            ok, message = check_connection(api_key, account_id)
            (st.success if ok else st.info)(message)
    st.caption(COPY["later"])
```

- [ ] **Step 4: Wire into `app.py`**

1. Add `import analytics_store` and `import ui_settings` to the imports.
2. After `db.init_db(conn)` (and any other `init_schema` calls) add `analytics_store.init_schema(conn)`.
3. Add `"Definições"` to the `st.tabs([...])` list, unpacking a new variable `tab_settings` (append after the existing tabs).
4. At the end of the file add:

```python
with tab_settings:
    ui_settings.render(cfg, conn)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite, including `test_app_smoke.py`).

- [ ] **Step 6: Commit**

```bash
git add content-creator/ui_settings.py content-creator/app.py content-creator/tests/test_ui_settings.py
git commit -m "feat: add Definições tab with Windsor connection per brand"
```

---

### Task 7: Resultados tab (refresh, headline numbers, best posts, recap)

**Files:**
- Create: `content-creator/ui_results.py`
- Modify: `content-creator/app.py` (imports, `STEP_LABELS`, tab list, tab block)
- Test: `content-creator/tests/test_ui_results.py`

**Interfaces:**
- Consumes: `analytics_refresh.refresh` (Task 3); `analytics_store.latest_snapshot`, `snapshot_before`, `list_posts` (Task 2); `insights.*` (Task 4); `recap.build_recap`, `recap.recap_phrases` (Task 5); `ui_settings.get_windsor_credentials`, `ui_settings.windsor_status` (Task 6); `windsor.WindsorError` (Task 1); `tone_guard.find_harsh_words` (Strategy Coach plan, Task 1).
- Cross-plan: strategy-coach (final ticket)
- Produces: `ui_results.COPY: dict[str, str]`
  - `ui_results.format_last_updated(iso: str | None, now: datetime | None = None) -> str` (e.g. `"Última actualização: hoje às 14:30"`, `"... ontem às 09:05"`, `"... a 03/07 às 09:05"`, or a gentle "ainda sem dados" line for `None`)
  - `ui_results.headline_metrics(snapshot: dict | None, previous: dict | None) -> list[dict]` (`[{"label","value","delta"}]` for followers, reach, impressions, profile visits; `delta` is `None` without a previous snapshot; empty list for `None`)
  - `ui_results.previous_month(month: str) -> str`
  - `ui_results.render(cfg, conn, client, run_with_progress) -> None`
  - New tab "Resultados" in `app.py`.
  - The tab keeps working when slots are unavailable: pillar tables only appear when `posts` carry pillars (Task 8 supplies matching; here posts are used unmatched, so only format/weekday tables are shown).

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

import tone_guard
import ui_results

APP_PATH = str(Path(__file__).parent.parent / "app.py")
NOW = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)


def test_copy_passes_the_tone_guard():
    for key, text in ui_results.COPY.items():
        assert tone_guard.find_harsh_words(text) == [], key


def test_format_last_updated():
    assert "hoje às 14:30" in ui_results.format_last_updated("2026-07-15T14:30:00+00:00", NOW)
    assert "ontem às 09:05" in ui_results.format_last_updated("2026-07-14T09:05:00+00:00", NOW)
    assert "03/07 às 09:05" in ui_results.format_last_updated("2026-07-03T09:05:00+00:00", NOW)
    assert "ainda" in ui_results.format_last_updated(None, NOW).lower()


def test_headline_metrics_with_and_without_previous_snapshot():
    snap = {"followers": 1100, "reach": 5000, "impressions": 8000, "profile_views": 300, "follower_change": 40}
    prev = {"followers": 1000, "reach": 4000, "impressions": 8000, "profile_views": 250, "follower_change": 10}
    metrics = ui_results.headline_metrics(snap, prev)
    assert [m["label"] for m in metrics] == ["Seguidores", "Alcance", "Impressões", "Visitas ao perfil"]
    assert metrics[0]["value"] == 1100 and metrics[0]["delta"] == 100
    assert ui_results.headline_metrics(snap, None)[0]["delta"] is None
    assert ui_results.headline_metrics(None, None) == []


def test_previous_month_wraps_the_year():
    assert ui_results.previous_month("2026-07") == "2026-06"
    assert ui_results.previous_month("2026-01") == "2025-12"


def test_results_tab_is_calm_when_windsor_is_not_connected(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    monkeypatch.delenv("WINDSOR_API_KEY", raising=False)
    at = AppTest.from_file(APP_PATH)
    at.run()
    assert not at.exception
    assert "Resultados" in [t.label for t in at.tabs]
    assert any("Definições" in i.value for i in at.info)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ui_results.py -v`
Expected: FAIL (`ModuleNotFoundError: ui_results`).

- [ ] **Step 3: Implement `ui_results.py`**

```python
import os
from datetime import datetime, timezone

import streamlit as st

import analytics_refresh
import analytics_store
import insights
import recap as recap_module
import ui_settings
import windsor

COPY = {
    "not_connected": "Ainda não ligámos o Windsor a este perfil. Quando quiseres, vai à aba Definições e eu explico o passo a passo.",
    "refresh": "Atualizar dados",
    "refreshed": "Dados atualizados.",
    "reused": "Acabaste de atualizar, por isso mostro os dados mais recentes.",
    "no_data": "Ainda não temos dados guardados. Clica em Atualizar dados para eu ir buscá-los.",
    "recap_button": "Ver o resumo do mês",
    "recap_title": "O teu mês, com carinho",
    "best_posts": "As publicações que mais pessoas tocaram",
    "by_format": "O que funciona melhor, por formato",
    "by_weekday": "Por dia da semana",
}


def format_last_updated(iso, now=None):
    if not iso:
        return "Ainda não atualizámos os dados."
    now = now or datetime.now(timezone.utc)
    moment = datetime.fromisoformat(iso)
    days = (now.date() - moment.date()).days
    clock = moment.strftime("%H:%M")
    if days == 0:
        return f"Última atualização: hoje às {clock}"
    if days == 1:
        return f"Última atualização: ontem às {clock}"
    return f"Última atualização: a {moment.strftime('%d/%m')} às {clock}"


def headline_metrics(snapshot, previous):
    if snapshot is None:
        return []
    fields = (("Seguidores", "followers"), ("Alcance", "reach"), ("Impressões", "impressions"), ("Visitas ao perfil", "profile_views"))
    return [
        {"label": label, "value": snapshot[key], "delta": (snapshot[key] - previous[key]) if previous else None}
        for label, key in fields
    ]


def previous_month(month):
    year, mon = (int(x) for x in month.split("-"))
    return f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"


def _refresh(cfg, conn, credentials):
    api_key, account_id = credentials
    try:
        result = analytics_refresh.refresh(conn, cfg.brand_pack, api_key, account_id)
    except windsor.WindsorError as e:
        st.info(str(e))
        return
    st.success(COPY["refreshed"] if result["fetched"] else COPY["reused"])


def render(cfg, conn, client, run_with_progress):
    credentials = ui_settings.get_windsor_credentials(conn, cfg.brand_pack)
    if credentials is None:
        st.info(COPY["not_connected"])
        return
    if st.button(COPY["refresh"], type="primary", key="results_refresh"):
        _refresh(cfg, conn, credentials)
    st.caption(format_last_updated(analytics_store.last_fetched_at(conn, cfg.brand_pack)))

    snapshot = analytics_store.latest_snapshot(conn, cfg.brand_pack)
    posts = analytics_store.list_posts(conn, cfg.brand_pack)
    if snapshot is None:
        st.info(COPY["no_data"])
        return
    previous = analytics_store.snapshot_before(conn, cfg.brand_pack, snapshot["period_start"])
    columns = st.columns(4)
    for column, metric in zip(columns, headline_metrics(snapshot, previous)):
        column.metric(metric["label"], metric["value"], metric["delta"])

    if posts:
        st.markdown(f"#### {COPY['best_posts']}")
        for post in insights.top_posts(posts, n=3):
            st.markdown(f"- **{post['published_at'][:10]}** · {post['caption'][:90]} ({insights.engagement(post)} interações)")
        st.markdown(f"#### {COPY['by_format']}")
        st.dataframe(insights.performance_by(posts, "format"), use_container_width=True)
        st.markdown(f"#### {COPY['by_weekday']}")
        st.dataframe(insights.performance_by(posts, "weekday"), use_container_width=True)

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if st.button(COPY["recap_button"], key="results_recap"):
        data = recap_module.build_recap(posts, month, previous_month(month))
        phrases = recap_module.recap_phrases(client, conn, data, cfg.brand_pack, cfg.max_daily_spend_usd)
        st.markdown(f"#### {COPY['recap_title']}")
        st.write(phrases["headline"])
        for line in phrases["highlights"] + phrases["suggestions"]:
            st.markdown(f"- {line}")
```

- [ ] **Step 4: Wire into `app.py`**

1. Add `import ui_results`.
2. Add `"Resultados"` to the `st.tabs([...])` list, unpacking a new variable `tab_results` (append after the existing tabs).
3. Extend `STEP_LABELS` with `"recap_phrases": "A preparar o resumo do mês"`.
4. At the end of the file add:

```python
with tab_results:
    ui_results.render(cfg, conn, client, run_with_progress)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite).

- [ ] **Step 6: Commit**

```bash
git add content-creator/ui_results.py content-creator/app.py content-creator/tests/test_ui_results.py
git commit -m "feat: add Resultados tab (refresh button, headline numbers, best posts, gentle recap)"
```

---

### Task 8: Feed results back into the Coach and the Calendar

**Files:**
- Create: `content-creator/windsor_bridge.py`
- Modify: `content-creator/calendar_store.py` (add `list_brand_slots`), `content-creator/ui_coach.py` (`_render_questions`), `content-creator/ui_calendar.py` (`render`), `content-creator/ui_results.py` (pillar tables when matches exist)
- Test: `content-creator/tests/test_windsor_bridge.py`

**Interfaces:**
- Consumes: `analytics_store.latest_snapshot`, `list_posts` (Task 2); `insights.summarize_for_coach`, `match_posts_to_slots`, `performance_hints`, `performance_by` (Task 4); `calendar_store.list_slots`/tables (Content Calendar plan, Task 1); `coach.draft_strategy(..., windsor_summary=...)` (Strategy Coach plan, Task 9); `calendar_generate.generate_month(..., performance=...)` (Content Calendar plan, Task 4); `ui_coach._render_questions`, `ui_calendar.render` (Strategy Coach Task 10, Content Calendar Task 6); `ui_results.render` is modified here (Task 7).
- Cross-plan: strategy-coach (final ticket), content-calendar (final ticket)
- Produces: `calendar_store.list_brand_slots(conn, brand_pack) -> list[dict]` (all slots of the brand, ordered by date)
  - `windsor_bridge.coach_evidence(conn, brand_pack) -> dict | None` (`insights.summarize_for_coach(latest snapshot, posts)`)
  - `windsor_bridge.matched_posts(conn, brand_pack) -> list[dict]` (posts matched to calendar slots)
  - `windsor_bridge.calendar_performance(conn, brand_pack) -> dict | None` (`insights.performance_hints(matched_posts)`)

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import analytics_store
import calendar_store
import db
import windsor_bridge

SNAP = {"followers": 1030, "follower_change": 30, "reach": 600, "impressions": 900, "profile_views": 30}


def post(post_id, published_at, fmt, likes, saves=0):
    return {"post_id": post_id, "published_at": published_at, "format": fmt, "caption": post_id,
            "likes": likes, "comments": 0, "saves": saves, "shares": 0, "reach": 100, "impressions": 100}


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    analytics_store.init_schema(connection)
    calendar_store.init_schema(connection)
    return connection


def test_everything_is_none_without_analytics(conn):
    assert windsor_bridge.coach_evidence(conn, "b") is None
    assert windsor_bridge.calendar_performance(conn, "b") is None
    assert windsor_bridge.matched_posts(conn, "b") == []


def test_coach_evidence_summarises_snapshot_and_posts(conn):
    analytics_store.save_snapshot(conn, "b", SNAP, "2026-06-01", "2026-07-15", "2026-07-15T12:00:00+00:00")
    analytics_store.upsert_posts(conn, "b", [post("a", "2026-07-06T10:00:00+0000", "carousel", 100, saves=40)], "t")
    evidence = windsor_bridge.coach_evidence(conn, "b")
    assert evidence["followers"] == 1030 and evidence["best_format"] == "carousel"


def test_calendar_performance_uses_slot_pillars(conn):
    plan = calendar_store.save_month_plan(conn, "b", "2026-07")
    calendar_store.add_slot(conn, plan, "b", "2026-07-06", "carousel", "Educar", "Confiança", "g", "t", cta_category="education")
    calendar_store.add_slot(conn, plan, "b", "2026-07-08", "reel", "Bastidores", "Descoberta", "g", "t")
    analytics_store.upsert_posts(conn, "b", [
        post("a", "2026-07-06T10:00:00+0000", "carousel", 100, saves=40),
        post("b", "2026-07-08T10:00:00+0000", "reel", 10),
    ], "t")
    hints = windsor_bridge.calendar_performance(conn, "b")
    assert hints["best_pillar"] == "Educar" and hints["best_format"] == "carousel"
    assert {p["pillar"] for p in windsor_bridge.matched_posts(conn, "b")} == {"Educar", "Bastidores"}


def test_list_brand_slots_is_brand_scoped_and_date_ordered(conn):
    plan_a = calendar_store.save_month_plan(conn, "a", "2026-07")
    plan_b = calendar_store.save_month_plan(conn, "b", "2026-07")
    calendar_store.add_slot(conn, plan_a, "a", "2026-07-09", "post", "P", "F", "g", "t2")
    calendar_store.add_slot(conn, plan_a, "a", "2026-07-02", "post", "P", "F", "g", "t1")
    calendar_store.add_slot(conn, plan_b, "b", "2026-07-01", "post", "P", "F", "g", "tb")
    assert [s["topic"] for s in calendar_store.list_brand_slots(conn, "a")] == ["t1", "t2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_windsor_bridge.py -v`
Expected: FAIL (`ModuleNotFoundError: windsor_bridge`).

- [ ] **Step 3: Implement**

Add to `calendar_store.py`:

```python
def list_brand_slots(conn, brand_pack):
    rows = conn.execute(
        "SELECT * FROM calendar_slots WHERE brand_pack = ? ORDER BY date, id", (brand_pack,)
    ).fetchall()
    return [_slot_row(r) for r in rows]
```

Create `windsor_bridge.py`:

```python
import analytics_store
import calendar_store
import insights


def coach_evidence(conn, brand_pack):
    return insights.summarize_for_coach(
        analytics_store.latest_snapshot(conn, brand_pack), analytics_store.list_posts(conn, brand_pack),
    )


def matched_posts(conn, brand_pack):
    return insights.match_posts_to_slots(
        analytics_store.list_posts(conn, brand_pack), calendar_store.list_brand_slots(conn, brand_pack),
    )


def calendar_performance(conn, brand_pack):
    return insights.performance_hints(matched_posts(conn, brand_pack))
```

- [ ] **Step 4: Wire into the Coach and the Calendar**

1. `ui_coach.py`, in `_render_questions`: add `import windsor_bridge` and change the drafting call to `coach.draft_strategy(client, conn, strategy_id, cfg.brand_pack, cfg.max_daily_spend_usd, windsor_summary=windsor_bridge.coach_evidence(conn, cfg.brand_pack))`.
2. `ui_calendar.py`, in `render`: add `import windsor_bridge` and pass `performance=windsor_bridge.calendar_performance(conn, cfg.brand_pack)` to the `calendar_generate.generate_month` call.
3. `ui_results.py`, in `render`: replace `posts = analytics_store.list_posts(...)` with `posts = windsor_bridge.matched_posts(conn, cfg.brand_pack)` (add the import) and, right after the by-format table, add a "Por pilar" section only when `insights.performance_by(posts, "pillar")` is non-empty:

```python
        by_pillar = insights.performance_by(posts, "pillar")
        if by_pillar:
            st.markdown("#### Por pilar")
            st.dataframe(by_pillar, use_container_width=True)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite, including the smoke tests that load every tab).

- [ ] **Step 6: Commit**

```bash
git add content-creator/windsor_bridge.py content-creator/calendar_store.py content-creator/ui_coach.py content-creator/ui_calendar.py content-creator/ui_results.py content-creator/tests/test_windsor_bridge.py
git commit -m "feat: feed Windsor results into the Coach evidence and the calendar plan"
```

---

### Task 9: Opt-in "what worked" caption examples for drafts

**Files:**
- Modify: `content-creator/windsor_bridge.py` (add `caption_examples`), `content-creator/ai.py` (`build_context_block` learns the `examples` key), `content-creator/slot_bridge.py` (`build_draft_context` adds examples), `content-creator/ui_settings.py` (checkbox)
- Test: `content-creator/tests/test_caption_examples.py`

**Interfaces:**
- Consumes: `analytics_store.get_setting`/`set_setting`/`list_posts` (Task 2); `insights.top_posts` (Task 4); `windsor_bridge` and `ui_settings.ACCOUNT_KEY`, `ui_settings.render` (Task 6), (Task 8); `ai.build_context_block`, `slot_bridge.build_draft_context` (Calendar Link plan, Tasks 1 and 3).
- Cross-plan: calendar-post-link (final ticket)
- Produces: `windsor_bridge.EXAMPLES_KEY = "use_caption_examples"`
  - `windsor_bridge.caption_examples(conn, brand_pack, n=2, max_chars=300) -> list[str]` (`[]` unless the setting is `"1"`; otherwise the captions of the top-`n` posts by engagement, truncated)
  - `ai.build_context_block` renders `context["examples"]` (list of strings) as "Exemplos do que funcionou para esta pessoa (usa só o estilo; nunca copies o texto)"
  - `slot_bridge.build_draft_context` includes `examples` when non-empty

- [ ] **Step 1: Write the failing tests**

```python
import pytest

import ai
import analytics_store
import calendar_store
import coach_store
import db
import slot_bridge
import tone_prefs
import windsor_bridge


def post(post_id, likes, caption):
    return {"post_id": post_id, "published_at": "2026-07-06T10:00:00+0000", "format": "post", "caption": caption,
            "likes": likes, "comments": 0, "saves": 0, "shares": 0, "reach": 100, "impressions": 100}


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    for module in (analytics_store, calendar_store, coach_store, tone_prefs):
        module.init_schema(connection)
    analytics_store.upsert_posts(connection, "b", [post("a", 100, "A" * 500), post("b", 5, "curta"), post("c", 50, "média")], "t")
    return connection


def test_examples_are_off_by_default_and_on_when_opted_in(conn):
    assert windsor_bridge.caption_examples(conn, "b") == []
    analytics_store.set_setting(conn, "b", windsor_bridge.EXAMPLES_KEY, "1")
    examples = windsor_bridge.caption_examples(conn, "b", n=2, max_chars=300)
    assert len(examples) == 2 and len(examples[0]) == 300 and examples[1] == "média"
    analytics_store.set_setting(conn, "b", windsor_bridge.EXAMPLES_KEY, "0")
    assert windsor_bridge.caption_examples(conn, "b") == []


def test_context_block_renders_examples_with_a_never_copy_warning():
    block = ai.build_context_block({"examples": ["legenda que funcionou"]})
    assert "legenda que funcionou" in block and "nunca copies" in block


def test_build_draft_context_includes_examples_only_when_opted_in(conn):
    idea = db.get_idea(conn, db.create_idea(conn, "b", "manual", "tema"))
    assert slot_bridge.build_draft_context(conn, idea) is None
    analytics_store.set_setting(conn, "b", windsor_bridge.EXAMPLES_KEY, "1")
    context = slot_bridge.build_draft_context(conn, idea)
    assert context["examples"][0].startswith("A")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_caption_examples.py -v`
Expected: FAIL (`AttributeError: module 'windsor_bridge' has no attribute 'EXAMPLES_KEY'`).

- [ ] **Step 3: Implement**

In `windsor_bridge.py`:

```python
EXAMPLES_KEY = "use_caption_examples"


def caption_examples(conn, brand_pack, n=2, max_chars=300):
    if analytics_store.get_setting(conn, brand_pack, EXAMPLES_KEY) != "1":
        return []
    top = insights.top_posts(analytics_store.list_posts(conn, brand_pack), n=n)
    return [p["caption"][:max_chars] for p in top if p["caption"]]
```

In `ai.build_context_block`, before the `if not lines:` check, add:

```python
    if context.get("examples"):
        lines.append(
            "- Exemplos do que funcionou para esta pessoa (usa só o estilo; nunca copies o texto): "
            + " | ".join(context["examples"])
        )
```

In `slot_bridge.build_draft_context` (add `import windsor_bridge`), before `return context or None`:

```python
    examples = windsor_bridge.caption_examples(conn, idea["brand_pack"])
    if examples:
        context["examples"] = examples
```

In `ui_settings.render`, above the closing caption, add:

```python
    import windsor_bridge  # local import: keeps the settings module importable without the bridge in isolation tests

    use_examples = analytics_store.get_setting(conn, cfg.brand_pack, windsor_bridge.EXAMPLES_KEY) == "1"
    choice = st.checkbox(
        "Usar as minhas legendas com melhores resultados como exemplo de estilo nos rascunhos (opcional)",
        value=use_examples, key="use_caption_examples",
    )
    if choice != use_examples:
        analytics_store.set_setting(conn, cfg.brand_pack, windsor_bridge.EXAMPLES_KEY, "1" if choice else "0")
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests -q`
Expected: PASS (whole suite).

- [ ] **Step 5: Commit**

```bash
git add content-creator/windsor_bridge.py content-creator/ai.py content-creator/slot_bridge.py content-creator/ui_settings.py content-creator/tests/test_caption_examples.py
git commit -m "feat: add opt-in caption examples from best-performing posts"
```

---

## Final checklist (after all tasks are merged into `windsor-results`)

- [ ] Run the whole suite: `python -m pytest tests -q`.
- [ ] Confirm `windsor.ACCOUNT_FIELD_MAP` / `POST_FIELD_MAP` were verified against the real connector (Task 1, Step 1). If not, do it now and fix the maps.
- [ ] **One real end-to-end run against the user's real Windsor connection**: set `WINDSOR_API_KEY`, save the account in Definições, test the connection, press Atualizar dados in Resultados, check numbers against the Windsor dashboard, click the recap, then draft a strategy and a calendar month and confirm the Windsor evidence/performance reaches their prompts. Record any bug the mocks missed in `content-creator/docs/decisions.md`.
- [ ] Read every screen once for tone (missing data explained warmly; nothing urgent or blaming).
- [ ] Final whole-branch review, then merge `windsor-results` into `main`.
