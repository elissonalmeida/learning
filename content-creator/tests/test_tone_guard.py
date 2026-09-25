import tone_guard


def test_find_harsh_words_flags_urgent_and_critical():
    assert tone_guard.find_harsh_words("Isto é CRÍTICO e urgente!") == ["crítico", "urgente"]


def test_find_harsh_words_is_empty_for_gentle_text():
    assert tone_guard.find_harsh_words("Quando te apetecer, aqui fica uma ideia leve.") == []


def test_find_harsh_words_ignores_partial_words():
    assert tone_guard.find_harsh_words("Uma ideia urgentemente bonita") == []


def test_gentle_tone_rule_is_itself_gentle_and_mentions_pt_pt():
    assert "PT-PT" in tone_guard.GENTLE_TONE_RULE
    # The rule quotes the banned words as examples of what NOT to write, so it is exempt from the check.
    assert "gentil" in tone_guard.GENTLE_TONE_RULE
