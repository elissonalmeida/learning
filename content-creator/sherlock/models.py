import re
from dataclasses import dataclass


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


def detect_platform(source):
    s = source.strip().lower()
    if "instagram.com" in s or (s.startswith("@") and " " not in s):
        return "instagram"
    if "tiktok.com" in s:
        return "tiktok"
    if "youtube.com" in s or "youtu.be" in s:
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
