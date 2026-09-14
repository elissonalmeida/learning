# Estilo Visual — @marianabotelho.pt

Fonte: guia de imagens oficial da marca (`guiaImagens.png`) e o carrossel
"Elixir" já publicado. Usado por `image_gen.py` (para construir os prompts
de imagem) e por `render.py` (para os templates HTML/CSS).

## Paleta de cores (hex)

- **Fundo (pergaminho):** `#efe4d0`
- **Moldura/estrutura:** `#83ae37`
- **Acento vermelho:** `#CA2D2D`
- **Acento dourado:** `#e6b55c`
- **Rosa claro:** `#ebb5a2`
- **Bege claro:** `#e7d1a8`

## Tipografia

- Títulos/destaque: **Cormorant Garamond** (serifada, elegante)
- Corpo de texto: **DM Sans** (sem serifa, legível em ecrã pequeno)

## Motivo botânico e moldura

Ilustrações botânicas em linha fina (plantas, ervas) e uma moldura oval
dourada/verde-escura com o texto "ELIXIR / MARIANA BOTELHO" — usada como
referência de composição, não para ser reproduzida literalmente em cada
imagem.

## Palavras-chave de ambiente/mood (para prompts de imagem)

natureza, botânico, artesanal, quente, acolhedor, luz natural suave, tons
terrosos, minimalista, orgânico, calmo — nunca clínico, nunca futurista,
nunca néon.

## Regra obrigatória para geração de imagem

**Nunca pedir texto na imagem.** O modelo de IA gera apenas o fundo/cena; o
texto (título, legenda) é sempre sobreposto depois via HTML/CSS em
`render.py`. Um prompt de imagem nunca deve incluir palavras que apareçam
escritas na imagem.
