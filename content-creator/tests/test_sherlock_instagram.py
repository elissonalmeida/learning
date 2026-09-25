from sherlock import gather, models

DISCOVERY = {
    "business_discovery": {
        "username": "outra",
        "followers_count": 5400,
        "media_count": 120,
        "media": {"data": [
            {"caption": "Como dormir melhor", "like_count": 300, "comments_count": 12,
             "media_type": "CAROUSEL_ALBUM", "timestamp": "2026-08-01T10:00:00+0000"},
            {"caption": "Bastidores do dia", "like_count": 80, "comments_count": 2,
             "media_type": "IMAGE", "timestamp": "2026-08-03T10:00:00+0000"},
        ]},
    }
}


def test_discovery_builds_text_from_captions_and_metrics():
    seen = {}

    def get_json(url):
        seen["url"] = url
        return DISCOVERY

    result = gather.gather_instagram_discovery("@outra", "1789", "tok", get_json=get_json)
    assert isinstance(result, models.GatherResult)
    assert result.method == "instagram-business-discovery"
    assert "Como dormir melhor" in result.text and "5400" in result.text
    assert "outra" in seen["url"] and "access_token=tok" in seen["url"]


def test_discovery_needs_upload_without_credentials():
    result = gather.gather_instagram_discovery("@outra", None, None, get_json=lambda u: DISCOVERY)
    assert isinstance(result, models.NeedsUpload)


def test_discovery_needs_upload_when_username_cannot_be_parsed():
    result = gather.gather_instagram_discovery("https://exemplo.pt", "1", "t", get_json=lambda u: DISCOVERY)
    assert isinstance(result, models.NeedsUpload)


def test_discovery_needs_upload_on_api_error_with_fixed_reason():
    def boom(url):
        raise OSError("400 Bad Request tok-secret")

    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=boom)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.DISCOVERY_FAIL_REASON
    assert "400" not in result.reason


def test_discovery_needs_upload_on_bad_json_shape():
    for bad in (None, {}, {"business_discovery": None}, {"business_discovery": "x"}):
        result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u, b=bad: b)
        assert isinstance(result, models.NeedsUpload)


def test_discovery_null_fields_never_render_none():
    data = {"business_discovery": {"username": None, "followers_count": None, "media": {"data": [
        {"caption": None, "like_count": None, "comments_count": None, "media_type": None, "timestamp": None}]}}}
    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u: data)
    assert isinstance(result, models.GatherResult)
    assert "None" not in result.text and "@outra" in result.text


def test_discovery_url_escapes_credentials():
    seen = {}
    gather.gather_instagram_discovery("@outra", "1", "a&b=c", get_json=lambda u: seen.setdefault("u", u) and DISCOVERY)
    assert "access_token=a%26b%3Dc" in seen["u"]
