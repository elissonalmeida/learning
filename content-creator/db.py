import sqlite3
from datetime import datetime, timezone
import json


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
    try:
        conn.execute("ALTER TABLE slide_images ADD COLUMN text_overflow INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
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
    # Drafts and slide_images belong to the idea and go with it; api_calls are
    # a spend audit trail that must survive the idea being cleaned up, so we
    # only null the link.
    conn.execute("DELETE FROM drafts WHERE idea_id = ?", (idea_id,))
    conn.execute("DELETE FROM slide_images WHERE idea_id = ?", (idea_id,))
    conn.execute("UPDATE api_calls SET idea_id = NULL WHERE idea_id = ?", (idea_id,))
    conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()


def update_idea_status(conn, idea_id, status):
    conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    conn.commit()


def create_draft(conn, idea_id, round_, caption, slides, quality_flags=None):
    cursor = conn.execute(
        "INSERT INTO drafts (idea_id, round, caption, slides, quality_flags, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (idea_id, round_, caption, json.dumps(slides), json.dumps(quality_flags or []), _now()),
    )
    conn.commit()
    return cursor.lastrowid


def update_draft_quality_flags(conn, draft_id, flags):
    conn.execute(
        "UPDATE drafts SET quality_flags = ? WHERE id = ?",
        (json.dumps(flags or []), draft_id),
    )
    conn.commit()


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


def create_slide_image(conn, idea_id, slide_index, prompt, file_path, cost_usd, text_overflow=False):
    cursor = conn.execute(
        "INSERT INTO slide_images "
        "(idea_id, slide_index, prompt, file_path, cost_usd, status, created_at, text_overflow) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
        (idea_id, slide_index, prompt, file_path, cost_usd, _now(), int(bool(text_overflow))),
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
