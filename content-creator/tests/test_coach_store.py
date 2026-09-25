import pytest

import coach_store
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    coach_store.init_schema(connection)
    return connection


def test_create_strategy_increments_version_per_brand(conn):
    first = coach_store.create_strategy(conn, "brand-a", profile={"who": "terapeuta"})
    second = coach_store.create_strategy(conn, "brand-a")
    other = coach_store.create_strategy(conn, "brand-b")
    assert coach_store.get_strategy(conn, first)["version"] == 1
    assert coach_store.get_strategy(conn, second)["version"] == 2
    assert coach_store.get_strategy(conn, other)["version"] == 1
    assert coach_store.get_strategy(conn, first)["profile"] == {"who": "terapeuta"}


def test_set_section_upserts_and_roundtrips_json(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    coach_store.set_section(conn, sid, "pillars", {"items": [1, 2]})
    coach_store.set_section(conn, sid, "pillars", {"items": [3]}, state="accepted", evidence="data")
    sections = coach_store.get_sections(conn, sid)
    assert sections["pillars"] == {"content": {"items": [3]}, "state": "accepted", "evidence": "data"}


def test_set_section_rejects_unknown_kind_and_state(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    with pytest.raises(ValueError):
        coach_store.set_section(conn, sid, "nonsense", {})
    with pytest.raises(ValueError):
        coach_store.set_section(conn, sid, "goals", {}, state="weird")


def test_decisions_are_chronological_and_limitable(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    for i in range(5):
        coach_store.log_decision(conn, sid, "offers", "edit", f"motivo {i}")
    all_ = coach_store.list_decisions(conn, sid)
    assert [d["user_reason"] for d in all_] == [f"motivo {i}" for i in range(5)]
    last_two = coach_store.list_decisions(conn, sid, limit=2)
    assert [d["user_reason"] for d in last_two] == ["motivo 3", "motivo 4"]


def test_mark_accepted_sets_status_and_latest_strategy_filters(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    assert coach_store.latest_strategy(conn, "brand-a", status="accepted") is None
    coach_store.mark_accepted(conn, sid)
    latest = coach_store.latest_strategy(conn, "brand-a", status="accepted")
    assert latest["id"] == sid and latest["accepted_at"] is not None


def test_findings_roundtrip(conn):
    coach_store.save_finding(conn, "brand-a", "https://x.pt", "website", "resumo", [{"type": "hook", "description": "pergunta"}])
    findings = coach_store.list_findings(conn, "brand-a")
    assert findings[0]["brief_text"] == "resumo"
    assert findings[0]["patterns"] == [{"type": "hook", "description": "pergunta"}]
    assert coach_store.list_findings(conn, "brand-b") == []


def test_turns_roundtrip(conn):
    sid = coach_store.create_strategy(conn, "brand-a")
    coach_store.add_turn(conn, sid, "user", "olá")
    coach_store.add_turn(conn, sid, "coach", "olá!")
    assert [t["role"] for t in coach_store.list_turns(conn, sid)] == ["user", "coach"]
