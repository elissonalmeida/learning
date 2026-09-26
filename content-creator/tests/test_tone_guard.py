import tone_guard
from sherlock import gather, models
import scoring


def _all_canned_strings():
    strings = list(models._UPLOAD_INSTRUCTIONS.values())
    for name in dir(gather):
        if name.isupper() and name.endswith("_REASON"):
            strings.append(getattr(gather, name))
    for goal in scoring.GOAL_MENU.values():
        strings.append(goal["label"])
        strings.append(goal["metric"])
    return strings


def test_find_harsh_words_flags_urgent_and_critical():
    assert tone_guard.find_harsh_words("Isto é CRÍTICO e urgente!") == ["crítico", "urgente"]


def test_find_harsh_words_is_empty_for_gentle_text():
    assert tone_guard.find_harsh_words("Quando te apetecer, aqui fica uma ideia leve.") == []


def test_find_harsh_words_ignores_partial_words():
    assert tone_guard.find_harsh_words("Uma ideia urgentemente bonita") == []


def test_gentle_tone_rule_mentions_pt_pt_and_gentle_wording():
    assert "PT-PT" in tone_guard.GENTLE_TONE_RULE
    assert "gentil" in tone_guard.GENTLE_TONE_RULE


def test_neutral_uses_of_alerta_and_grave_are_not_flagged():
    assert tone_guard.find_harsh_words("Fica atenta e alerta ao que o teu corpo pede, com uma voz grave e calma.") == []


def test_all_canned_user_facing_strings_are_gentle():
    strings = _all_canned_strings()
    assert len(strings) >= 10  # sanity check that the collection actually found the constants
    for text in strings:
        assert tone_guard.find_harsh_words(text) == [], f"harsh words in: {text!r}"
