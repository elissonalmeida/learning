"""Seam-crossing test: idea -> pipeline -> approve -> archive -> hard delete."""
from types import SimpleNamespace

import pytest

import ai
import db
import pipeline


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


def make_fake_ai_module():
    """A fake that generates a clean draft needing no revision."""

    def generate_draft(client, topic, tone, pillar, brand_pack):
        return {"caption": "legenda final", "slides": ["s1", "s2"]}, 1000, 400, 0.006

    def critique_draft(client, draft, brand_pack):
        return [], 800, 100, 0.0026

    def revise_draft(client, draft, flags, brand_pack):  # pragma: no cover - not reached
        raise AssertionError("revise_draft should not be called for a clean draft")

    return SimpleNamespace(
        generate_draft=generate_draft,
        critique_draft=critique_draft,
        revise_draft=revise_draft,
        MAX_REVISION_ROUNDS=ai.MAX_REVISION_ROUNDS,
    )


def test_idea_to_draft_to_approval_to_hard_delete(conn):
    idea_id = db.create_idea(
        conn, "marianabotelho-ig", "manual", "ashwagandha para o stress",
        pillar="Educativo Integrativo",
    )
    idea = db.get_idea(conn, idea_id)
    assert idea["status"] == "idea"

    draft, flags, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=make_fake_ai_module(),
    )
    assert draft["caption"] == "legenda final"
    assert flags == []
    assert rounds == 0
    assert db.get_idea(conn, idea_id)["status"] == "reviewed"

    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert [d["round"] for d in drafts] == [0]
    assert drafts[0]["slides"] == ["s1", "s2"]
    assert drafts[0]["quality_flags"] == []

    # Both AI calls were logged against the idea and counted towards spend.
    logged = conn.execute(
        "SELECT function FROM api_calls WHERE idea_id = ? ORDER BY id", (idea_id,)
    ).fetchall()
    assert [r["function"] for r in logged] == ["generate_draft", "critique_draft"]
    assert db.get_spend_today(conn) == pytest.approx(0.0086)

    db.update_idea_status(conn, idea_id, "approved")
    assert db.get_idea(conn, idea_id)["status"] == "approved"

    db.archive_idea(conn, idea_id)
    archived = db.get_idea(conn, idea_id)
    assert archived["status"] == "archived"
    assert archived["archived_at"] is not None
    assert idea_id not in [i["id"] for i in db.list_ideas(conn, brand_pack="marianabotelho-ig")]

    db.hard_delete_idea(conn, idea_id)
    assert db.get_idea(conn, idea_id) is None
    assert db.list_drafts_for_idea(conn, idea_id) == []

    # The spend audit trail survives, detached from the deleted idea.
    surviving = conn.execute("SELECT idea_id, function FROM api_calls ORDER BY id").fetchall()
    assert [r["function"] for r in surviving] == ["generate_draft", "critique_draft"]
    assert all(r["idea_id"] is None for r in surviving)
    assert db.get_spend_today(conn) == pytest.approx(0.0086)
