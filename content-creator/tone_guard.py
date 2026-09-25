import re

GENTLE_TONE_RULE = (
    "Tom obrigatório: gentil, acolhedor e encorajador. Nunca uses urgência, alarme, culpa ou "
    "linguagem crítica (por exemplo 'crítico', 'urgente', 'falhaste'). Apresenta lacunas como "
    "convites simpáticos, por exemplo 'quando te apetecer, aqui fica uma ideia leve para "
    "retomares'. Escreve em Português Europeu (PT-PT)."
)

HARSH_WORDS = (
    "crítico", "crítica", "críticos", "críticas", "urgente", "urgentes", "urgência",
    "falhaste", "erro teu", "erro seu", "desleixo", "desleixado", "desleixada",
    "atrasado", "atrasada", "inaceitável",
)

_HARSH_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(w) for w in HARSH_WORDS) + r")(?!\w)", re.IGNORECASE
)


def find_harsh_words(text):
    return sorted({m.group(1).lower() for m in _HARSH_RE.finditer(text or "")})
