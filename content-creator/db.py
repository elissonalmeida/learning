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
    conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()


def update_idea_status(conn, idea_id, status):
    conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    conn.commit()
