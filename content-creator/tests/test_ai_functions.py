import json
from unittest.mock import MagicMock
import pytest
import ai


def make_fake_client(response_text, tokens_in=100, tokens_out=50, stop_reason="end_turn", with_thinking_block=False):
    fake_response = MagicMock()
    text_block = MagicMock(type="text", text=response_text)
    if with_thinking_block:
        thinking_block = MagicMock(type="thinking")
        del thinking_block.text  # a real ThinkingBlock has no .text attribute
        fake_response.content = [thinking_block, text_block]
    else:
        fake_response.content = [text_block]
    fake_response.usage.input_tokens = tokens_in
    fake_response.usage.output_tokens = tokens_out
    fake_response.stop_reason = stop_reason
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


def test_truncated_response_raises_response_truncated_error():
    client = make_fake_client('{"caption": "legenda cort', stop_reason="max_tokens")
    with pytest.raises(ai.ResponseTruncatedError):
        ai.generate_draft(
            client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
        )


def test_non_json_response_raises_invalid_ai_response_error():
    client = make_fake_client("Claro! Aqui está o teu carrossel: ...")
    with pytest.raises(ai.InvalidAIResponseError) as excinfo:
        ai.generate_draft(
            client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
        )
    assert "Claro! Aqui está o teu carrossel" in str(excinfo.value)


def test_call_claude_skips_a_leading_thinking_block():
    """Claude Sonnet 5 can return an extended-thinking block as content[0] with no
    .text attribute; _call_claude must find the actual text block, not assume index 0."""
    fake_json = json.dumps({"caption": "legenda", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json, with_thinking_block=True)
    draft, tokens_in, tokens_out, cost = ai.generate_draft(
        client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
    )
    assert draft == {"caption": "legenda", "slides": ["s1", "s2"]}


def test_call_claude_raises_invalid_ai_response_error_when_no_text_block_present():
    client = make_fake_client("irrelevant")
    client.messages.create.return_value.content = [MagicMock(type="thinking")]
    del client.messages.create.return_value.content[0].text
    with pytest.raises(ai.InvalidAIResponseError):
        ai.generate_draft(
            client, "ashwagandha", "Educativo-Científico", "Educativo Integrativo", "marianabotelho-ig"
        )


def test_load_tone_names_reads_the_brand_pack():
    names = ai.load_tone_names("marianabotelho-ig")
    assert len(names) == 6
    assert "Educativo-Científico" in names
    assert "Íntimo-Poético" in names
    assert names[0] == "Íntimo-Poético"


def test_suggest_default_tone_matches_pillar():
    assert ai.suggest_default_tone("marianabotelho-ig", "Educativo Integrativo") == "Educativo-Científico"
    assert ai.suggest_default_tone("marianabotelho-ig", "Bastidores") == "Íntimo-Poético"


def test_suggest_default_tone_returns_none_when_unknown_or_missing():
    assert ai.suggest_default_tone("marianabotelho-ig", "Pilar Inexistente") is None
    assert ai.suggest_default_tone("marianabotelho-ig", None) is None


def test_revise_draft_parses_json():
    fake_json = json.dumps({"caption": "legenda corrigida", "slides": ["s1", "s2"]})
    client = make_fake_client(fake_json)
    draft = {"caption": "legenda", "slides": ["s1"]}
    flags = [{"criterion": "Hashtags", "issue": "só 3 hashtags"}]
    revised, tokens_in, tokens_out, cost = ai.revise_draft(client, draft, flags, "marianabotelho-ig")
    assert revised == {"caption": "legenda corrigida", "slides": ["s1", "s2"]}
