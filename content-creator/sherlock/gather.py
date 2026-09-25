import urllib.request
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, upload_instructions

MAX_CHARS = 20000
MIN_CHARS = 200


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f"[imagem: {alt}]")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def _http_fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ContentCreator/1.0)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def gather_website(url, fetch=_http_fetch):
    try:
        html = fetch(url)
    except Exception as e:  # network errors, HTTP errors, timeouts: all mean "ask for an upload"
        return NeedsUpload(url, str(e), upload_instructions("website"))
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        return NeedsUpload(url, "A página quase não tem texto legível.", upload_instructions("website"))
    return GatherResult(url, "website", text)
