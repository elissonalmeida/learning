from sherlock import gather, models


def test_detect_platform():
    assert models.detect_platform("https://www.instagram.com/mariana/") == "instagram"
    assert models.detect_platform("@mariana") == "instagram"
    assert models.detect_platform("https://www.tiktok.com/@x") == "tiktok"
    assert models.detect_platform("https://youtu.be/abc") == "youtube"
    assert models.detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert models.detect_platform("https://exemplo.pt/blog") == "website"
    assert models.detect_platform("um texto colado com várias palavras") == "text"


def test_instagram_username_from_url_and_handle():
    assert models.instagram_username("https://www.instagram.com/mariana.botelho/") == "mariana.botelho"
    assert models.instagram_username("@mariana.botelho") == "mariana.botelho"
    assert models.instagram_username("https://exemplo.pt") is None


def test_upload_instructions_mention_alt_text_for_instagram_and_are_gentle():
    from tone_guard import find_harsh_words

    text = models.upload_instructions("instagram")
    assert "descrição" in text.lower() or "alt" in text.lower()
    assert find_harsh_words(text) == []
    assert models.upload_instructions("qualquer-coisa") == models.upload_instructions("other")


def test_gather_website_extracts_visible_text_and_image_alt():
    html = (
        "<html><head><style>x{}</style><script>bad()</script></head><body>"
        "<h1>Olá mundo</h1><p>" + ("Texto útil de exemplo. " * 20) + "</p>"
        "<img src='a.png' alt='Uma mulher a meditar'></body></html>"
    )
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: html)
    assert isinstance(result, models.GatherResult)
    assert result.method == "website"
    assert "Olá mundo" in result.text
    assert "Uma mulher a meditar" in result.text
    assert "bad()" not in result.text


def test_gather_website_returns_needs_upload_on_fetch_error():
    def boom(url):
        raise OSError("bloqueado")

    result = gather.gather_website("https://exemplo.pt", fetch=boom)
    assert isinstance(result, models.NeedsUpload)
    assert "bloqueado" not in result.reason
    assert result.reason == gather.WEBSITE_FAIL_REASON
    assert result.instructions


def test_gather_website_returns_needs_upload_when_page_has_almost_no_text():
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: "<html><body>oi</body></html>")
    assert isinstance(result, models.NeedsUpload)


def test_detect_platform_uses_hostname_not_substring():
    assert models.detect_platform("https://x.pt/?u=instagram.com") == "website"
    assert models.detect_platform("https://x.pt/tiktok.com/youtu.be") == "website"
    assert models.detect_platform("instagram.com/mariana") == "instagram"
    assert models.detect_platform("m.youtube.com/watch?v=abc") == "youtube"
    assert models.detect_platform("https://notinstagram.com/x") == "website"


def _long_html():
    return "<html><body><p>" + ("Texto útil de exemplo. " * 20) + "</p></body></html>"


def test_gather_website_prepends_https_when_scheme_missing():
    seen = []

    def fetch(url):
        seen.append(url)
        return _long_html()

    result = gather.gather_website("exemplo.pt/blog", fetch=fetch)
    assert seen == ["https://exemplo.pt/blog"]
    assert isinstance(result, models.GatherResult)


def test_gather_website_keeps_existing_scheme():
    seen = []
    gather.gather_website("http://exemplo.pt", fetch=lambda url: seen.append(url) or _long_html())
    assert seen == ["http://exemplo.pt"]


def test_gather_website_caps_fetched_body(monkeypatch):
    monkeypatch.setattr(gather, "MAX_FETCH", 300)
    html = "<p>" + ("a " * 200) + "</p><p>" + ("ZZZ " * 1000) + "</p>"
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: html)
    assert isinstance(result, models.GatherResult)
    assert "ZZZ" not in result.text


def test_http_fetch_reads_a_bounded_number_of_bytes(monkeypatch):
    calls = {}

    class Resp:
        headers = type("H", (), {"get_content_charset": lambda self: None})()

        def read(self, n=-1):
            calls["n"] = n
            return b"ola"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gather.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert gather._http_fetch("https://exemplo.pt") == "ola"
    assert calls["n"] == gather.MAX_FETCH


def test_gather_website_strips_whitespace_around_url():
    seen = []
    def fetch(url):
        seen.append(url)
        return "<p>" + "texto " * 100 + "</p>"
    gather.gather_website("  https://exemplo.pt/x  ", fetch=fetch)
    gather.gather_website("  www.exemplo.pt  ", fetch=fetch)
    assert seen == ["https://exemplo.pt/x", "https://www.exemplo.pt"]


def test_detect_platform_text_mentioning_instagram_is_plain_text():
    # Deliberate: only a URL or @handle counts as a source, not prose that mentions a site.
    assert models.detect_platform("vê instagram.com para exemplos") == "text"
