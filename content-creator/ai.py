MAX_REFERENCE_WORDS = 6000
MAX_REVISION_ROUNDS = 2

# USD per token. Update if Anthropic's published pricing changes.
PRICE_PER_INPUT_TOKEN = 3.00 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 15.00 / 1_000_000


class ReferenceTooLongError(Exception):
    pass


def validate_reference_length(reference_text):
    word_count = len(reference_text.split())
    if word_count > MAX_REFERENCE_WORDS:
        raise ReferenceTooLongError(
            f"Reference text has {word_count} words, over the {MAX_REFERENCE_WORDS}-word limit. "
            "Trim it or split it into smaller parts."
        )


def calculate_cost(tokens_in, tokens_out):
    return tokens_in * PRICE_PER_INPUT_TOKEN + tokens_out * PRICE_PER_OUTPUT_TOKEN
