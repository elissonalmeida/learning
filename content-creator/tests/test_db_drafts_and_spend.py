import pytest
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


@pytest.fixture
def idea_id(conn):
    return db.create_idea(conn, "marianabotelho-ig", "manual", "5 plantas adaptogénicas")


def test_create_and_list_drafts_round_trips_json(conn, idea_id):
    db.create_draft(
        conn, idea_id, round_=0,
        caption="Legenda de teste",
        slides=["slide 1", "slide 2"],
        quality_flags=[{"criterion": "Hashtags", "issue": "só 3 hashtags"}],
    )
    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert len(drafts) == 1
    assert drafts[0]["slides"] == ["slide 1", "slide 2"]
    assert drafts[0]["quality_flags"] == [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]
    assert drafts[0]["round"] == 0


def test_drafts_ordered_by_round(conn, idea_id):
    db.create_draft(conn, idea_id, round_=1, caption="v2", slides=["a"])
    db.create_draft(conn, idea_id, round_=0, caption="v1", slides=["a"])
    drafts = db.list_drafts_for_idea(conn, idea_id)
    assert [d["round"] for d in drafts] == [0, 1]


def test_log_api_call_and_get_spend_today(conn, idea_id):
    db.log_api_call(conn, "generate_draft", tokens_in=1000, tokens_out=500, estimated_cost_usd=0.05, idea_id=idea_id)
    db.log_api_call(conn, "critique_draft", tokens_in=800, tokens_out=200, estimated_cost_usd=0.03, idea_id=idea_id)
    assert db.get_spend_today(conn) == pytest.approx(0.08)


def test_would_exceed_daily_cap(conn, idea_id):
    db.log_api_call(conn, "generate_draft", tokens_in=1000, tokens_out=500, estimated_cost_usd=1.90, idea_id=idea_id)
    assert db.would_exceed_daily_cap(conn, estimated_call_cost=0.20, daily_cap_usd=2.0) is True
    assert db.would_exceed_daily_cap(conn, estimated_call_cost=0.05, daily_cap_usd=2.0) is False
