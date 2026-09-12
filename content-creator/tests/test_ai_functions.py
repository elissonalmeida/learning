import json
from unittest.mock import MagicMock
import pytest
import ai


def make_fake_client(response_text, tokens_in=100, tokens_out=50):
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=response_text)]
    fake_response.usage.input_tokens = tokens_in
    fake_response.usage.output_tokens = tokens_out
    client = MagicMock()
    client.messages.create.return_value = fake_response
    return client


def test_render_prompt_substitutes_placeholders():
    template = "Olá {{NOME}}, o teu pilar é {{PILAR}}."
    result = ai.render_prompt(template, nome="Mariana", pilar="Educativo")
    assert result == "Olá Mariana, o teu pilar é Educativo."


def test_load_prompt_reads_file():
    text = ai.load_prompt("extract_topics")
    assert "{{DOMAIN_FRAMEWORK}}" in text


def test_load_brand_doc_reads_file():
    text = ai.load_brand_doc("marianabotelho-ig", "tone-of-voice.md")
    assert "Íntimo-Poético" in text


def test_extract_topics_parses_json_and_reports_usage():
    fake_json = json.dumps([{"topic": "5 plantas para o sono", "pillar": "Educativo Integrativo"}])
    client = make_fake_client(fake_json, tokens_in=500, tokens_out=100)
    topics, tokens_in, tokens_out, cost = ai.extract_topics(client, "um artigo de referência qualquer", "marianabotelho-ig")
    assert topics == [{"topic": "5 plantas para o sono", "pillar": "Educativo Integrativo"}]
    assert tokens_in == 500
    assert tokens_out == 100
    assert cost == pytest.approx(ai.calculate_cost(500, 100))


def test_extract_topics_rejects_reference_over_limit():
    client = make_fake_client("[]")
    with pytest.raises(ai.ReferenceTooLongError):
        ai.extract_topics(client, "palavra " * (ai.MAX_REFERENCE_WORDS + 1), "marianabotelho-ig")


def test_generate_draft_parses_json():
    fake_json = json.dumps({"caption": "legenda", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json)
    draft, tokens_in, tokens_out, cost = ai.generate_draft(
        client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
    )
    assert draft == {"caption": "legenda", "slides": ["s1", "s2"]}


def test_critique_draft_parses_json_array():
    fake_json = json.dumps([{"criterion": "Hashtags", "issue": "só 3 hashtags"}])
    client = make_fake_client(fake_json)
    draft = {"caption": "legenda", "slides": ["s1"]}
    flags, tokens_in, tokens_out, cost = ai.critique_draft(client, draft, "marianabotelho-ig")
    assert flags == [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]


def test_revise_draft_parses_json():
    fake_json = json.dumps({"caption": "legenda corrigida", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json)
    draft = {"caption": "legenda", "slides": ["s1"]}
    flags = [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]
    revised, tokens_in, tokens_out, cost = ai.revise_draft(client, draft, flags, "marianabotelho-ig")
    assert revised == {"caption": "legenda corrigida", "slides": ["s1", "s2"]}
