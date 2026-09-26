import email.message
import io
import urllib.error
import urllib.request

import pytest

from sherlock import gather, models


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """None of these tests should touch real DNS (finding 5): fake the default
    resolver to a fixed public address. Tests that need a specific resolution
    outcome pass their own `resolve=` explicitly, which overrides this."""
    monkeypatch.setattr(gather, "_resolve_all", lambda host: ["93.184.216.34"])


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


class _FakeOpener:
    def __init__(self, response):
        self._response = response

    def open(self, request, timeout=None):
        return self._response


def test_http_fetch_reads_a_bounded_number_of_bytes(monkeypatch):
    calls = {}

    class Resp:
        headers = type("H", (), {
            "get_content_charset": lambda self: None,
            "get_content_type": lambda self: "text/html",
        })()

        def read(self, n=-1):
            calls["n"] = n
            return b"ola"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gather.urllib.request, "build_opener", lambda handler: _FakeOpener(Resp()))
    assert gather._http_fetch("https://exemplo.pt", resolve=lambda host: ["93.184.216.34"]) == "ola"
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


def test_gather_website_keeps_original_input_as_source_but_fetches_normalized():
    result = gather.gather_website("  www.exemplo.pt  ", fetch=lambda url: _long_html())
    assert result.source == "www.exemplo.pt"


def test_gather_website_rejects_non_http_schemes():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run for a blocked scheme")

    for bad in ("file:///etc/passwd", "ftp://exemplo.pt/x"):
        result = gather.gather_website(bad, fetch=fetch_should_not_run)
        assert isinstance(result, models.NeedsUpload)
        assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_rejects_localhost_and_literal_private_ips():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run for a blocked host")

    for bad in ("http://localhost", "http://127.0.0.1", "http://192.168.1.1", "http://[::1]"):
        result = gather.gather_website(bad, fetch=fetch_should_not_run)
        assert isinstance(result, models.NeedsUpload)
        assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_rejects_domain_resolving_to_a_private_ip():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run for a host resolving to a private IP")

    result = gather.gather_website(
        "http://internal.exemplo.pt", fetch=fetch_should_not_run, resolve=lambda host: ["10.0.0.5"]
    )
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_rejects_ipv6_only_loopback():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run for a host resolving only to ::1")

    result = gather.gather_website(
        "http://ipv6.exemplo.pt", fetch=fetch_should_not_run, resolve=lambda host: ["::1"]
    )
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_rejects_when_any_resolved_address_is_private():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run when any resolved address is private")

    result = gather.gather_website(
        "http://dualstack.exemplo.pt", fetch=fetch_should_not_run,
        resolve=lambda host: ["93.184.216.34", "10.0.0.5"],
    )
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_blocks_when_resolution_fails():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run when the host can't be resolved")

    def boom(host):
        raise OSError("no address associated with hostname")

    result = gather.gather_website("http://naoexiste.exemplo.pt", fetch=fetch_should_not_run, resolve=boom)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_allows_a_public_host_resolving_normally():
    result = gather.gather_website(
        "https://exemplo.pt", fetch=lambda url: _long_html(), resolve=lambda host: ["93.184.216.34"]
    )
    assert isinstance(result, models.GatherResult)


def test_gather_website_returns_needs_upload_for_non_html_content_type():
    def fetch(url):
        raise gather._UnsupportedContentType("application/pdf")

    result = gather.gather_website("https://exemplo.pt/ficheiro.pdf", fetch=fetch)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BAD_CONTENT_TYPE_REASON


def test_http_fetch_rejects_non_text_content_type(monkeypatch):
    class Resp:
        headers = type("H", (), {
            "get_content_charset": lambda self: None,
            "get_content_type": lambda self: "application/pdf",
        })()

        def read(self, n=-1):
            return b"%PDF-1.4"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gather.urllib.request, "build_opener", lambda handler: _FakeOpener(Resp()))
    with pytest.raises(gather._UnsupportedContentType):
        gather._http_fetch("https://exemplo.pt/ficheiro.pdf", resolve=lambda host: ["93.184.216.34"])


def test_redirect_handler_refuses_a_redirect_to_a_blocked_host():
    handler = gather._SafeRedirectHandler(resolve=lambda host: ["93.184.216.34"])
    req = urllib.request.Request("https://exemplo.pt")
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/secret")


def test_redirect_handler_allows_a_redirect_to_a_public_host():
    handler = gather._SafeRedirectHandler(resolve=lambda host: ["93.184.216.34"])
    req = urllib.request.Request("https://exemplo.pt")
    new_req = handler.redirect_request(req, None, 302, "Found", {}, "https://outro.exemplo.pt/pagina")
    assert new_req.full_url == "https://outro.exemplo.pt/pagina"


def test_http_fetch_refuses_a_redirect_to_a_blocked_host_end_to_end(monkeypatch):
    class RedirectingOpener:
        def __init__(self, handler):
            self._handler = handler

        def open(self, request, timeout=None):
            # Mirrors what OpenerDirector does on a 3xx response: it hands the next
            # hop's URL to the installed redirect handler before following it.
            self._handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/secret")
            raise AssertionError("should never reach a real response")

    monkeypatch.setattr(gather.urllib.request, "build_opener", lambda handler: RedirectingOpener(handler))
    with pytest.raises(urllib.error.HTTPError):
        gather._http_fetch("https://exemplo.pt", resolve=lambda host: ["93.184.216.34"])


def test_redirect_handler_caps_the_number_of_hops():
    assert gather._SafeRedirectHandler.max_redirections == gather.MAX_REDIRECTS


def test_is_blocked_ip_blocks_carrier_grade_nat_and_allows_a_real_public_ip():
    import ipaddress

    # 100.64.0.0/10 (RFC 6598 shared/CGNAT address space) isn't loopback, private
    # (in the classic RFC1918 sense) or link-local, but it also isn't globally
    # routable -- the old is_private-based check let it through.
    assert gather._is_blocked_ip(ipaddress.ip_address("100.64.0.1")) is True
    assert gather._is_blocked_ip(ipaddress.ip_address("8.8.8.8")) is False


def test_gather_website_rejects_carrier_grade_nat_address():
    def fetch_should_not_run(url):
        raise AssertionError("fetch must not run for a CGNAT address")

    result = gather.gather_website(
        "http://cgnat.exemplo.pt", fetch=fetch_should_not_run, resolve=lambda host: ["100.64.0.1"]
    )
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.WEBSITE_BLOCKED_REASON


def test_gather_website_allows_a_real_public_ip():
    result = gather.gather_website(
        "https://exemplo.pt", fetch=lambda url: _long_html(), resolve=lambda host: ["8.8.8.8"]
    )
    assert isinstance(result, models.GatherResult)


class _FakeHTTPHandler(urllib.request.HTTPHandler):
    """Subclassing HTTPHandler (not plain BaseHandler) so build_opener recognises
    this as already providing http:// support and skips adding the real one --
    otherwise the real HTTPHandler would also be installed and could attempt an
    actual network connection."""

    def __init__(self):
        super().__init__()
        self.requests = []

    def http_open(self, req):
        self.requests.append(req.full_url)
        if req.full_url == "http://exemplo.pt/":
            headers = email.message.Message()
            headers["Location"] = "http://127.0.0.1/secret"
            resp = urllib.request.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            resp.msg = "Found"
            return resp
        headers = email.message.Message()
        headers["Content-Type"] = "text/plain"
        resp = urllib.request.addinfourl(io.BytesIO(b"segredo"), headers, req.full_url, 200)
        resp.msg = "OK"
        return resp


def test_real_opener_with_safe_redirect_handler_refuses_redirect_to_a_private_host():
    """End-to-end through real urllib.request.OpenerDirector machinery (no network):
    a fake http:// handler serves a 302 to a private host, and _SafeRedirectHandler
    must refuse to follow it -- the fake handler's second URL must never be requested."""
    fake_http = _FakeHTTPHandler()
    redirect_handler = gather._SafeRedirectHandler(resolve=lambda host: ["93.184.216.34"])
    opener = urllib.request.build_opener(fake_http, redirect_handler)

    with pytest.raises(urllib.error.HTTPError):
        opener.open(urllib.request.Request("http://exemplo.pt/"))

    assert fake_http.requests == ["http://exemplo.pt/"]
