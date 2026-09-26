from sherlock import gather, models

FILLER = "texto de enchimento " * 8

DISCOVERY = {
    "business_discovery": {
        "username": "outra",
        "followers_count": 5400,
        "media_count": 120,
        "media": {"data": [
            {"caption": "Como dormir melhor " + FILLER, "like_count": 300, "comments_count": 12,
             "media_type": "CAROUSEL_ALBUM", "timestamp": "2026-08-01T10:00:00+0000"},
            {"caption": "Bastidores do dia " + FILLER, "like_count": 80, "comments_count": 2,
             "media_type": "IMAGE", "timestamp": "2026-08-03T10:00:00+0000"},
        ]},
    }
}


def _recording_get_json(seen):
    def get_json(url):
        seen["u"] = url
        return DISCOVERY

    return get_json


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
    assert result.reason == gather.DISCOVERY_NOT_CONFIGURED_REASON
    assert "Business Discovery" not in result.reason


def test_discovery_needs_upload_when_username_cannot_be_parsed():
    result = gather.gather_instagram_discovery("https://exemplo.pt", "1", "t", get_json=lambda u: DISCOVERY)
    assert isinstance(result, models.NeedsUpload)


def test_discovery_post_link_gets_a_profile_link_reason_without_jargon():
    calls = []
    result = gather.gather_instagram_discovery(
        "https://www.instagram.com/p/abc123/", "1", "t", get_json=lambda u: calls.append(u)
    )
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.DISCOVERY_NOT_A_PROFILE_REASON
    assert "Business Discovery" not in result.reason
    assert "perfil" in result.reason.lower()
    assert not calls


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
        {"caption": None, "like_count": None, "comments_count": None, "media_type": None, "timestamp": None},
        {"caption": FILLER}]}}}
    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u: data)
    assert isinstance(result, models.GatherResult)
    assert "None" not in result.text and "@outra" in result.text


def test_discovery_url_escapes_credentials():
    seen = {}
    gather.gather_instagram_discovery("@outra", "1", "a&b=c", get_json=_recording_get_json(seen))
    assert "access_token=a%26b%3Dc" in seen["u"]


def test_discovery_rejects_invalid_username_without_calling_api():
    calls = []
    result = gather.gather_instagram_discovery("@x){evil}", "1", "t", get_json=lambda u: calls.append(u))
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.DISCOVERY_BAD_USERNAME_REASON
    assert not calls


def test_discovery_skips_malformed_posts():
    data = {"business_discovery": {"username": "outra", "media": {"data": [
        "lixo", None, {"caption": 5, "timestamp": 20260801, "media_type": []},
        {"caption": "Boa " + FILLER, "timestamp": "2026-08-01T10:00:00+0000"}]}}}
    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u: data)
    assert isinstance(result, models.GatherResult)
    assert "Boa" in result.text and "lixo" not in result.text


def test_discovery_needs_upload_when_no_usable_media():
    data = {"business_discovery": {"username": "outra", "followers_count": 10, "media": {"data": []}}}
    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u: data)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.DISCOVERY_EMPTY_REASON


def test_discovery_truncates_to_max_chars():
    data = {"business_discovery": {"username": "outra", "media": {"data": [{"caption": "a" * (gather.MAX_CHARS * 2)}]}}}
    result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=lambda u: data)
    assert len(result.text) == gather.MAX_CHARS


def test_discovery_needs_upload_when_get_json_raises_key_or_value_error():
    for exc in (KeyError("x"), ValueError("y")):
        def boom(url, exc=exc):
            raise exc

        result = gather.gather_instagram_discovery("@outra", "1", "t", get_json=boom)
        assert isinstance(result, models.NeedsUpload)


def test_http_get_json_caps_read_at_max_fetch(monkeypatch):
    sizes = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            sizes.append(n)
            return b'{"a": 1}'

    monkeypatch.setattr(gather.urllib.request, "urlopen", lambda url, timeout: FakeResponse())
    assert gather._http_get_json("https://x") == {"a": 1}
    assert sizes == [gather.MAX_FETCH]
