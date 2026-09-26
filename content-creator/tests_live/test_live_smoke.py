"""Real, paid API smoke test. NOT part of the normal suite (see pytest.ini).

Mocked tests can't reveal wrong assumptions about real API behavior (see
docs/decisions.md, 2026-09-13). Run this by hand or via the "Live smoke"
workflow: `pytest tests_live`. Costs a few cents per run.
"""
import os

import pytest

import ai

BRAND_PACK = "marianabotelho-ig"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
)


def test_real_generate_and_critique():
    client = ai.get_client(os.environ["ANTHROPIC_API_KEY"])
    tone = ai.suggest_default_tone(BRAND_PACK, None)
    draft, tokens_in, tokens_out, cost = ai.generate_draft(
        client, "óleo essencial de lavanda para o sono", tone, None, BRAND_PACK
    )
    assert draft["caption"].strip()
    assert draft["slides"]
    assert tokens_in > 0 and tokens_out > 0

    flags, _, _, _ = ai.critique_draft(client, draft, BRAND_PACK)
    assert isinstance(flags, list)
