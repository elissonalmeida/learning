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
