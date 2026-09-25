import json
import subprocess
import tempfile
import urllib.request
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, detect_platform, upload_instructions

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


def _video_text(info):
    lines = [
        f"Título: {info.get('title', '')}",
        f"Autor: {info.get('uploader', '')}",
        f"Descrição: {info.get('description', '')}",
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
        proc = run(["yt-dlp", "--dump-single-json", "--skip-download", url], capture_output=True, text=True)
    except FileNotFoundError:
        return NeedsUpload(url, "O yt-dlp não está instalado.", upload_instructions(kind))
    if proc.returncode != 0:
        reason = (proc.stderr or "").strip()[:200] or "O yt-dlp não conseguiu ler este vídeo."
        return NeedsUpload(url, reason, upload_instructions(kind))
    text = _video_text(json.loads(proc.stdout))
    method = "yt-dlp"
    transcript = transcribe(url) if transcribe else None
    if transcript:
        text += f"\n\nTranscrição:\n{transcript}"
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
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                return None
            model = whisper.load_model("base")
            return model.transcribe(f"{tmp}/audio.mp3").get("text", "").strip() or None
    except Exception:
        return None
