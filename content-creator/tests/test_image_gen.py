import base64
from unittest.mock import MagicMock
import pytest
import image_gen


def make_fake_client(image_bytes=b"\x89PNG-fake", tokens_in=50, tokens_out=1120):
    fake_interaction = MagicMock()
    fake_interaction.output_image.data = base64.b64encode(image_bytes).decode()
    fake_interaction.usage.total_input_tokens = tokens_in
    fake_interaction.usage.total_output_tokens = tokens_out
    client = MagicMock()
    client.interactions.create.return_value = fake_interaction
    return client


def test_build_image_prompt_includes_slide_text():
    prompt = image_gen.build_image_prompt("óleo de lavanda para o sono", "marianabotelho-ig", "hero")
    assert "óleo de lavanda para o sono" in prompt


def test_build_image_prompt_includes_brand_palette():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "#83ae37" in prompt


def test_build_image_prompt_never_asks_for_text_in_image():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "sem texto nenhum escrito na imagem" in prompt


def test_build_image_prompt_differs_by_slide_role():
    hero = image_gen.build_image_prompt("texto", "marianabotelho-ig", "hero")
    card = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert hero != card


def test_generate_image_returns_bytes_tokens_and_cost():
    client = make_fake_client(image_bytes=b"\x89PNG-fake", tokens_in=50, tokens_out=1120)
    image_bytes, tokens_in, tokens_out, cost = image_gen.generate_image(client, "um prompt qualquer")
    assert image_bytes == b"\x89PNG-fake"
    assert tokens_in == 50
    assert tokens_out == 1120
    assert cost == pytest.approx(image_gen.calculate_cost(50, 1120))


def test_generate_image_calls_the_configured_model(monkeypatch):
    client = make_fake_client()
    image_gen.generate_image(client, "um prompt")
    _, kwargs = client.interactions.create.call_args
    assert kwargs["model"] == image_gen.MODEL
    assert kwargs["input"] == "um prompt"


def test_calculate_cost_matches_gemini_pricing():
    # Gemini 3.1 Flash Image standard pricing: $0.50/1M input, $60.00/1M output.
    assert image_gen.calculate_cost(1_000_000, 0) == pytest.approx(0.50)
    assert image_gen.calculate_cost(0, 1_000_000) == pytest.approx(60.00)
