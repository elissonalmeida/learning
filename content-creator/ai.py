import json
import re
from pathlib import Path

import anthropic

MAX_REFERENCE_WORDS = 6000
MAX_REVISION_ROUNDS = 2

# USD per token for Claude Sonnet 5 ($2.00 in / $10.00 out per million tokens).
# Update if Anthropic's published pricing changes.
PRICE_PER_INPUT_TOKEN = 2.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 10.00 / 1_000_000

MODEL = "claude-sonnet-5"
MAX_TOKENS = 8000

PROMPTS_DIR = Path(__file__).parent / "prompts"
BRANDS_DIR = Path(__file__).parent / "brands"


class ReferenceTooLongError(Exception):
    pass


class ResponseTruncatedError(Exception):
    pass


class InvalidAIResponseError(Exception):
    pass


def _parse_json_response(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        snippet = text[:200] if text else ""
        raise InvalidAIResponseError(
            "A resposta da API não era JSON válido. "
            f"Erro: {e}. Início da resposta: {snippet!r}"
        ) from e


def validate_reference_length(reference_text):
    word_count = len(reference_text.split())
    if word_count > MAX_REFERENCE_WORDS:
        raise ReferenceTooLongError(
            f"Reference text has {word_count} words, over the {MAX_REFERENCE_WORDS}-word limit. "
            "Trim it or split it into smaller parts."
        )


def calculate_cost(tokens_in, tokens_out):
    return tokens_in * PRICE_PER_INPUT_TOKEN + tokens_out * PRICE_PER_OUTPUT_TOKEN


def get_client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def load_prompt(name):
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_brand_doc(brand_pack, filename):
    return (BRANDS_DIR / brand_pack / filename).read_text(encoding="utf-8")


TONE_HEADING_RE = re.compile(r"^## Tom \d+ — (.+)$", re.MULTILINE)
WHEN_TO_USE_RE = re.compile(r"^\*\*Quando usar:\*\*(.*)$", re.MULTILINE)


def _tone_blocks(brand_pack):
    """Yield (tone_name, block_text) pairs from the brand pack's tone-of-voice.md."""
    doc = load_brand_doc(brand_pack, "tone-of-voice.md")
    matches = list(TONE_HEADING_RE.finditer(doc))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        yield match.group(1).strip(), doc[match.end():end]


def load_tone_names(brand_pack):
    return [name for name, _ in _tone_blocks(brand_pack)]


def suggest_default_tone(brand_pack, pillar):
    """Return the first tone whose 'Quando usar' line mentions the given pillar."""
    if not pillar:
        return None
    needle = pillar.strip().lower()
    if not needle:
        return None
    for name, block in _tone_blocks(brand_pack):
        for when in WHEN_TO_USE_RE.findall(block):
            if needle in when.lower():
                return name
    return None


def render_prompt(template, **kwargs):
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace("{{" + key.upper() + "}}", value)
    return rendered


def _call_claude(client, prompt_text, max_tokens=MAX_TOKENS):
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt_text}],
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ResponseTruncatedError(
            f"A resposta foi cortada ao atingir o limite de {max_tokens} tokens de saída. "
            "Reduz o tamanho do pedido ou aumenta MAX_TOKENS em ai.py."
        )
    text = response.content[0].text
    return text, response.usage.input_tokens, response.usage.output_tokens


def extract_topics(client, reference_text, brand_pack):
    validate_reference_length(reference_text)
    prompt = render_prompt(
        load_prompt("extract_topics"),
        domain_framework=load_brand_doc(brand_pack, "domain-framework.md"),
    )
    prompt = f"{prompt}\n\n## Texto de Referência\n{reference_text}"
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    topics = _parse_json_response(text)
    return topics, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def generate_draft(client, topic, tone, pillar, brand_pack):
    prompt = render_prompt(
        load_prompt("generate_draft"),
        domain_framework=load_brand_doc(brand_pack, "domain-framework.md"),
        tone_of_voice=load_brand_doc(brand_pack, "tone-of-voice.md"),
    )
    prompt = f"{prompt}\n\n## Tópico\n{topic}\n\n## Pilar\n{pillar}\n\n## Tom Escolhido\n{tone}"
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    draft = _parse_json_response(text)
    return draft, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def critique_draft(client, draft, brand_pack):
    prompt = render_prompt(
        load_prompt("critique_draft"),
        draft_json=json.dumps(draft, ensure_ascii=False),
        quality_criteria=load_brand_doc(brand_pack, "quality-criteria.md"),
        anti_patterns=load_brand_doc(brand_pack, "anti-patterns.md"),
    )
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    flags = _parse_json_response(text)
    return flags, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)


def revise_draft(client, draft, flags, brand_pack):
    prompt = render_prompt(
        load_prompt("revise_draft"),
        draft_json=json.dumps(draft, ensure_ascii=False),
        quality_flags=json.dumps(flags, ensure_ascii=False),
    )
    text, tokens_in, tokens_out = _call_claude(client, prompt)
    revised = _parse_json_response(text)
    return revised, tokens_in, tokens_out, calculate_cost(tokens_in, tokens_out)
