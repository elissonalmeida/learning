import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, detect_platform, instagram_username, upload_instructions

MAX_CHARS = 20000
MIN_CHARS = 200
MAX_FETCH = 2_000_000  # max bytes read from a socket/response; also max chars of website html kept
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
        return response.read(MAX_FETCH).decode(charset, errors="replace")


def gather_website(url, fetch=_http_fetch):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        html = fetch(url)[:MAX_FETCH]
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


GRAPH_VERSION = "v21.0"
_DISCOVERY_FIELDS = (
    "business_discovery.username({username})"
    "{{followers_count,media_count,media{{caption,like_count,comments_count,media_type,timestamp,permalink}}}}"
)
DISCOVERY_FAIL_REASON = "Não consegui ler este perfil pelo Instagram neste momento."
DISCOVERY_BAD_USERNAME_REASON = "Este nome de utilizador do Instagram não parece válido."
DISCOVERY_EMPTY_REASON = "Este perfil quase não tem publicações legíveis."
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _http_get_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read(MAX_FETCH).decode("utf-8"))


def gather_instagram_discovery(source, ig_user_id, access_token, get_json=_http_get_json):
    username = instagram_username(source)
    if not (username and ig_user_id and access_token):
        return NeedsUpload(
            source,
            "A ligação opcional ao Instagram (Business Discovery) não está configurada.",
            upload_instructions("instagram"),
        )
    if not _USERNAME_RE.match(username):
        return NeedsUpload(source, DISCOVERY_BAD_USERNAME_REASON, upload_instructions("instagram"))
    fields = _DISCOVERY_FIELDS.format(username=username)
    url = (
        f"https://graph.facebook.com/{GRAPH_VERSION}/{urllib.parse.quote(ig_user_id, safe='')}"
        f"?fields={urllib.parse.quote(fields, safe='(){},')}"
        f"&access_token={urllib.parse.quote(access_token, safe='')}"
    )
    try:
        data = get_json(url)["business_discovery"]
        media = (data.get("media") or {}).get("data") or []
        lines = [
            f"Perfil: @{data.get('username') or username}",
            f"Seguidores: {_num(data.get('followers_count'))}  Publicações: {_num(data.get('media_count'))}",
        ]
        for post in media:
            if isinstance(post, dict):
                lines.append(
                    f"- [{_str(post.get('media_type'))}] {_str(post.get('timestamp'))[:10]} "
                    f"gostos={_num(post.get('like_count'))} comentários={_num(post.get('comments_count'))}: "
                    f"{_str(post.get('caption'))}"
                )
    except Exception:  # API/network errors or unexpected shapes: ask for an upload instead
        return NeedsUpload(source, DISCOVERY_FAIL_REASON, upload_instructions("instagram"))
    text = "\n".join(lines)[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        return NeedsUpload(source, DISCOVERY_EMPTY_REASON, upload_instructions("instagram"))
    return GatherResult(source, "instagram-business-discovery", text)


def _num(value):
    return "?" if value is None else value


def _str(value):
    return value if isinstance(value, str) else ""
