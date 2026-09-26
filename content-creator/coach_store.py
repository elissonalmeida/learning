import json
from datetime import datetime, timezone

SECTION_KINDS = ("goals", "offers", "funnel", "pillars", "authority", "rhythm")
SECTION_STATES = ("draft", "accepted", "revisit")
SECTION_EVIDENCE_LEVELS = ("data", "pattern", "reasoned")


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
    data["profile"] = json.loads(data["profile_json"]) if data["profile_json"] is not None else None
    del data["profile_json"]
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
    if evidence not in SECTION_EVIDENCE_LEVELS:
        raise ValueError(f"Unknown section evidence: {evidence}")
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
    if kind not in SECTION_KINDS:
        raise ValueError(f"Unknown section kind: {kind}")
    if state not in SECTION_STATES:
        raise ValueError(f"Unknown section state: {state}")
    cursor = conn.execute(
        "UPDATE strategy_sections SET state = ?, updated_at = ? WHERE strategy_id = ? AND kind = ?",
        (state, _now(), strategy_id, kind),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"No section {kind!r} for strategy {strategy_id!r}")
    conn.commit()


def log_decision(conn, strategy_id, section_kind, action, user_reason=None):
    if section_kind not in SECTION_KINDS:
        raise ValueError(f"Unknown section kind: {section_kind}")
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
