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


def test_generate_image_raises_no_image_returned_when_gemini_gives_no_image():
    fake_interaction = MagicMock()
    fake_interaction.output_image = None
    fake_interaction.usage.total_input_tokens = 50
    fake_interaction.usage.total_output_tokens = 10
    client = MagicMock()
    client.interactions.create.return_value = fake_interaction

    with pytest.raises(image_gen.NoImageReturned) as excinfo:
        image_gen.generate_image(client, "um prompt qualquer")

    assert excinfo.value.tokens_in == 50
    assert excinfo.value.tokens_out == 10
    assert excinfo.value.cost == pytest.approx(image_gen.calculate_cost(50, 10))


def test_calculate_cost_matches_gemini_pricing():
    # Gemini 3.1 Flash Image standard pricing: $0.50/1M input, $60.00/1M output.
    assert image_gen.calculate_cost(1_000_000, 0) == pytest.approx(0.50)
    assert image_gen.calculate_cost(0, 1_000_000) == pytest.approx(60.00)


def test_card_prompt_asks_for_one_centred_subject_for_the_oval_medallion():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "centrado" in prompt
    assert "oval" in prompt
    assert "margens" not in prompt  # no empty margin reserved for text any more


def test_image_prompt_never_carries_words_that_could_be_painted():
    for role in ("hero", "card"):
        prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", role).lower()
        assert "@marianabotelho" not in prompt
        assert "mariana botelho" not in prompt
        assert "elixir" not in prompt
        assert "handle" not in prompt
        assert "cormorant" not in prompt and "lora" not in prompt  # typography stays out


def test_image_prompt_keeps_palette_mood_and_botanical_motif():
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "#efe4d0" in prompt
    assert "acolhedor" in prompt  # mood keywords
    assert "botânic" in prompt  # botanical motif, as mood


def test_card_prompt_asks_for_no_drawn_frame_or_border():
    # The renderer already frames the image in a gold oval; a frame painted by the
    # model shows up as a double frame.
    prompt = image_gen.build_image_prompt("texto", "marianabotelho-ig", "card")
    assert "sem moldura" in prompt
