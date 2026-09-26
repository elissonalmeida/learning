import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ai
import scoring


def fake_client(payload):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=300, output_tokens=120), stop_reason="end_turn",
    )
    return client


PROFILE = {"who": "terapeuta holística", "goals": ["build_authority", "get_conversations"], "offers": ["workshop"], "sources": []}
EVIDENCE = {"windsor": None, "findings": ["resumo de um perfil"]}


def test_goal_menu_has_six_plain_language_goals():
    assert set(scoring.GOAL_MENU) == {
        "grow_audience", "build_authority", "get_conversations",
        "followers_to_leads", "leads_to_clients", "keep_engaged",
    }
    assert all(v["label"] and v["metric"] for v in scoring.GOAL_MENU.values())


def test_score_goals_ranks_by_score_and_ignores_model_rank():
    payload = [
        {"goal": "get_conversations", "score": 55, "metric": "DMs/semana", "target": "5", "reasons": ["a"], "evidence": "reasoned", "rank": 1},
        {"goal": "build_authority", "score": 80, "metric": "guardados", "target": "+40%", "reasons": ["b"], "evidence": "pattern", "rank": 2},
    ]
    items, tin, tout, cost = scoring.score_goals(fake_client(payload), PROFILE, EVIDENCE)
    assert [i["goal"] for i in items] == ["build_authority", "get_conversations"]
    assert [i["rank"] for i in items] == [1, 2]
    assert tin == 300 and cost > 0


def test_score_goals_prompt_carries_tone_rule_and_evidence():
    payload = [
        {"goal": "build_authority", "score": 1, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"},
        {"goal": "get_conversations", "score": 2, "metric": "m2", "target": "t2", "reasons": ["r"], "evidence": "reasoned"},
    ]
    client = fake_client(payload)
    scoring.score_goals(client, PROFILE, EVIDENCE)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "gentil" in prompt and "resumo de um perfil" in prompt


@pytest.mark.parametrize("bad", [
    [{"goal": "inventado", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": 500, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "prova"}],
    [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": [], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": True, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": False, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}],
    [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}] * 2,
    {"not": "a list"},
])
def test_validate_rejects_malformed_items(bad):
    with pytest.raises(ai.InvalidAIResponseError):
        scoring.validate_scored_goals(bad, ["build_authority", "get_conversations"])


def test_data_evidence_is_downgraded_when_no_windsor_data():
    payload = [
        {"goal": "build_authority", "score": 70, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "data"},
        {"goal": "get_conversations", "score": 40, "metric": "m2", "target": "t2", "reasons": ["r"], "evidence": "reasoned"},
    ]
    items, *_ = scoring.score_goals(fake_client(payload), PROFILE, EVIDENCE)
    assert next(i for i in items if i["goal"] == "build_authority")["evidence"] == "reasoned"


def test_pattern_evidence_is_downgraded_when_no_findings():
    payload = [
        {"goal": "build_authority", "score": 70, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "pattern"},
        {"goal": "get_conversations", "score": 40, "metric": "m2", "target": "t2", "reasons": ["r"], "evidence": "reasoned"},
    ]
    items, *_ = scoring.score_goals(fake_client(payload), PROFILE, {"windsor": None, "findings": []})
    assert next(i for i in items if i["goal"] == "build_authority")["evidence"] == "reasoned"


def test_validate_rejects_a_missing_chosen_goal():
    items = [{"goal": "build_authority", "score": 5, "metric": "m", "target": "t", "reasons": ["r"], "evidence": "reasoned"}]
    with pytest.raises(ai.InvalidAIResponseError):
        scoring.validate_scored_goals(items, ["build_authority", "get_conversations"])
