import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class GatherResult:
    source: str
    method: str
    text: str


@dataclass
class NeedsUpload:
    source: str
    reason: str
    instructions: str


_UPLOAD_INSTRUCTIONS = {
    "instagram": (
        "Não consegui ler este perfil automaticamente, mas podemos avançar juntos. "
        "Se quiseres, envia-me uma destas opções: (1) um PDF do perfil (no telemóvel, "
        "imprime a página do perfil e guarda como PDF); (2) capturas de ecrã dos posts mais "
        "recentes; (3) as legendas coladas em texto. Se puderes, inclui também a descrição "
        "das fotos (o texto alternativo), porque costuma trazer informação útil."
    ),
    "tiktok": (
        "Não consegui ler este perfil automaticamente, sem problema. Podes enviar capturas de "
        "ecrã dos vídeos mais recentes ou colar as descrições e o texto que aparece nos vídeos."
    ),
    "youtube": (
        "Não consegui ler este vídeo automaticamente. Podes colar o título, a descrição e, se "
        "tiveres, a transcrição (no YouTube: três pontos por baixo do vídeo, 'Mostrar transcrição')."
    ),
    "website": (
        "Não consegui abrir esta página automaticamente. Podes colar o texto principal da página "
        "ou enviar capturas de ecrã ou um PDF (no navegador: imprimir, guardar como PDF)."
    ),
    "other": (
        "Não consegui ler esta fonte automaticamente. Podes colar o texto, enviar capturas de "
        "ecrã ou um PDF, e eu aproveito o que lá estiver."
    ),
}


def upload_instructions(kind):
    return _UPLOAD_INSTRUCTIONS.get(kind, _UPLOAD_INSTRUCTIONS["other"])


def _hostname(source):
    if re.search(r"\s", source):
        return None
    try:
        return urlparse(source if "://" in source else "//" + source).hostname
    except ValueError:
        return None


def _host_is(host, *domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def detect_platform(source):
    s = source.strip().lower()
    if s.startswith("@") and " " not in s:
        return "instagram"
    host = _hostname(s)
    if host:
        if _host_is(host, "instagram.com"):
            return "instagram"
        if _host_is(host, "tiktok.com"):
            return "tiktok"
        if _host_is(host, "youtube.com", "youtu.be"):
            return "youtube"
    if re.match(r"^(https?://|www\.)\S+$", s):
        return "website"
    return "text"


_IG_URL_RE = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.IGNORECASE)


def instagram_username(source):
    s = source.strip()
    if s.startswith("@"):
        return s[1:] or None
    m = _IG_URL_RE.search(s)
    if m and m.group(1).lower() not in {"p", "reel", "reels", "stories", "explore"}:
        return m.group(1)
    return None
