import base64
from pathlib import Path

from google import genai

MODEL = "gemini-3.1-flash-image"

# USD per token for Gemini 3.1 Flash Image (standard pricing, confirmed via a
# real test generation: $0.50 in / $60.00 out per million tokens).
PRICE_PER_INPUT_TOKEN = 0.50 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 60.00 / 1_000_000

BRANDS_DIR = Path(__file__).parent / "brands"


class NoImageReturned(Exception):
    """Raised when Gemini's response has no image, e.g. because the prompt was
    blocked. Carries the tokens/cost of the (already paid-for) call so the
    caller can still log the spend before surfacing the error."""

    def __init__(self, tokens_in, tokens_out, cost):
        super().__init__("Gemini não devolveu nenhuma imagem para este pedido.")
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost = cost


def load_brand_doc(brand_pack, filename):
    return (BRANDS_DIR / brand_pack / filename).read_text(encoding="utf-8")


def calculate_cost(tokens_in, tokens_out):
    return tokens_in * PRICE_PER_INPUT_TOKEN + tokens_out * PRICE_PER_OUTPUT_TOKEN


def get_client(api_key):
    return genai.Client(api_key=api_key)


def build_image_prompt(slide_text, brand_pack, slide_role):
    visual_style = load_brand_doc(brand_pack, "visual-style.md")
    if slide_role == "hero":
        framing = "Composição de cena completa, ambiente com espaço em redor do assunto principal."
    else:
        framing = (
            "Composição fechada num único assunto, com espaço vazio numa das "
            "margens para texto ser sobreposto depois."
        )
    return (
        "Gera uma imagem fotográfica, sem texto nenhum escrito na imagem, que "
        f"represente visualmente o seguinte conteúdo: {slide_text}\n\n"
        f"{framing}\n\n"
        "Segue este estilo visual da marca:\n" + visual_style
    )


def generate_image(client, prompt):
    interaction = client.interactions.create(model=MODEL, input=prompt)
    tokens_in = interaction.usage.total_input_tokens
    tokens_out = interaction.usage.total_output_tokens
    cost = calculate_cost(tokens_in, tokens_out)
    if interaction.output_image is None or interaction.output_image.data is None:
        raise NoImageReturned(tokens_in, tokens_out, cost)
    image_bytes = base64.b64decode(interaction.output_image.data)
    return image_bytes, tokens_in, tokens_out, cost
