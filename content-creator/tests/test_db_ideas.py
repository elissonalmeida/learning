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

def test_hard_delete_removes_drafts_and_keeps_api_calls(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic G")
    db.create_draft(conn, idea_id, 0, "legenda", ["s1"], [])
    db.log_api_call(
        conn, "generate_draft", tokens_in=100, tokens_out=50,
        estimated_cost_usd=0.01, idea_id=idea_id,
    )
    db.archive_idea(conn, idea_id)
    db.hard_delete_idea(conn, idea_id)

    assert db.get_idea(conn, idea_id) is None
    assert db.list_drafts_for_idea(conn, idea_id) == []
    calls = conn.execute("SELECT * FROM api_calls").fetchall()
    assert len(calls) == 1
    assert calls[0]["idea_id"] is None
    assert calls[0]["estimated_cost_usd"] == 0.01


def test_update_draft_quality_flags(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic H")
    draft_id = db.create_draft(conn, idea_id, 0, "legenda", ["s1"], None)
    assert db.list_drafts_for_idea(conn, idea_id)[0]["quality_flags"] == []

    flags = [{"criterion": "Hook", "issue": "fraco"}]
    db.update_draft_quality_flags(conn, draft_id, flags)
    assert db.list_drafts_for_idea(conn, idea_id)[0]["quality_flags"] == flags


def test_update_idea_status(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "topic F")
    db.update_idea_status(conn, idea_id, "approved")
    assert db.get_idea(conn, idea_id)["status"] == "approved"
