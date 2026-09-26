import ipaddress
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

from sherlock.models import GatherResult, NeedsUpload, detect_platform, instagram_username, upload_instructions

MAX_CHARS = 20000
MIN_CHARS = 200
MAX_FETCH = 2_000_000  # max bytes read from a socket/response; also max chars of website html kept
MAX_REDIRECTS = 5
# Run yt-dlp as a module of this interpreter: the "yt-dlp" script is only on PATH
# when the venv is activated.
YTDLP_CMD = [sys.executable, "-m", "yt_dlp"]
WEBSITE_FAIL_REASON = "Não consegui abrir esta página neste momento."
WEBSITE_BLOCKED_REASON = "Este link não pode ser aberto a partir daqui."
WEBSITE_BAD_CONTENT_TYPE_REASON = "Este link não leva a uma página de texto legível."
WEBSITE_THIN_REASON = "A página quase não tem texto legível."


class _UnsupportedContentType(Exception):
    """Raised by a fetch function when the response isn't HTML/text."""


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


def _resolve_all(host):
    """Default resolver: every address (IPv4 and IPv6) a real connection could land on."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _is_blocked_ip(ip):
    # Block everything that isn't globally routable (this already covers private,
    # loopback, link-local and a good deal more, e.g. carrier-grade NAT's
    # 100.64.0.0/10) plus multicast/unspecified/reserved explicitly, since
    # is_global's exact definition has shifted slightly across Python versions.
    # An IPv4-mapped IPv6 address (::ffff:10.0.0.1) is checked as its IPv4 form so
    # it can't be used to sneak a private IPv4 address past the guard.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not ip.is_global or ip.is_multicast or ip.is_unspecified or ip.is_reserved


def _is_blocked_host(hostname, resolve):
    # Residual accepted risk: this is a point-in-time check. Nothing stops the
    # DNS answer from changing between this check and the connection urlopen
    # makes moments later (DNS rebinding / TOCTOU). Out of scope for a
    # single-user local app; a real multi-user deployment would need to pin the
    # resolved address and connect to it directly.
    if not hostname:
        return True
    host = hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return _is_blocked_ip(ipaddress.ip_address(host))
    except ValueError:
        pass  # not a literal address: resolve it below
    try:
        addresses = resolve(host)
    except Exception:  # can't verify where this host points: fail closed
        return True
    if not addresses:
        return True
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True  # an address we can't even parse: fail closed
        if _is_blocked_ip(ip):
            return True
    return False


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-checks every redirect hop against the same host guard as the initial
    request, and caps the number of hops (the base class default is 10)."""

    max_redirections = MAX_REDIRECTS

    def __init__(self, resolve):
        self._resolve = resolve

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme not in ("http", "https") or _is_blocked_host(parsed.hostname, self._resolve):
            raise urllib.error.HTTPError(newurl, code, "Redirect to a blocked address refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_fetch(url, timeout=20, resolve=None):
    resolve = resolve or _resolve_all
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ContentCreator/1.0)",
        "Accept-Encoding": "identity",
    })
    opener = urllib.request.build_opener(_SafeRedirectHandler(resolve))
    with opener.open(request, timeout=timeout) as response:
        content_type = (response.headers.get_content_type() or "").lower()
        if content_type and not content_type.startswith("text/"):
            raise _UnsupportedContentType(content_type)
        charset = response.headers.get_content_charset() or "utf-8"
        return _decode_body(response.read(MAX_FETCH), response.headers.get("Content-Encoding"), charset)


def _decode_body(raw, content_encoding, charset):
    """Some servers compress even when asked not to; urllib never decompresses."""
    encoding = (content_encoding or "").strip().lower()
    if encoding in ("gzip", "x-gzip"):
        raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, MAX_FETCH)
    elif encoding == "deflate":
        raw = zlib.decompressobj().decompress(raw, MAX_FETCH)
    return raw[:MAX_FETCH].decode(charset, errors="replace")


def gather_website(url, fetch=_http_fetch, resolve=None):
    resolve = resolve or _resolve_all
    original = url.strip()
    normalized = original
    if "://" not in normalized:
        normalized = "https://" + normalized
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in ("http", "https") or _is_blocked_host(parsed.hostname, resolve):
        return NeedsUpload(original, WEBSITE_BLOCKED_REASON, upload_instructions("website"))
    try:
        html = fetch(normalized)[:MAX_FETCH]
    except _UnsupportedContentType:
        return NeedsUpload(original, WEBSITE_BAD_CONTENT_TYPE_REASON, upload_instructions("website"))
    except Exception:  # network errors, HTTP errors, timeouts: all mean "ask for an upload"
        return NeedsUpload(original, WEBSITE_FAIL_REASON, upload_instructions("website"))
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        return NeedsUpload(original, WEBSITE_THIN_REASON, upload_instructions("website"))
    return GatherResult(original, "website", text)


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


VIDEO_BAD_SOURCE_REASON = "Cola o link completo do vídeo, tal como aparece no navegador."
VIDEO_FAIL_REASON = "Não consegui ler este vídeo neste momento."
VIDEO_TIMEOUT_REASON = "Este vídeo está a demorar demasiado tempo a carregar; tenta novamente daqui a pouco."
METADATA_TIMEOUT = 120
AUDIO_TIMEOUT = 600


def gather_video(url, run=subprocess.run, transcribe=None):
    original = url.strip()
    normalized = original
    if "://" not in normalized:
        normalized = "https://" + normalized
    kind = detect_platform(normalized)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return NeedsUpload(original, VIDEO_BAD_SOURCE_REASON, upload_instructions(kind))
    try:
        proc = run(
            [*YTDLP_CMD, "--dump-single-json", "--skip-download", "--no-playlist", "--playlist-items", "1",
             "--", normalized],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=METADATA_TIMEOUT,
        )
    except FileNotFoundError:
        return NeedsUpload(original, VIDEO_FAIL_REASON, upload_instructions(kind))
    except subprocess.TimeoutExpired:
        return NeedsUpload(original, VIDEO_TIMEOUT_REASON, upload_instructions(kind))
    if proc.returncode != 0:
        return NeedsUpload(original, VIDEO_FAIL_REASON, upload_instructions(kind))
    try:
        info = json.loads(proc.stdout)
    except (TypeError, ValueError):
        return NeedsUpload(original, VIDEO_FAIL_REASON, upload_instructions(kind))
    if not isinstance(info, dict):
        return NeedsUpload(original, VIDEO_FAIL_REASON, upload_instructions(kind))
    text = _video_text(info)
    method = "yt-dlp"
    try:
        transcript = transcribe(normalized) if transcribe else None
    except Exception:  # the transcript is a bonus: any failure means "no transcript"
        transcript = None
    if transcript:
        header = "\n\nTranscrição:\n"
        room = MAX_CHARS - len(text) - len(header)
        if room > 0:
            text += header + transcript[:room]
            method = "yt-dlp+whisper"
    return GatherResult(original, method, text[:MAX_CHARS])


TRANSCRIBE_TIMEOUT = 600

# Only one transcription worker at a time: if a previous call's worker thread is
# still running (e.g. it outlived TRANSCRIBE_TIMEOUT and is still stuck), a new
# call bails out immediately instead of piling up another CPU-heavy transcription
# on top of it.
_transcribe_state = {"worker": None}
_transcribe_lock = threading.Lock()


def whisper_transcribe(url, run=subprocess.run):
    """Best-effort transcript via yt-dlp audio download + openai-whisper. Returns None if
    whisper or ffmpeg are unavailable or anything fails: the transcript is a bonus.
    Note: the first call loads the "base" Whisper model, which downloads about 140 MB
    from the network; TRANSCRIBE_TIMEOUT bounds that download plus the transcription
    itself, since both run in the worker thread below."""
    with _transcribe_lock:
        previous = _transcribe_state["worker"]
        if previous is not None and previous.is_alive():
            return None
    try:
        import whisper  # noqa: WPS433 (optional heavy dependency, imported lazily)
    except ImportError:
        return None
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            proc = run(
                [*YTDLP_CMD, "-x", "--audio-format", "mp3", "--no-playlist", "--playlist-items", "1",
                 "-o", f"{tmp}/audio.%(ext)s", "--", url],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=AUDIO_TIMEOUT,
            )
            if proc.returncode != 0:
                return None

            outcome = {}

            def _run_model():
                # Runs on a worker thread: any exception here must not reach
                # threading.excepthook (which would print a traceback) -- a failed
                # transcription is just "no transcript", handled the same as every
                # other failure mode in this function.
                try:
                    model = whisper.load_model("base")
                    outcome["text"] = model.transcribe(f"{tmp}/audio.mp3").get("text", "").strip() or None
                except Exception:
                    outcome["text"] = None

            worker = threading.Thread(target=_run_model, daemon=True)
            with _transcribe_lock:
                _transcribe_state["worker"] = worker
            worker.start()
            worker.join(TRANSCRIBE_TIMEOUT)
            if worker.is_alive():  # still running: give up, don't wait for it any longer
                return None
            return outcome.get("text")
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
DISCOVERY_NOT_CONFIGURED_REASON = "A ligação automática ao Instagram ainda não está configurada."
DISCOVERY_NOT_A_PROFILE_REASON = (
    "Este link parece ser de uma publicação, não de um perfil. Podes enviar o link do perfil?"
)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _http_get_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read(MAX_FETCH).decode("utf-8"))


def gather_instagram_discovery(source, ig_user_id, access_token, get_json=_http_get_json):
    username = instagram_username(source)
    if not username:
        return NeedsUpload(source, DISCOVERY_NOT_A_PROFILE_REASON, upload_instructions("instagram"))
    if not (ig_user_id and access_token):
        return NeedsUpload(source, DISCOVERY_NOT_CONFIGURED_REASON, upload_instructions("instagram"))
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
