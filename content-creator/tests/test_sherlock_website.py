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
    assert "bloqueado" in result.reason
    assert result.instructions


def test_gather_website_returns_needs_upload_when_page_has_almost_no_text():
    result = gather.gather_website("https://exemplo.pt", fetch=lambda url: "<html><body>oi</body></html>")
    assert isinstance(result, models.NeedsUpload)
