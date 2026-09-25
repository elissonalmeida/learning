import json
import subprocess
import tempfile
import urllib.request
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, detect_platform, upload_instructions

MAX_CHARS = 20000
MIN_CHARS = 200
MAX_FETCH_CHARS = 2_000_000
WEBSITE_FAIL_REASON = "Não consegui abrir esta página neste momento."


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
        return response.read(MAX_FETCH_CHARS).decode(charset, errors="replace")


def gather_website(url, fetch=_http_fetch):
    if "://" not in url:
        url = "https://" + url.strip()
    try:
        html = fetch(url)[:MAX_FETCH_CHARS]
    except Exception:  # network errors, HTTP errors, timeouts: all mean "ask for an upload"
        return NeedsUpload(url, WEBSITE_FAIL_REASON, upload_instructions("website"))
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        return NeedsUpload(url, "A página quase não tem texto legível.", upload_instructions("website"))
    return GatherResult(url, "website", text)


def _video_text(info):
    lines = [
        f"Título: {info.get('title') or ''}",
        f"Autor: {info.get('uploader') or ''}",
        f"Descrição: {info.get('description') or ''}",
    ]
    for label, key in (("Visualizações", "view_count"), ("Gostos", "like_count"), ("Comentários", "comment_count")):
        if info.get(key) is not None:
            lines.append(f"{label}: {info[key]}")
    if info.get("tags"):
        lines.append("Etiquetas: " + ", ".join(info["tags"]))
    return "\n".join(lines)


def gather_video(url, run=subprocess.run, transcribe=None):
    kind = detect_platform(url)
    try:
        proc = run(["yt-dlp", "--dump-single-json", "--skip-download", url], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return NeedsUpload(url, "O yt-dlp não está instalado.", upload_instructions(kind))
    if proc.returncode != 0:
        reason = (proc.stderr or "").strip()[:200] or "O yt-dlp não conseguiu ler este vídeo."
        return NeedsUpload(url, reason, upload_instructions(kind))
    try:
        text = _video_text(json.loads(proc.stdout))
    except (TypeError, ValueError):
        return NeedsUpload(url, "O yt-dlp não conseguiu ler este vídeo.", upload_instructions(kind))
    method = "yt-dlp"
    try:
        transcript = transcribe(url) if transcribe else None
    except Exception:  # the transcript is a bonus: any failure means "no transcript"
        transcript = None
    if transcript:
        header = "\n\nTranscrição:\n"
        room = MAX_CHARS - len(text) - len(header)
        if room > 0:
            text += header + transcript[:room]
            method = "yt-dlp+whisper"
    return GatherResult(url, method, text[:MAX_CHARS])


def whisper_transcribe(url, run=subprocess.run):
    """Best-effort transcript via yt-dlp audio download + openai-whisper. Returns None if
    whisper or ffmpeg are unavailable or anything fails: the transcript is a bonus."""
    try:
        import whisper  # noqa: WPS433 (optional heavy dependency, imported lazily)
    except ImportError:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                ["yt-dlp", "-x", "--audio-format", "mp3", "-o", f"{tmp}/audio.%(ext)s", url],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                return None
            model = whisper.load_model("base")
            return model.transcribe(f"{tmp}/audio.mp3").get("text", "").strip() or None
    except Exception:
        return None
