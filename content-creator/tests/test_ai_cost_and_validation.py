import pytest
from ai import validate_reference_length, calculate_cost, ReferenceTooLongError, MAX_REFERENCE_WORDS

def test_reference_under_limit_passes():
    validate_reference_length("palavra " * 100)  # 100 words, well under limit

def test_reference_over_limit_raises():
    with pytest.raises(ReferenceTooLongError):
        validate_reference_length("palavra " * (MAX_REFERENCE_WORDS + 1))

def test_calculate_cost_is_proportional_to_tokens():
    cost_small = calculate_cost(tokens_in=1000, tokens_out=500)
    cost_large = calculate_cost(tokens_in=2000, tokens_out=1000)
    assert cost_large == pytest.approx(cost_small * 2)
    assert cost_small > 0
