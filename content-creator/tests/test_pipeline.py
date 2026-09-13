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

    def extract_topics(client, reference_text, brand_pack):
        return [{"topic": "t", "pillar": "Educativo Integrativo"}], 500, 100, 0.02

    return SimpleNamespace(
        generate_draft=generate_draft,
        critique_draft=critique_draft,
        revise_draft=revise_draft,
        extract_topics=extract_topics,
        MAX_REVISION_ROUNDS=ai.MAX_REVISION_ROUNDS,
    )


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
    assert rounds == ai.MAX_REVISION_ROUNDS
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


def test_persists_flags_on_the_same_round_row(conn, idea):
    flags = [{"criterion": "Hook", "issue": "fraco"}]
    fake_ai = make_fake_ai_module(critique_sequence=[flags, []], revised_captions=["v1"])
    pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    drafts = db.list_drafts_for_idea(conn, idea["id"])
    assert len(drafts) == 2
    assert [d["quality_flags"] for d in drafts] == [flags, []]


def test_round_zero_draft_is_retained_when_critique_fails(conn, idea):
    def failing_critique(client, draft, brand_pack):
        raise ai.InvalidAIResponseError("resposta inválida")

    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    fake_ai.critique_draft = failing_critique

    with pytest.raises(ai.InvalidAIResponseError):
        pipeline.run_generation_pipeline(
            client=None, conn=conn, idea=idea, tone="Educativo-Científico",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        )
    drafts = db.list_drafts_for_idea(conn, idea["id"])
    assert [d["round"] for d in drafts] == [0]
    assert drafts[0]["caption"] == "v0"


def test_respects_injected_max_revision_rounds(conn, idea):
    still_failing = [{"criterion": "Hook", "issue": "fraco"}]
    fake_ai = make_fake_ai_module(
        critique_sequence=[still_failing, still_failing],
        revised_captions=["v1"],
    )
    fake_ai.MAX_REVISION_ROUNDS = 1
    _, _, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert rounds == 1


def test_raises_when_daily_cap_already_reached(conn, idea):
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.run_generation_pipeline(
            client=None, conn=conn, idea=idea, tone="Educativo-Científico",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        )


def test_run_extraction_logs_the_call_and_returns_topics(conn):
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    topics = pipeline.run_extraction(
        client=None, conn=conn, reference_text="texto qualquer",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert topics == [{"topic": "t", "pillar": "Educativo Integrativo"}]
    row = conn.execute("SELECT * FROM api_calls").fetchone()
    assert row["function"] == "extract_topics"
    assert row["estimated_cost_usd"] == pytest.approx(0.02)


def test_run_extraction_raises_when_daily_cap_already_reached(conn):
    db.log_api_call(conn, "extract_topics", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0)
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.run_extraction(
            client=None, conn=conn, reference_text="texto qualquer",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        )


def test_on_step_reports_running_then_done_for_each_call(conn, idea):
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    events = []
    pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        on_step=lambda step, status, detail=None: events.append((step, status)),
    )
    assert events == [
        ("generate_draft", "running"),
        ("generate_draft", "done"),
        ("critique_draft", "running"),
        ("critique_draft", "done"),
    ]


def test_on_step_reports_each_round_of_a_revision_loop(conn, idea):
    fake_ai = make_fake_ai_module(
        critique_sequence=[[{"criterion": "Hook", "issue": "fraco"}], []],
        revised_captions=["v1"],
    )
    events = []
    pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        on_step=lambda step, status, detail=None: events.append((step, status)),
    )
    assert events == [
        ("generate_draft", "running"), ("generate_draft", "done"),
        ("critique_draft", "running"), ("critique_draft", "done"),
        ("revise_draft", "running"), ("revise_draft", "done"),
        ("critique_draft", "running"), ("critique_draft", "done"),
    ]


def test_on_step_reports_error_with_detail_when_a_call_fails(conn, idea):
    def failing_critique(client, draft, brand_pack):
        raise ai.InvalidAIResponseError("resposta inválida")

    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    fake_ai.critique_draft = failing_critique
    events = []

    with pytest.raises(ai.InvalidAIResponseError):
        pipeline.run_generation_pipeline(
            client=None, conn=conn, idea=idea, tone="Educativo-Científico",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
            on_step=lambda step, status, detail=None: events.append((step, status, detail)),
        )

    assert events[:2] == [("generate_draft", "running", None), ("generate_draft", "done", None)]
    assert events[2][:2] == ("critique_draft", "running")
    assert events[3] == ("critique_draft", "error", "resposta inválida")


def test_on_step_reports_error_when_daily_cap_already_reached(conn, idea):
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    events = []
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.run_generation_pipeline(
            client=None, conn=conn, idea=idea, tone="Educativo-Científico",
            brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
            on_step=lambda step, status, detail=None: events.append((step, status)),
        )
    assert events[0] == ("generate_draft", "running")
    assert events[1][0] == "generate_draft"
    assert events[1][1] == "error"


def test_run_extraction_reports_progress(conn):
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    events = []
    pipeline.run_extraction(
        client=None, conn=conn, reference_text="texto qualquer",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
        on_step=lambda step, status, detail=None: events.append((step, status)),
    )
    assert events == [("extract_topics", "running"), ("extract_topics", "done")]


def test_on_step_defaults_to_none_and_does_not_break_existing_callers(conn, idea):
    """Existing tests (and any caller) that don't pass on_step must keep working."""
    fake_ai = make_fake_ai_module(critique_sequence=[[]])
    draft, flags, rounds = pipeline.run_generation_pipeline(
        client=None, conn=conn, idea=idea, tone="Educativo-Científico",
        brand_pack="marianabotelho-ig", daily_cap_usd=2.0, ai_module=fake_ai,
    )
    assert draft["caption"] == "v0"
