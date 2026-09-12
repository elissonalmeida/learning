# Content Creator — Design Spec

## Background

An earlier attempt at automating Instagram content for `@marianabotelho.pt` exists as a 10-agent OpenSquad squad (`marianabotelho-content-ig`, at `C:\Users\Elisson\Documents\Aura\opensquad\squads\marianabotelho-content-ig`). It never reached production quality — text and images were both weak, and no working carousel was ever produced. However, its brand/voice/research documents are genuinely solid and are reused as-is by this project. They are reproduced in full in the Appendix below so this spec is self-contained — no need to go back to the OpenSquad folder to understand what they say.

## Purpose of this project

A **learning project**: build a small, understandable, real piece of software (not a black-box framework) that produces genuinely good Instagram carousel text (caption + slides), reusing the brand knowledge in the Appendix. Secondary goal: produce a written spec detailed enough to redo this later in TypeScript as a second, separate learning exercise.

## Reusability model: engine vs. brand pack

The app itself (`app.py`, `ai.py`, `db.py`) is written to be **brand-agnostic** — it doesn't know anything about pharmacists, plants, or Instagram tone specifically. Everything specific to one niche/voice/audience — the tones, the content pillars, the quality checklist, the anti-patterns, the worked examples, the audience research — lives in a **brand pack**: a self-contained folder of markdown docs.

This is what makes the "same code, different field" idea from your question realistic: to reuse this tool for a different domain (e.g. content for an IT/databases audience), you would write a **new brand pack** folder (its own tone-of-voice.md, domain-framework.md, quality-criteria.md, anti-patterns.md, output-examples.md, research-brief.md, in whatever language and style fits that audience) and point the app at it — no changes to `app.py`/`ai.py`/`db.py` required. The engine loads whichever brand pack is configured; it never hard-codes Mariana-specific content.

```
content-creator/
  brands/
    marianabotelho-ig/         <- first brand pack, built in v1 (Appendix below)
      tone-of-voice.md
      domain-framework.md
      quality-criteria.md
      anti-patterns.md
      output-examples.md
      research-brief.md
```

v1 only ever has one brand pack configured at a time (via `.env`: `BRAND_PACK=marianabotelho-ig`), and the database tags every idea with which brand pack produced it (`ideas.brand_pack`), so a future brand pack could be added later without losing or confusing existing data — even though v1 itself only builds and uses the one.

## Language rule

All generated content — extracted topics, drafts, captions — **must be European Portuguese (PT-PT)**, regardless of the language of any reference material given as input. A reference article in English is a perfectly valid source to extract topics from, but every topic, caption, and slide the AI produces is written in PT-PT. This is not left implicit: every prompt in `ai.py` (extraction, generation, critique, revision) explicitly states this requirement, and `critique_draft` treats PT-PT/PT-BR compliance as one of its checks (per quality-criteria.md, Critério 2, in the Appendix).

## Scope — v1

**In scope:**
- Text only: Instagram carousel slide copy + caption. No image/graphic generation.
- Input either a topic typed directly, or a pasted reference text (article, notes — any language) from which the AI proposes multiple candidate topic angles, always output in PT-PT.
- AI-assisted quality loop (generate → critique → revise, capped) before human review.
- A local database tracking every idea and draft, with a library view to browse, filter, and archive/delete.
- Runs as a local Python/Streamlit app on the user's or his wife's computer, using a shared Anthropic API key.
- Deliberate, cost-conscious use of the paid API — prompt iteration happens for free in Claude Code first.

**Out of scope for v1** (candidate v2+ features):
- Image/carousel graphic rendering.
- Auto-publishing to Instagram.
- Automated topic/monthly content planning (the old squad's "tema do dia" / "planeamento mensal" steps).
- Performance analytics (saves, reach, etc.).
- Multi-user support / per-user API keys / concurrent multi-computer use.
- A second brand pack for a different niche (the architecture supports it; building one is a separate future exercise).
- A TypeScript rewrite (deliberately deferred — this spec is written to make that possible later).

## User flow

1. **Input.** User pastes a reference text (max 6,000 words — hard cap, rejected above that with a message to trim/split) or types a topic directly.
2. **Topic extraction** (only if reference text given). AI proposes up to 5 distinct, non-overlapping topic angles genuinely well-supported by the material, always phrased in PT-PT regardless of the reference's language. Quality over quantity: the prompt explicitly instructs the model not to pad the list to hit a target count — 2 excellent angles beats 5 mediocre ones.
3. **Selection.** User multi-selects one or more proposed topics (or confirms a directly-typed topic). Each selected topic becomes its own `idea` row in the database, status `idea`. This supports building a short series from one reference (e.g. 3 posts across a week from the same source).
4. **Tone selection.** For the idea being drafted now, user picks one of the 6 established tones; the app suggests a default based on the idea's pillar.
5. **Draft generation.** AI writes the carousel slides and caption per domain-framework.md's structure rules, using the chosen tone's voice from tone-of-voice.md.
6. **Quality loop.** A critique pass checks the draft against quality-criteria.md and anti-patterns.md and lists failed criteria. If any failed and fewer than 2 revision rounds have run, a revise pass fixes only the listed issues, then critiques again. After round 2, the draft goes to human review regardless of remaining flags — the flags are shown, not hidden.
7. **Human review.** User (or wife) reads the final draft and any remaining quality flags, and approves, edits, or rejects.
8. **Save.** Every round's draft is retained (not just the final one), with the idea's status updated (`drafted` → `reviewed` → `approved`/`rejected`).

## Architecture

Project lives in its own subfolder of this repo, `content-creator/`, kept separate from the repo root so this "learning" repo can hold multiple independent projects over time:

```
content-creator/
  app.py            Streamlit UI — the flow above, wired together
  ai.py             Claude API calls: extract_topics, generate_draft, critique_draft, revise_draft
                     (brand-agnostic — takes a brand pack's docs as input, contains no Mariana-specific text)
  db.py             SQLite schema + CRUD (ideas, drafts, api_calls)
  config.py         reads .env: ANTHROPIC_API_KEY, DB_PATH, MAX_DAILY_SPEND_USD, BRAND_PACK
  brands/
    marianabotelho-ig/   the brand pack built in v1 — see Appendix for full contents
  tests/            pytest, AI calls mocked — see Testing section
  run.bat           double-clickable launcher (activates venv, runs `streamlit run app.py`)
  .env.example
  requirements.txt
```

Database file path (configurable, defaults to a Dropbox-synced folder for automatic backup):
`C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db`

## Data model

```sql
CREATE TABLE ideas (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    brand_pack TEXT NOT NULL,        -- e.g. 'marianabotelho-ig'; which brand pack produced this idea
    source_type TEXT NOT NULL,       -- 'manual' | 'reference'
    reference_text TEXT,             -- null if source_type = 'manual'
    topic TEXT NOT NULL,
    pillar TEXT,                     -- one of the 4 pillars, or null until set
    tone TEXT,                       -- one of the 6 tones
    status TEXT NOT NULL DEFAULT 'idea',  -- idea|drafted|reviewed|approved|rejected|archived
    archived_at TEXT                 -- soft-delete marker; null = active
);

CREATE TABLE drafts (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    round INTEGER NOT NULL,          -- 0 = initial draft, 1/2 = revisions
    caption TEXT NOT NULL,
    slides TEXT NOT NULL,            -- JSON array of slide texts, ordered
    quality_flags TEXT,              -- JSON array of failed criteria this round, if any
    created_at TEXT NOT NULL
);

CREATE TABLE api_calls (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER REFERENCES ideas(id),   -- null for extraction calls not yet tied to an idea
    function TEXT NOT NULL,          -- 'extract_topics' | 'generate_draft' | 'critique_draft' | 'revise_draft'
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL
);
```

Slides are stored as a JSON array in a single column rather than a normalized table — a deliberate v1 simplification since nothing in v1 queries individual slides; this can be migrated to a normalized `slides` table later without losing data if per-slide querying becomes useful.

Deletion is soft by default (`archived_at` set, row hidden from the main Library view but recoverable) with a separate, explicit action to hard-delete already-archived rows.

## AI pipeline

Four Claude API calls, each a distinct function in `ai.py`, each taking the active brand pack's docs as input rather than having any brand-specific text hard-coded:

- `extract_topics(reference_text, brand_pack) -> list[{topic, pillar_guess}]` — instructed to propose up to 5 angles, quality over quantity, never padding the list, output always in PT-PT for this brand pack.
- `generate_draft(topic, tone, pillar, brand_pack) -> {caption, slides}` — prompt includes the relevant tone description/examples from the brand pack's tone-of-voice.md and the structural rules from its domain-framework.md.
- `critique_draft(draft, brand_pack) -> list[failed_criteria]` — checks against the brand pack's quality-criteria.md and anti-patterns.md.
- `revise_draft(draft, failed_criteria, brand_pack) -> {caption, slides}` — fixes only the listed issues.

Loop control lives in `app.py`, not `ai.py`: generate → critique → (if failures and round < 2: revise → critique again) → stop after round 2 regardless, always surfacing remaining flags to the human.

Before any of this is wired into the app, prompts for each function are prototyped and iterated directly in Claude Code (using the existing Pro subscription, no API cost) against the real marianabotelho-ig brand pack and real example topics, until output quality looks right. Only once prompts are solid do they move into `ai.py` for real API-key testing.

## Cost safeguards

- **Account-level (outside the app):** a monthly spend limit and email alert set on console.anthropic.com — enforced by Anthropic regardless of any bug in this code.
- **Reference text hard cap:** 6,000 words; rejected above that, not truncated silently.
- **Revision loop hard cap:** 2 rounds, always.
- **No unbounded retries:** each API call gets at most 1 retry on failure, never silent infinite retry.
- **Daily spend cap in-app:** `MAX_DAILY_SPEND_USD` in `.env` (start at $2). Before each call, `db.py` sums today's `api_calls.estimated_cost_usd`; if the call would exceed the cap, it's blocked with a clear message instead of executing.
- **Visibility:** the Library view shows running spend totals (today / this month) computed from `api_calls`.

## Distribution

Single shared Anthropic API key (the user's), stored in `.env`, not per-user. The user sets up Python and copies the project folder onto his wife's computer; `run.bat` activates the environment and runs `streamlit run app.py`, opening a browser tab — no terminal or command-line interaction required from her. Single-user-at-a-time usage is assumed; the Dropbox-synced database file is not designed for concurrent simultaneous access from two machines.

## Testing strategy

Two distinct kinds of verification, kept deliberately separate to avoid ever confusing a fake response for a real one:

1. **Automated tests** (`tests/`, run via pytest, following test-driven development): verify code logic only — does the revision loop stop at round 2, does the daily spend cap actually block a call, does archiving hide a row from the active list, does the cost calculation add up. All AI calls are mocked with canned fake responses. These tests never present their fake output as content to a human; they only assert on code behavior.
2. **Manual quality evaluation**: judging whether generated captions/slides are actually well-written can only be done by reading real output. This happens first via prompt prototyping directly in Claude Code (free, subscription-based, before any app code depends on it), and later via small, deliberate end-to-end runs of the real app against the real API once prompts are considered solid.

## Open questions / deferred to v2+

- Image/carousel graphic generation (the old squad's biggest unsolved problem).
- Auto-publishing to Instagram.
- Topic/monthly planning automation.
- Post-performance analytics feeding back into topic selection.
- Normalizing `drafts.slides` into its own table if per-slide querying becomes valuable.
- A second brand pack, proving out the reuse model for a different niche/audience.
- A TypeScript rewrite, using this spec as the blueprint.

---

## Appendix: Brand Pack — `marianabotelho-ig`

Reproduced in full from the OpenSquad squad `marianabotelho-content-ig`, at
`C:\Users\Elisson\Documents\Aura\opensquad\squads\marianabotelho-content-ig\pipeline\data\`,
so this spec is self-contained. These six files are copied verbatim into `content-creator/brands/marianabotelho-ig/`.

### research-brief.md

> Audience profile, performance data, and competitor patterns. Read this first — it's the "why" behind every rule in the other five files.

```markdown
# Research Brief — @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Versão:** 2.0
**Data:** 2026-06-15

Este brief compila todos os dados de investigação relevantes para a produção de conteúdo para @marianabotelho.pt. Deve ser lido pelos agentes Íris e Catarina antes de iniciar trabalho.

---

## 1. Perfil do Público (Dados Windsor.ai)

### Dados Demográficos
- **Seguidores totais:** 1.208
- **Género:** 88% feminino
- **Grupo etário núcleo:** 45-54 anos (38% dos seguidores)
- **Grupo etário alargado:** 35-65 anos (audiência relevante)
- **Países:** Portugal 79% · Brasil 14% · Outros 7%

### Estado Actual de Performance
- **Saves:** 0 nos últimos 30 dias — métrica crítica a activar
- **Engagement rate:** 22% quando há post (muito alto para o tamanho da conta)
- **Melhor dia de publicação:** Domingo
- **Melhor hora:** 10h
- **Frequência actual:** 6-7 dias activos por mês (muito irregular)
- **Objectivo do squad:** 3-4 posts por semana com saves como KPI principal

### Perfil Psicográfico da Audiência Core (mulheres 45-54, PT)
- Em transição de vida — hormonal (perimenopausa/menopausa), profissional ou relacional
- Procuram equilíbrio emocional e reconexão com o próprio corpo
- Familiarizadas com saúde integrativa mas com formação académica variável
- Tomam decisões de saúde com base em confiança + evidência — não em tendências
- Valorizam autenticidade e continuidade narrativa — não perfeição visual
- Comentários actuais do perfil: calorosos, pessoais, de gratidão — audiência relacional

---

## 2. Auditoria do Perfil Próprio (@marianabotelho.pt)

### O Que Está a Funcionar
- **Reels com storytelling** têm o maior alcance: Post 1 (HAM/HET): 271 likes, 3.124 views
- **Narrativa pessoal + credencial + produto concreto** = fórmula do melhor post (Post 2 — Elixir)
- **Colaborações** geram comentários acima da média: Post 4 (manteiga): 48 comentários
- **Eventos presenciais com localização real** ressoam com audiência local portuguesa
- **Engagement rate de 22%** é excepcional — a audiência existe e está engajada

### O Que Não Está a Funcionar
- **0 saves** — nenhum post tem estrutura de referência salvável
- **Inconsistência de voz** — oscila entre poético-espiritual e comercial-institucional
- **Hashtags com erros:** "reike" em vez de "reiki" (6 ocorrências no Post 3)
- **Mistura PT-PT / PT-BR** no mesmo post (Post 3: "estresse", "sua vida")
- **Pilares subrepresentados:** cosmética natural (17%), educativo integrativo (17%), bastidores (8%)
- **Credencial farmacêutica raramente aparece** — o maior diferenciador é o menos explorado

### Post Modelo a Replicar: Post 2 (Elixir)
Estrutura: abertura íntima/narrativa → história pessoal (alambique, transição PT-BR) → credencial académica (Farmácia + Fitoterapia) → produto concreto → CTA suave. É o único post que cumpre todas as regras de voz.

---

## 3. Padrões dos Perfis de Referência

### @hanuna.csi (Dra. Mariana Britto, BH — farmacêutica + terapeuta de bem-estar)
**Lições principais:**
- Conteúdo educativo com passos práticos = 3x mais engagement que inspiracional (179 likes vs. 71)
- Hook mais eficaz: sensação corporal específica ("ficar mais ofegante e sentir o coração disparar")
- Assinar com a mesma frase em todos os posts cria reconhecimento de marca
- 5 hashtags focadas funcionam melhor que lista longa genérica
- 100% Reels — sem carrosséis (diferente da estratégia da Mariana que combina formatos)

**Aplicação para @marianabotelho.pt:** Reels com técnica em passos numerados. Hook corporal/sensorial. Assinatura fixa (já tem: "O corpo sabe o caminho de volta a si.").

### @anasofiacorreia.pt (Astróloga + mentora sistémica, PT)
**Lições principais:**
- Âncora temporal ("Hoje, dia 9 de Junho, às 19h58") cria urgência e relevância imediata
- Linguagem de permissão ("te permites receber", "deixas entrar") ressoa com a audiência 35-65 PT
- Estrutura de legenda validada: Hook → Contexto → Ponte Emocional → Insight → Reframe → CTA → Assinatura
- Profundidade emocional e psicológica > informação astrológica isolada
- Sign-off consistente ("Com Amor, Ana Sofia") cria calor e identidade
- Carrosséis: primeiro slide = hook bold + "Desliza para o lado" como convite

**Aplicação para @marianabotelho.pt:** Adoptar a estrutura de legenda de 7 elementos. Usar linguagem de permissão. Âncoras temporais (lua cheia, estação, mudança hormonal).

### @eva_mendonca_oliveira (referência não investigada — dados limitados)
**Notas da discovery:** Perfil de referência para conteúdo de bem-estar feminino em PT. Investigação completa não disponível neste build — incorporar em futuras actualizações do squad.

---

## 4. Estratégia de Conteúdo — Síntese para Produção

### A Equação de Saves
**Save = Estrutura de Referência + Mecanismo Explicado + CTA para Guardar**

- Carrossel de lista numerada (5 plantas / 4 técnicas / 3 mecanismos) → activa save
- Tutorial passo-a-passo (ritual completo, preparação do Elixir, técnica de respiração) → activa save
- Infográfico de referência (como escolher óleo essencial / diferença HAM vs. HET vs. Reiki) → activa save
- Frase inspiracional isolada → não activa save

### Os Formatos Certos por Objectivo

| Objectivo | Formato | Pilar | Modelo de Referência |
|-----------|---------|-------|----------------------|
| Saves | Carrossel de referência (lista/tutorial) | Educativo Integrativo | @marianabotelho.pt Post 2 + @anasofiacorreia.pt |
| Alcance | Reel com hook corporal + técnica em passos | Terapias / Educativo | @hanuna.csi Reel 1 |
| Comentários | Post com pergunta directa ao público | Bastidores / Terapias | @anasofiacorreia.pt Content 2 |
| Partilhas | Post com âncora de momento ("Se tens 40+...") | Educativo / Terapias | @anasofiacorreia.pt Content 1 |

### Gap de Pilar vs. Frequência Sugerida

| Pilar | Frequência Actual | Frequência Sugerida |
|-------|-----------------|---------------------|
| Terapias Energéticas | 60%+ | 30-40% |
| Educativo Integrativo | <15% | 30% |
| Cosmética Natural | <15% | 20% |
| Bastidores / Vida | <10% | 15-20% |

---

## 5. Regras de Conteúdo — Resumo Executivo

1. **Língua:** PT-PT exclusivo. "stress" não "estresse". Tuteia sempre. Nunca "você".
2. **Assinatura:** "O corpo sabe o caminho de volta a si." — última frase de todos os posts.
3. **Âncora farmacêutico:** Nos primeiros 2 parágrafos de todos os posts educativos.
4. **Save-first:** Todo carrossel tem slide final com "Guarda este post".
5. **Hook:** 125 caracteres, sensação corporal ou contraintuitivo — não apresentação.
6. **CTA:** Específico e accionável — nunca "curtam e comentem".
7. **Holístico rigoroso:** Nenhuma afirmação de mecanismo sem validação da Taís Terapias.
8. **Legal:** Sem "cura", "trata", "elimina doenças" — linguagem de apoio/complemento.
9. **Hashtags:** 5-8, com #marianabotelho, sem "reike".
10. **Visual:** Fotografia autêntica — nunca stock photo.
```

### tone-of-voice.md

> The 6 tones the AI can choose from when generating a draft.

```markdown
# Tons de Voz — @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Língua:** PT-PT exclusivo

---

Cada post começa com a escolha de um tom. Estes 6 tons representam os registos possíveis para @marianabotelho.pt. São distintos na energia, na cadência e no tipo de conteúdo que servem melhor.

---

## Tom 1 — Íntimo-Poético

**Descrição:** O tom mais próximo da voz natural da Mariana. Fala como uma carta escrita à mão — próxima, sensorial, cheia de imagens. Não é abstracto: é poético com chão. Usa metáforas do corpo, da natureza e do tempo. A farmacêutica está implícita, não declarada. Serve bem posts de bastidores, rituais e reflexões pessoais.

**Quando usar:** pilares Bastidores e Terapias Energéticas; posts de Domingo; quando o ângulo é narrativa pessoal.

**Hook exemplo:**
> "Havia uma planta que crescia na janela da farmácia da minha avó. Eu não sabia ainda que ia dedicar a vida a perceber o que ela sabia sobre mim."

**Copy exemplo:**
> "Há coisas que o corpo sabe antes de a mente as nomear. A lavanda que colhi esta manhã ainda está entre os meus dedos. E há qualquer coisa na forma como ela abre — devagar, sem pressa — que me lembra que é assim que toda a cura acontece. O corpo sabe o caminho de volta a si."

---

## Tom 2 — Educativo-Científico

**Descrição:** Rigoroso, claro, acessível. A farmacêutica está em primeiro plano. Usa terminologia científica correcta mas explica-a para não-especialistas. Não é frio — tem calor humano — mas não sacrifica precisão por poesia. Ideal para posts que explicam mecanismos de plantas, terapias ou substâncias. O tom que activa saves.

**Quando usar:** pilar Educativo Integrativo; carrosséis de referência; qualquer post com mecanismo de acção explicado.

**Hook exemplo:**
> "Como farmacêutica, o que me fascina no ashwagandha não é o nome sânscrito — é o que ele faz ao eixo HPA quando o corpo está em stress crónico."

**Copy exemplo:**
> "A Withania somnifera — ashwagandha — age sobre o eixo hipotálamo-hipófise-adrenal. Em português simples: ajuda o corpo a calibrar a resposta ao stress. Não elimina o stress. Ajuda o teu sistema nervoso a não ficar preso nele. É a diferença entre apagar o fogo e ensinar a casa a não arder. O corpo sabe o caminho de volta a si."

---

## Tom 3 — Provocador-Suave

**Descrição:** Começa com uma afirmação que desafia o que a audiência já pensa — mas sem agressividade. É uma provocação com acolhimento. O efeito é de surpresa seguida de reconhecimento: "nunca tinha pensado assim." Usa contrastes, inversões e paradoxos. Gera comentários e partilhas. Não usar em posts de produtos específicos.

**Quando usar:** Reels de alcance; posts educativos com um ângulo contraintuitivo; quando o objectivo é comentários.

**Hook exemplo:**
> "O que chamas de ansiedade pode ser o teu sistema nervoso a tentar salvar-te. O problema não é a ansiedade — é que ainda não aprendeste a ouvi-la."

**Copy exemplo:**
> "Passamos anos a querer eliminar o que sentimos. A ansiedade, o cansaço, o vazio. Como se fossem inimigos. E se fossem mensageiros? A aromaterapia não adormece o mensageiro — ajuda-te a abrir a porta e a ouvir o que ele tem para dizer. O corpo sabe o caminho de volta a si."

---

## Tom 4 — Narrativo-Pessoal

**Descrição:** Conta uma história real — da Mariana, de uma cliente (anónima), de um momento específico. Tem início, meio e fim. É o tom que mais humaniza a marca e que mais gera partilhas orgânicas. A credencial emerge naturalmente da narrativa, não é declarada. Requer detalhes concretos: lugar, hora, sensação.

**Quando usar:** posts de Bastidores; o "Post Modelo" (à semelhança do Post 2 — Elixir); colaborações; aniversários e marcos.

**Hook exemplo:**
> "Era quarta-feira à tarde e eu estava no alambique, a destilar lavanda, quando percebi que não conseguia parar de chorar. Não de tristeza. De alívio."

**Copy exemplo:**
> "Há três anos, quando saí do Brasil e vim para Portugal com duas malas e uma formação em Farmácia que não sabia ainda como usar, comprei o primeiro alambique de cobre com o dinheiro que me tinha sobrado. Cada lote de Elixir que produzo ainda carrega algo desse dia. O corpo sabe o caminho de volta a si."

---

## Tom 5 — Ritual-Contemplativo

**Descrição:** Lento, meditativo, como uma meditação guiada em texto. Usa a segunda pessoa do singular no modo imperativo suave: "Fecha os olhos." "Coloca a mão no peito." "Respira." Cria uma experiência no momento da leitura. Não é informativo — é vivencial. Gera saves porque as pessoas querem reler como um ritual. Ideal para Reels voice-over.

**Quando usar:** Reels de meditação ou técnica somática; posts de rituais passo-a-passo; conteúdo de inverno/solstício/lua.

**Hook exemplo:**
> "Antes de continuares a ler — coloca a mão no centro do peito. Sente o calor. Esse calor és tu."

**Copy exemplo:**
> "Fecha os olhos por um momento.
> Respira fundo — pelo nariz, devagar.
> Sente o peso do teu corpo na cadeira.
> Agora, imagina que cada expiração leva consigo o que já não é teu.
> Não tens de saber o que é. O corpo sabe.
> Abre os olhos quando estiveres pronta.
> O corpo sabe o caminho de volta a si."

---

## Tom 6 — Urgência-Gentil

**Descrição:** Cria um senso de importância e timing — mas sem pressão. Usa âncoras temporais ("neste momento", "nesta fase da vida", "neste ciclo") para criar relevância imediata. A urgência vem do reconhecimento, não da escassez. A audiência sente que este post chegou exactamente na altura certa. Ideal para posts publicados em momentos especiais (lua cheia, mudança de estação, início de mês).

**Quando usar:** posts publicados em datas específicas; conteúdo de início de ciclo (lunar, sazonal, de vida); quando o objectivo é partilha.

**Hook exemplo:**
> "Se tens mais de 40 anos e sentes que o teu corpo está a mudar de uma forma que não consegues explicar — este post é para ti. E é agora."

**Copy exemplo:**
> "A transição hormonal não é o fim de uma versão de ti. É o início de outra. Mas o sistema nervoso não sabe isso — precisa de ser informado. As plantas adaptogénicas — a maca, o ashwagandha, a rhodiola — foram estudadas precisamente para este momento da vida feminina. Não são suplementos. São aliados de transição. O corpo sabe o caminho de volta a si."
```

### domain-framework.md

> The 4 content pillars, and the exact structure a carousel, Reel, and caption must follow.

```markdown
# Framework Operacional — Conteúdo Instagram @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Versão:** 2.0
**Língua:** PT-PT exclusivo

---

## 1. A Filosofia do Save-First

Todo o conteúdo produzido por este squad é optimizado para **saves** — não para likes, não para comentários, não para alcance imediato.

**Porquê:** Os dados Windsor.ai confirmam 0 saves em 30 dias. O Instagram trata os saves como o sinal de maior intenção de um utilizador: significa que quer voltar ao conteúdo. O algoritmo premia posts com saves com distribuição prolongada. Para a audiência 45-54 de mulheres em transição de vida, o save é um gesto de cuidado consigo própria — "vou precisar disto mais tarde."

**O que activa saves:**
- Listas práticas com mecanismo explicado ("5 plantas para o sono — e o que cada uma faz no corpo")
- Tutoriais com passos concretos e numerados
- Conteúdo de referência que a pessoa vai querer reler antes de uma consulta ou ritual
- Rituais completos que podem ser executados em casa
- Carrosséis com slide final explícito: "Guarda este post para quando precisares"

**O que NÃO activa saves:**
- Frases inspiracionais sem substância prática
- Posts vagos sem mecanismo ou estrutura
- Anúncios de eventos
- Conteúdo duplicado do que já existe no feed

---

## 2. Os 4 Pilares de Conteúdo

### Pilar 1 — Terapias Energéticas
**O que cobre:** HAM (Harmonização de Alta Magia), HET (Harmonia Energética Terapêutica), Reiki (todos os graus), leitura de aura, florais de Bach, tratamentos energéticos.
**Tom:** Explicativo mas espiritual. Sempre com mecanismo (ex: o Reiki como activação do sistema nervoso parassimpático, não como magia).
**Frequência sugerida:** 1-2 posts por semana — é o pilar com melhor alcance actual (3.124 views no Post 1).
**Formatos ideais:** Reel (storytelling + resultados) + Carrossel (como funciona / o que esperar).
**Gap actual:** Forte, mas sem ancora científica.

### Pilar 2 — Cosmética Natural
**O que cobre:** Elixir de Mariana, óleos essenciais, manteigas, aromaterapia, formulação artesanal, receitas caseiras.
**Tom:** Narrativo-pessoal + educativo. O alambique de cobre é um elemento visual e narrativo único.
**Frequência sugerida:** Mínimo 1 post por mês — actualmente subrepresentado (apenas 2 de 12 posts visíveis).
**Formatos ideais:** Reel de bastidores (processo de destilação) + Carrossel (ingredientes + mecanismo).
**Gap actual:** Quase ausente — é o maior gap do perfil dado ser um produto diferenciador.

### Pilar 3 — Educativo Integrativo
**O que cobre:** Fitoterapia, aromaterapia, farmácia natural, farmacognosia, mecanismos de acção de plantas, interacções, contra-indicações, adaptogénicos, compostos activos.
**Tom:** Educativo-Científico (Tom 2). A credencial farmacêutica é o âncora obrigatório.
**Frequência sugerida:** 1 post por semana — actualmente muito fraco (apenas conteúdo espiritual sem base científica).
**Formatos ideais:** Carrossel de referência (formato lista/tutorial = activa saves) + Reel educativo com voz-off.
**Gap actual:** Crítico — é o pilar que mais activa saves e que mais diferencia a Mariana de outros perfis de terapias.

### Pilar 4 — Bastidores / Vida
**O que cobre:** Natureza, rituais pessoais, processo criativo, momentos autênticos, a Lola (cachorra), viagens, estações do ano, bastidores do atelier/alambique.
**Tom:** Íntimo-Poético (Tom 1) ou Narrativo-Pessoal (Tom 4).
**Frequência sugerida:** 1 post por semana — actualmente quase ausente (apenas 1 de 12 posts).
**Formatos ideais:** Reel curto (30-45s, imagens naturais, voz suave) + Story diária.
**Gap actual:** Crítico para a conexão humana — a audiência feminina 45-54 conecta com autenticidade.

---

## 3. Estrutura do Carrossel

Os carrosséis são o formato prioritário para activar saves. Cada carrossel segue esta estrutura:

### Slide 1 — HOOK VISUAL
- Máximo 8 palavras
- Impacto imediato — deve parar o scroll
- Pode ser uma pergunta, uma afirmação contraintuitiva, ou um número
- Tipografia grande, fundo simples, uma cor de destaque
- Exemplos: "A planta que regula o teu stress melhor do que o magnésio" / "5 coisas que o teu corpo diz quando está em sobrecarga" / "Reiki não é o que pensas"

### Slides 2-8 — CORPO DO CONTEÚDO
- Uma ideia por slide — nunca dois conceitos no mesmo slide
- Linguagem concisa: máximo 3-4 linhas de texto por slide
- Progressão lógica: cada slide deve dar vontade de deslizar para o seguinte
- Incluir mecanismo de acção quando relevante (Pilar 3 especialmente)
- Elementos visuais: fotografia real ou ícone simples — nunca stock photo genérica

### Slide Final — CTA + ASSINATURA
- CTA específico e accionável: "Guarda este carrossel para quando precisares de X"
- Nunca: "Curtam e comentem"
- Incluir: "O corpo sabe o caminho de volta a si."
- Opcional: hashtags no slide ou só na legenda

### Legenda do Carrossel
- Estrutura obrigatória: **Hook → Contexto → Ponte emocional → Insight → Reframe → CTA → Assinatura**
- 150-300 palavras
- Credencial farmacêutica nos primeiros 2 parágrafos (posts educativos)
- Hashtags: 5-8, sempre com #marianabotelho
- Última frase sempre: "O corpo sabe o caminho de volta a si."

---

## 4. Estrutura do Reel

Os Reels são o formato prioritário para alcance. Cada Reel segue esta estrutura:

### Abertura — HOOK (3 segundos)
- Frase ou questão que prende — baseada numa sensação corporal ou experiência reconhecível
- Exemplos validados: "Já acordaste com aquela sensação de peso no peito que não consegues explicar?" / "O teu sistema nervoso não sabe que a reunião já acabou."
- Nunca começar com "Olá sou a Mariana" ou uma apresentação — o hook vem primeiro
- Formato @marianabotelho.pt: voice-over com imagens de natureza, rituais, bastidores — sem falar directamente para a câmara

### Corpo — DESENVOLVIMENTO (30-60 segundos)
- Técnica, insight ou mecanismo em passos numerados quando aplicável
- Linguagem acessível mas rigorosa (Tom 2 ou combinação com Tom 1)
- Ritmo: pausas deliberadas — não é rápido como trend, é contemplativo
- Visual: luz natural, planos próximos, mãos a trabalhar, plantas, alambique

### Encerramento — REFRAME + CTA (últimos 5 segundos)
- Reframe poético que sintetiza o que foi dito
- CTA simples e específico: "Guarda este vídeo." / "Partilha com alguém que precisa ouvir isto." / "Experimenta esta semana e conta-me nos comentários."
- Nunca: "Não te esqueças de subscrever" — linguagem de YouTuber não serve esta marca
- Sempre terminar com: "O corpo sabe o caminho de volta a si." (dito ou em texto)

### Legenda do Reel
- Mais curta que o carrossel: 50-100 palavras
- O vídeo faz o trabalho — a legenda expande, não repete
- Hook da legenda diferente do hook do vídeo
- CTA alinhado com o objectivo do Reel (save, comentário, partilha)
- Hashtags: 5-8, incluindo #marianabotelho

---

## 5. Estrutura da Legenda (Modelo @anasofiacorreia.pt Adaptado)

Para todos os posts de feed, a legenda segue esta sequência de 7 elementos:

1. **Hook** — Primeira frase antes do "ver mais". Deve funcionar sozinha. Específico, não vago. Máximo 125 caracteres.
2. **Contexto** — Uma ou duas frases que ancoram o leitor no tema. Pode incluir a credencial farmacêutica aqui.
3. **Ponte Emocional** — Conecta o tema com a experiência vivida da audiência. "Muitas de nós chegamos a este ponto sem saber que..."
4. **Insight** — O coração do post. O mecanismo, a distinção, o "eu nunca tinha pensado assim". 2-4 frases.
5. **Reframe** — Uma frase que muda a perspectiva. Pode ser poética. "Não é fraqueza — é o corpo a pedir atenção."
6. **CTA** — Específico e accionável. "Guarda este post." / "Comenta com o que sentes mais." / "Partilha com uma amiga que está nesta fase."
7. **Assinatura** — SEMPRE última frase: "O corpo sabe o caminho de volta a si."

---

## 6. A Regra do Âncora Farmacêutico

**Regra:** Em TODOS os posts do Pilar Educativo Integrativo, e em QUALQUER post que mencione plantas, substâncias ou mecanismos de acção, a credencial farmacêutica da Mariana deve aparecer nos primeiros 2 parágrafos da legenda.

**Fórmulas aprovadas:**
- "Como farmacêutica, o que me fascina nesta planta é..."
- "A ciência chama-lhe [nome técnico]. Eu chamo-lhe [nome intuitivo]."
- "Estudei Farmácia porque queria perceber o que a natureza fazia por dentro. E a [planta/substância] é uma das minhas respostas favoritas."
- "Durante anos na farmácia, as pessoas perguntavam-me sobre [tema]. A resposta honesta é..."

**Porquê:** A audiência 45-54 que toma decisões de saúde valoriza credibilidade científica. Sem o âncora farmacêutico, o perfil é indistinguível de outros perfis de terapias holísticas sem formação.

---

## 7. A Regra da Assinatura

**Regra:** A frase "O corpo sabe o caminho de volta a si." é a assinatura da marca e deve aparecer SEMPRE como última frase de TODOS os posts de feed, scripts de Reel e CTAs de carrossel.

Esta frase:
- Sintetiza o posicionamento da Mariana (o corpo como guia, não como problema a corrigir)
- Cria reconhecimento de marca ao longo do tempo
- É poética mas não vaga — tem um significado claro e terapêutico
- Funciona como assinatura visual e auditiva (no voice-over dos Reels)

Não alterar. Não substituir. Nunca omitir.
```

### quality-criteria.md

> The 11 pass/fail checks the critique pass runs against every draft.

```markdown
# Critérios de Qualidade — @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Versão:** 2.0

Todo o conteúdo produzido por este squad é avaliado contra os seguintes critérios antes de ser apresentado à Mariana. Um post só avança para aprovação final quando passa em todos os critérios obrigatórios.

---

## Critério 1 — Save-Worthiness (OBRIGATÓRIO)

**Pergunta:** Este conteúdo tem uma estrutura que justifica ser guardado para reler ou usar mais tarde?

**Indicadores positivos (pelo menos 1 deve estar presente):**
- [ ] Tem uma lista numerada com mecanismos explicados (ex: "5 plantas para o sono — e como funcionam")
- [ ] É um tutorial com passos concretos e executáveis em casa
- [ ] É um carrossel de referência que a pessoa vai querer consultar antes de usar uma planta/óleo
- [ ] Tem um ritual completo com ingredientes, proporções e intenções
- [ ] Slide final do carrossel tem CTA explícito para guardar: "Guarda este post para quando precisares"

**Indicadores negativos (nenhum deve estar presente):**
- Post puramente inspiracional sem substância prática
- Anúncio de evento sem conteúdo de valor
- Frase isolada sem contexto ou mecanismo

**Avaliação:** PASSA / FALHA

---

## Critério 2 — Conformidade PT-PT (OBRIGATÓRIO)

**Pergunta:** O texto está em Português europeu correcto sem brasilismos?

**Checklist de conformidade:**
- [ ] "stress" (não "estresse")
- [ ] "sessão" (não "seção")
- [ ] "perceber" (não "entender" no sentido brasileiro)
- [ ] "tuteia" consistente — NUNCA "você" quando o texto tuteia
- [ ] Sem "pra", "pro", "pras", "pros"
- [ ] Sem "venha" (PT-BR) → usar "vem"
- [ ] Sem "a disposição" → usar "à disposição" ou reformular
- [ ] Sem "reike" → SEMPRE "reiki"
- [ ] Sem mistura de registos PT-PT e PT-BR na mesma legenda

**Avaliação:** PASSA (0 erros) / FALHA (1+ erros — listar correcções)

---

## Critério 3 — Âncora Farmacêutico (OBRIGATÓRIO para posts educativos)

**Pergunta:** O post menciona plantas, substâncias, mecanismos, ou terapias? Se sim, a credencial farmacêutica da Mariana aparece nos primeiros 2 parágrafos?

**Critério:** Qualquer post do Pilar Educativo Integrativo (fitoterapia, aromaterapia, plantas, compostos activos) DEVE incluir uma das fórmulas aprovadas:
- "Como farmacêutica, o que me fascina nesta planta é..."
- "A ciência chama-lhe X, eu chamo-lhe..."
- Referência explícita à formação em Farmácia/Fitoterapia nos primeiros 2 parágrafos

**Não aplicável a:** posts de Bastidores puramente pessoais (Pilar 4) e posts de terapias energéticas sem componente científica.

**Avaliação:** PASSA / FALHA / N/A

---

## Critério 4 — Força do Hook (OBRIGATÓRIO)

**Pergunta:** A primeira frase (antes do "ver mais" — aproximadamente os primeiros 125 caracteres) é forte o suficiente para parar o scroll?

**Checklist:**
- [ ] Específico — nomeia uma experiência, sensação, ou problema concreto (não vago)
- [ ] Não começa com "Olá" ou apresentação da Mariana
- [ ] Não começa com uma pergunta retórica fraca ("Já ouviste falar de X?")
- [ ] Cria curiosidade, reconhecimento imediato, ou desafio a uma crença
- [ ] Funciona sozinho sem contexto adicional
- [ ] Para carrosséis: o Slide 1 tem máximo 8 palavras e impacto visual imediato

**Padrões de hook validados:**
- Sensação corporal: "Já acordaste com aquela sensação de peso no peito que não consegues explicar?"
- Contraintuitivo: "O que chamas de ansiedade pode ser o teu sistema nervoso a tentar salvar-te."
- Credencial + curiosidade: "Como farmacêutica, o que me fascina no ashwagandha não é o nome sânscrito — é o que ele faz ao teu cérebro."
- Âncora temporal: "Se tens mais de 40 anos e sentes que o teu corpo está a mudar — este post é para ti."

**Avaliação:** PASSA / FRACO (sugerir alternativa) / FALHA

---

## Critério 5 — Especificidade do CTA (OBRIGATÓRIO)

**Pergunta:** O Call-to-Action é específico e accionável?

**CTAs PROIBIDOS:**
- "Curtam e comentem" — genérico, sem valor
- "Não se esqueçam de seguir" — linguagem de YouTuber
- "Partilhem com alguém" — sem contexto de quem ou porquê

**CTAs APROVADOS (exemplos):**
- "Guarda este post para quando precisares de apoio nesta fase." — save-first
- "Comenta com a planta que já usas e eu conto-te o mecanismo." — engagement qualitativo
- "Partilha com uma amiga que está a atravessar uma transição de vida." — expansão com contexto
- "Experimenta este ritual esta semana e conta-me como correu nos comentários." — acção + feedback
- "Guarda este carrossel — vai querer reler quando escolheres o óleo essencial certo."

**Avaliação:** PASSA / FALHA (reescrever CTA)

---

## Critério 6 — Precisão Holística (OBRIGATÓRIO)

**Pergunta:** Todas as afirmações sobre mecanismos de plantas, terapias e substâncias são rigorosas e verificáveis?

**Checklist:**
- [ ] "Vibração alta" ou "frequências elevadas" NÃO aparecem sem contexto ou mecanismo explicado
- [ ] Mecanismos de plantas estão correctos e não exagerados (ex: "apoia o sono" não "cura a insónia")
- [ ] Reiki é descrito como autoconhecimento/regulação energética, NUNCA como magia ou cura garantida
- [ ] "Detox" só aparece com especificação do quê e como (não usado como conceito vago)
- [ ] Nomes científicos de plantas estão correctos quando incluídos

**Validação:** Taís Terapias valida este critério antes da entrega.

**Avaliação:** PASSA / FALHA (lista de correcções da Taís)

---

## Critério 7 — Conformidade Legal (OBRIGATÓRIO)

**Pergunta:** O conteúdo está em conformidade com a regulamentação ASAE e Decreto-Lei 74/2010 PT sobre publicidade de suplementos e terapias?

**Proibido absolutamente:**
- "Cura" — nunca usar como promessa directa
- "Trata [doença específica]" — proibido por lei
- "Elimina [sintoma/doença]" — promessa terapêutica ilegal
- "Comprovado cientificamente para curar" — sem substanciação regulatória

**Linguagem aprovada:**
- "Pode apoiar..." / "Complementa..." / "Ajuda o corpo a..."
- "Estudos sugerem que..." (com substância real, não fabricada)
- "Na tradição da fitoterapia, é usado para apoiar..."
- "Como complemento a um estilo de vida equilibrado..."

**Avaliação:** PASSA / FALHA (correcção obrigatória antes de qualquer aprovação)

---

## Critério 8 — Assinatura da Marca (OBRIGATÓRIO)

**Pergunta:** O post termina com "O corpo sabe o caminho de volta a si."?

**Regra:** Esta frase deve ser a última frase de TODOS os posts de feed. Sem excepções.
- Para carrosséis: no slide final E na legenda
- Para Reels: na legenda e no script de encerramento (falado ou em texto on-screen)
- Não modificar, não substituir, não omitir

**Avaliação:** PASSA / FALHA

---

## Critério 9 — Hashtags (OBRIGATÓRIO)

**Checklist:**
- [ ] Entre 5 e 8 hashtags (nem menos, nem mais)
- [ ] Inclui obrigatoriamente #marianabotelho
- [ ] Inclui pelo menos 1 hashtag de terapia relevante ao tema
- [ ] ZERO erros ortográficos nas hashtags — especialmente: NUNCA "#reike" (sempre "#reiki")
- [ ] Sem hashtags genéricas irrelevantes (ex: #amor #vida se não for o tema)
- [ ] Sem hashtags em PT-BR num post PT-PT

**Hashtags base aprovadas:**
#marianabotelho #farmaceuticaholistica #terapiasenergeticas #reiki #cosmeticanatural #fitoterapia #saudeholistica #mulheres45 #bemestar #aromaterapia #terapiasholísticas #ham #het

**Avaliação:** PASSA / FALHA (listar correcções)

---

## Critério 10 — Consistência de Tom PT-PT (ORIENTAÇÃO)

**Pergunta:** O tom geral do post é consistente com a voz da Mariana — íntimo, poético, directo, sem deslizar para o comercial/institucional?

**Sinais de deslizamento para evitar:**
- Tom institucional: "Atuo na área da saúde holística há mais de X anos" — frio, CV
- Tom comercial: "Não percas esta oportunidade" / "Garante já o teu lugar" — venda agressiva
- Tom académico-frio: parágrafos longos sem respiração, sem emoção
- Tom abstracto-vago: "energia de amor e luz" sem substância

**Tom alvo:** Como uma farmacêutica que é também terapeuta e escritora — rigorosa mas quente, específica mas poética.

**Avaliação:** BOM / AJUSTAR (sugestão de revisão de tom)

---

## Critério 11 — Ausência de Padrões Genéricos de IA (OBRIGATÓRIO)

**Pergunta:** O texto evita os tiques reconhecíveis de escrita gerada por IA?

**Checklist:**
- [ ] Sem travessão como conector de ideias no meio de frases (rótulos estruturais como "Slide 1 — HOOK" são permitidos; travessões dentro do corpo da legenda não são)
- [ ] Sem construção "não só X, mas também Y"
- [ ] Sem regra de três forçada (grupos de três criados artificialmente onde o número natural seria outro)
- [ ] Sem vocabulário abstracto-vazio: "crucial", "fundamental" (como reforço vazio), "fomentar", "moldar" (abstracto), "impulsionar" (abstracto), "capacitar", "sinergia", "panorama"/"cenário" (abstracto), "mergulhar", "testemunho de"
- [ ] Sem adjectivos promocionais vazios sem substância concreta a seguir ("incrível", "revolucionário", "imperdível", "deslumbrante")
- [ ] Sem enchimento ("é importante notar que", "de forma a", "devido ao facto de que")
- [ ] Sem conclusões genéricas que serviriam para qualquer conta de bem-estar sem alteração

**Teste rápido:** ler a legenda em voz alta e perguntar "isto podia ter sido escrito por qualquer conta genérica de bem-estar, sem nada da voz da Mariana?" Se sim, falha.

**Avaliação:** PASSA / FALHA (listar correcções — ver anti-padrão 13 em `anti-patterns.md`)

---

## Resumo da Avaliação

| Critério | Tipo | Responsável |
|----------|------|-------------|
| 1. Save-Worthiness | OBRIGATÓRIO | Catarina / Íris |
| 2. PT-PT Conformidade | OBRIGATÓRIO | Renata |
| 3. Âncora Farmacêutico | OBRIGATÓRIO (educativo) | Renata / Catarina |
| 4. Hook Forte | OBRIGATÓRIO | Catarina |
| 5. CTA Específico | OBRIGATÓRIO | Catarina / Renata |
| 6. Precisão Holística | OBRIGATÓRIO | Taís |
| 7. Conformidade Legal | OBRIGATÓRIO | Taís / Renata |
| 8. Assinatura da Marca | OBRIGATÓRIO | Renata |
| 9. Hashtags | OBRIGATÓRIO | Renata |
| 10. Consistência de Tom | ORIENTAÇÃO | Renata |
| 11. Ausência de Padrões Genéricos de IA | OBRIGATÓRIO | Renata |

**Regra de aprovação:** Todos os critérios OBRIGATÓRIOS devem ter PASSA para avançar para a Mariana. O Critério 10 é orientação — falhar não bloqueia, mas deve ser corrigido.
```

### anti-patterns.md

> Concrete "never do this" examples with the correct alternative — this is what the old squad's bad output violated.

```markdown
# Anti-Padrões — @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Versão:** 2.0

Este documento lista os erros que NUNCA devem aparecer no conteúdo produzido para @marianabotelho.pt. Cada ponto tem um exemplo do problema e a alternativa correcta.

---

## NUNCA FAZER

### 1. "Vibração alta" sem mecanismo
**Problema:** Usar "vibração alta", "elevar a vibração", "frequências elevadas" como conceitos isolados sem explicar o mecanismo ou contexto.
**Exemplo errado:** "O Reiki eleva a tua vibração e traz energia positiva."
**Alternativa correcta:** "O Reiki actua sobre o sistema nervoso autónomo — muitas pessoas descrevem uma sensação de relaxamento profundo que se assemelha ao estado pré-sono. Não é magia — é a regulação do eixo parassimpático."
**Porquê:** A audiência 45-54 toma decisões de saúde. Linguagem vaga sem mecanismo não credibiliza — afasta quem tem formação e não convence quem não tem.

---

### 2. "Reike" em vez de "reiki"
**Problema:** Erro ortográfico grave que apareceu 6 vezes no perfil real da Mariana (Post 3). Destrói credibilidade de uma farmacêutica especializada em terapias holísticas.
**Exemplo errado:** `#reike` / "sessão de reike" / "praticante de reike"
**Alternativa correcta:** `#reiki` / "sessão de reiki" / "praticante de reiki"
**Regra:** Verificar TODAS as ocorrências de "reiki" no texto e em todas as hashtags antes de qualquer entrega.

---

### 3. Mistura de PT-BR e PT-PT na mesma peça
**Problema:** Usar vocabulário, ortografia ou estruturas brasileiras num post que de resto está em PT-PT. Confunde a audiência portuguesa e sinaliza falta de cuidado editorial.
**Exemplos errados:**
- "estresse" (BR) em vez de "stress" (PT)
- "venha conhecer" (BR) em vez de "vem conhecer" (PT)
- "seção" (BR) em vez de "secção" ou "sessão" (PT, dependendo do contexto)
- "a disposição" (BR) em vez de "à disposição" (PT)
- "pra" / "pro" / "tá" (marcas de oralidade BR)
**Alternativa correcta:** Escolher PT-PT e manter rigorosamente até ao fim. A audiência portuguesa e brasileira compreende PT-PT; o inverso cria estranheza para os portugueses (79% da audiência).

---

### 4. "Você" quando o texto tuteia
**Problema:** A Mariana tuteia sempre ("tu", "te", "o teu"). Usar "você" quebra o contrato de intimidade com a audiência.
**Exemplos errados:** "Você merece cuidar de si." / "O seu corpo sabe." / "A sua vida muda quando..."
**Alternativa correcta:** "Mereces cuidar de ti." / "O teu corpo sabe." / "A tua vida muda quando..."
**Regra:** Pesquisar "você" / "seu" / "sua" (quando possessivo de 2ª pessoa) em todo o texto antes de entregar.

---

### 5. Promessas de cura ou tratamento
**Problema:** Afirmações que prometem resultados terapêuticos específicos violam o Decreto-Lei 74/2010 PT (publicidade de suplementos e terapias) e podem atrair atenção da ASAE.
**Exemplos errados:**
- "A lavanda cura a ansiedade."
- "O Reiki trata depressão."
- "Este elixir elimina a insónia."
- "Comprovado cientificamente para curar o stress."
**Alternativa correcta:**
- "A lavanda é estudada pelo seu efeito calmante — actua sobre receptores GABA, o mesmo mecanismo de alguns ansiolíticos, mas de forma suave e sem dependência."
- "O Reiki apoia o processo de relaxamento profundo. Muitos clientes descrevem melhorias no sono e na gestão do stress após sessões regulares."
**Vocabulário aprovado:** apoia / complementa / pode ajudar a / é estudado para / na tradição da fitoterapia é usado para

---

### 6. Estética de stock photo
**Problema:** A Mariana usa fotografia autêntica — luz natural, mãos a trabalhar, natureza real, o alambique. Imagens genéricas de banco de imagens (mulheres sorridentes em fundo branco, flores perfeitas em estúdio) são incongruentes com a identidade visual da marca.
**Exemplos errados nas specs de design:**
- "Usar imagem de banco de imagens de mulher meditando"
- "Foto de flores de lavanda em fundo branco"
- Imagens com filtros artificiais excessivos
**Alternativa correcta:**
- "Fotografia da Mariana com planta na mão, luz natural"
- "Close do alambique de cobre em funcionamento"
- "Fotografia de ritual com ervas e cristais no atelier da Mariana"

---

### 7. Posts só de anúncios de eventos sem conteúdo de valor
**Problema:** Postar apenas "Próxima sessão HAM: [data e local]. Reserva agora." sem contexto, sem educação, sem história. A audiência segue a Mariana pelo conteúdo — não pela agenda.
**Exemplo errado:** Post sobre sessão HET em Setúbal apenas com data, hora e preço.
**Alternativa correcta:** Anunciar o evento dentro de um post de valor — "O que é o HET e por que escolhi levar esta prática a Setúbal este mês. [Contexto do HET, mecanismo, o que esperar] + no final: [data, como reservar]"
**Regra:** Todo o post de evento deve ter pelo menos 60% de conteúdo de valor educativo ou narrativo.

---

### 8. Omitir o âncora farmacêutico em posts educativos
**Problema:** Escrever sobre plantas, óleos, mecanismos ou terapias sem mencionar a formação farmacêutica da Mariana. É o diferenciador mais forte do perfil e o que justifica confiança para a audiência 45-54.
**Exemplo errado:** Post sobre ashwagandha que menciona "reduz o stress" sem citar a formação ou o mecanismo.
**Alternativa correcta:** "Como farmacêutica, o que me fascina na Withania somnifera (ashwagandha) é que age sobre o eixo HPA — o sistema de resposta ao stress do teu corpo — de uma forma que a medicina convencional ainda está a estudar."

---

### 9. CTAs genéricos sem acção específica
**Problema:** CTAs vazios que não dizem à audiência o que fazer nem porquê.
**Exemplos errados:**
- "Curtam e comentem!"
- "Partilhem com alguém!"
- "Sigam para mais conteúdo."
- "Deixem o vosso like."
**Alternativa correcta:**
- "Guarda este carrossel para quando escolheres o óleo essencial certo para ti."
- "Comenta com a planta que já tens em casa e eu conto-te o que ela faz."
- "Partilha com uma amiga que está a atravessar uma transição hormonal — este post é para ela."
- "Experimenta este ritual esta semana e conta-me como correu nos comentários 👇"

---

### 10. Carrosséis sem estrutura salvável
**Problema:** Um carrossel com frases soltas inspiracionais num por slide não tem estrutura de referência — não activa saves.
**Exemplos errados:**
- Carrossel de 8 slides com uma citação por slide
- Carrossel de "dicas" sem mecanismo ou contexto
- Slides sem progressão lógica (podem ser lidos em qualquer ordem)
**Alternativa correcta:**
- Carrossel "5 plantas para o sistema nervoso — mecanismo, dose e cuidados": cada slide é uma planta com mecanismo explicado → estrutura de referência → activa save

---

### 11. "Detox" sem especificação
**Problema:** "Detox" é um termo vago e potencialmente enganoso sem especificação do que está a ser removido, pelo quê, e como.
**Exemplos errados:** "Esta planta faz detox ao teu organismo." / "Ritual de detox energético."
**Alternativa correcta:**
- Para fitoterapia: "A alcachofra (Cynara scolymus) apoia a função hepática — estimula a produção de bílis, o que facilita a digestão de gorduras. É o mecanismo por detrás do que muitas pessoas chamam de 'detox'."
- Para terapias energéticas: "Limpeza energética" (não "detox energético") — e explicar o que significa no contexto da terapia específica.

---

### 12. Emojis em excesso
**Problema:** Usar mais de 3 emojis no mesmo post ou emojis irrelevantes para o tema fragmentam a leitura e infantilizam o tom.
**Exemplo errado:** "✨🌸💫🙏🌿💕🦋 A lavanda é incrível! ❤️🌺✨"
**Alternativa correcta:** Emojis funcionais e moderados: 🌿 para natureza/plantas, 💫 para terapias energéticas, ❤️ para conexão emocional, 👇 para CTA. Máximo 2-3 por legenda.

---

### 13. Padrões genéricos de escrita de IA ("AI slop")
**Problema:** Texto gerado por IA tem tiques reconhecíveis que sinalizam "isto foi escrito por um robô" a qualquer leitor treinado a reconhecê-los — e cada vez mais leitores reconhecem. Isto destrói a credencial de autenticidade que é o maior diferenciador da Mariana.

**Travessão em excesso no corpo do texto.** Frases como "Slide 1 — HOOK" (rótulo estrutural) estão bem; travessões dentro do corpo da legenda como conector de ideias são um tique de IA.
**Exemplo errado:** "A lavanda acalma — não porque seja mágica — mas porque actua no sistema nervoso."
**Alternativa correcta:** "A lavanda acalma. Não porque seja mágica, mas porque actua no sistema nervoso."

**"Não só X, mas também Y."**
**Exemplo errado:** "Não só relaxa o corpo, mas também acalma a mente."
**Alternativa correcta:** "Relaxa o corpo e acalma a mente." (ou escolher só o ponto mais forte)

**Regra de três forçada** — agrupar tudo em conjuntos de três mesmo quando o número natural é outro.
**Exemplo errado:** "Uma planta rigorosa, calorosa e transformadora."
**Alternativa correcta:** "Uma planta rigorosa e calorosa." (ou só um adjectivo, se for o que a frase pede)

**Vocabulário de IA / abstracto-vazio.** "crucial", "fundamental" (usado como reforço vazio), "fomentar", "moldar" (abstracto), "impulsionar" (abstracto), "capacitar", "sinergia", "panorama"/"cenário" (abstracto), "mergulhar" (no sentido de "explorar em profundidade"), "testemunho de", "reforça a importância de".
**Exemplo errado:** "Este ritual é fundamental para fomentar o teu bem-estar e moldar uma nova relação com o corpo."
**Alternativa correcta:** "Este ritual muda a forma como sentes o teu corpo."

**Adjectivos promocionais vazios** — sobreposto ao anti-padrão 6 (estética de stock photo), mas aplicado à escolha de palavras: "incrível", "revolucionário", "imperdível", "deslumbrante" sem substância concreta a seguir.
**Exemplo errado:** "Este óleo essencial é absolutamente incrível!"
**Alternativa correcta:** nomear o mecanismo ou o efeito concreto, sem o adjectivo.

**Enchimento.** "É importante notar que", "de forma a", "devido ao facto de que" — cortar sem perda de sentido.

**Conclusões genéricas** que poderiam aparecer em qualquer post de qualquer marca sem alteração.
**Exemplo errado:** "O futuro do bem-estar é promissor."
**Alternativa correcta:** um facto, plano ou convite específico.

**Alternativa correcta (regra geral):** ler a legenda em voz alta e perguntar "isto podia ter sido escrito por qualquer conta genérica de bem-estar, sem nada da voz da Mariana?" Se sim, reescrever com um dos 6 tons de `tone-of-voice.md` até deixar de ser verdade.

---

## SEMPRE FAZER

### 1. Verificar "reiki" em todas as ocorrências (texto + hashtags)
Antes de qualquer entrega, pesquisar "reike" e corrigir para "reiki".

### 2. Incluir assinatura da marca em todos os posts de feed
"O corpo sabe o caminho de volta a si." — última frase, sem excepções.

### 3. Testar o hook isoladamente
Copiar a primeira frase/125 caracteres e perguntar: "Isto faria parar o scroll de uma mulher de 48 anos com cansaço crónico?"

### 4. Verificar a cadeia tuteia/você em todo o texto
Pesquisar "você" / "seu" / "sua" (como possessivo de 2ª pessoa) e corrigir para "te" / "teu" / "tua".

### 5. Incluir CTA para save em carrosséis educativos
Se o carrossel tem estrutura de referência, o slide final e/ou a legenda deve ter: "Guarda este post..."

### 6. Confirmar que nenhuma promessa de cura aparece em contexto legal sensível
Antes de entregar posts sobre doenças, sintomas ou condições de saúde, rever com vocabulário aprovado: apoia / complementa / pode ajudar a.

### 7. Contar hashtags (5-8) e verificar ortografia
Especialmente: #reiki (nunca #reike), #terapiasholísticas (com acento), #farmaceuticaholistica.

### 8. Ler a legenda à procura de tiques de escrita de IA
Travessões no meio de frases, "não só X mas também Y", regra de três forçada, vocabulário abstracto-vazio (crucial, fomentar, moldar, sinergia), adjectivos promocionais sem substância, enchimento, conclusões genéricas. Ver anti-padrão 13.
```

### output-examples.md

> Three full worked examples (carousel, Reel, reference-list carousel) showing what "good" looks like end to end.

```markdown
# Exemplos de Output — @marianabotelho.pt
**Squad:** marianabotelho-content-ig
**Versão:** 2.0
**Língua:** PT-PT exclusivo

Estes são exemplos completos e realistas do tipo de conteúdo que este squad produz. Servem como referência de qualidade, tom e estrutura para todos os agentes.

---

## Exemplo 1 — Carrossel: Reiki para Ansiedade

**Pilar:** Educativo Integrativo + Terapias Energéticas
**Ângulo:** O Mecanismo Explicado (Reiki como regulação do sistema nervoso, não magia)
**Tom:** Educativo-Científico (Tom 2) com momentos Íntimo-Poéticos (Tom 1)
**Formato:** Carrossel 8 slides + Legenda
**Objectivo:** Save + Comentários

---

### SLIDES

**Slide 1 — HOOK**
> **O Reiki não é o que pensas.**
> *(8 palavras, tipografia grande, fundo cor creme, letra verde-musgo escuro)*

**Slide 2 — A PERGUNTA**
> **E se a ansiedade não for o problema —**
> **mas o sinal que o teu sistema nervoso está a enviar?**
>
> O Reiki não adormece o sinal.
> Ajuda o teu corpo a ouvi-lo com menos medo.

**Slide 3 — O MECANISMO (farmacêutico)**
> **A ciência chama-lhe activação parassimpática.**
>
> Quando o corpo está em ansiedade crónica, o sistema nervoso simpático domina — o "luta ou fuga".
>
> O toque terapêutico do Reiki activa o sistema nervoso parassimpático — o "repouso e digestão".
>
> É o mesmo mecanismo de uma respiração profunda. Mas mais sustentado.

**Slide 4 — O QUE NÃO É**
> **O Reiki não cura a ansiedade.**
>
> Não substitui acompanhamento psicológico.
> Não elimina as causas do stress.
>
> O que faz: cria um espaço de regulação onde o teu sistema nervoso aprende que pode descansar.

**Slide 5 — O QUE ACONTECE NUMA SESSÃO**
> **O que podes esperar:**
>
> 🌿 Sensação de calor ou formigueiro nas zonas de toque
> 🌿 Sonolência ou estado meditativo profundo
> 🌿 Após a sessão: alguns sentem leveza, outros precisam de dormir
>
> Não é igual para toda a gente. O corpo responde ao que precisa.

**Slide 6 — A PERGUNTA DA AUDIÊNCIA**
> **"Mas isto tem comprovação científica?"**
>
> Há estudos (Universidade de Michigan, 2018) que documentam reduções de cortisol após sessões de toque terapêutico.
>
> Não é prova definitiva. É evidência emergente que justifica continuar a investigar.
>
> Como farmacêutica, isso é suficiente para eu confiar no processo com integridade.

**Slide 7 — O CONVITE**
> **Quem pode beneficiar do Reiki para a ansiedade?**
>
> ✓ Mulheres em transição de vida (hormonal, profissional, relacional)
> ✓ Pessoas com stress crónico que já experimentaram outras abordagens
> ✓ Quem quer uma prática de auto-regulação além da medicação
>
> *(Não substituição — complemento)*

**Slide 8 — CTA + ASSINATURA**
> **Guarda este carrossel para quando alguém te perguntar o que é o Reiki.**
>
> Ou para quando precisares de te lembrar que o teu sistema nervoso pode aprender a descansar.
>
> 🌿 Perguntas? Escreve nos comentários — estou aqui.
>
> *O corpo sabe o caminho de volta a si.*

---

### LEGENDA

Como farmacêutica, há uma pergunta que me fazem sempre sobre o Reiki: "Mas isto tem alguma base científica?"

A resposta honesta é: tem evidência emergente — não prova definitiva. E isso, para mim, é suficiente para praticar com integridade.

O que os estudos documentam é a activação do sistema nervoso parassimpático durante o toque terapêutico. Em português simples: o corpo sai do modo "luta ou fuga" e entra no modo "repouso e recuperação". É o mesmo mecanismo de uma respiração diafragmática prolongada — mas mantido por 60 minutos.

Para mulheres com ansiedade crónica, esse espaço de regulação pode ser transformador. Não porque o Reiki "cure" — mas porque oferece ao sistema nervoso uma experiência repetida de que é seguro descansar.

Desliza para perceber o que acontece realmente no corpo durante uma sessão 👉

Tens perguntas sobre Reiki ou estás a considerar a tua primeira sessão? Comenta aqui ou envia mensagem directa — respondo a tudo.

*O corpo sabe o caminho de volta a si.*

#marianabotelho #reiki #terapiasholísticas #ansiedade #sistemanervosoautónomo #farmaceuticaholistica #saudeholistica #mulheres45

---

## Exemplo 2 — Reel: Lavanda — O Mecanismo Farmacológico

**Pilar:** Educativo Integrativo + Cosmética Natural
**Ângulo:** A Farmácia por Detrás da Planta (linalol + receptores GABA)
**Tom:** Educativo-Científico (Tom 2) com abertura Ritual-Contemplativa (Tom 5)
**Formato:** Script de Reel 45-60 segundos + Legenda
**Objectivo:** Save + Alcance (novo público de mulheres com interesse em saúde natural)

---

### SCRIPT DO REEL

**[Cena 1 — ABERTURA, 0-3s]**
*[Visual: mãos da Mariana a segurar ramo de lavanda fresca, luz da manhã. Voice-over suave.]*

> "Esta planta cheira a sono. E há uma razão científica para isso."

---

**[Cena 2 — APRESENTAÇÃO DO MECANISMO, 3-15s]**
*[Visual: close da lavanda. Texto on-screen: "Lavanda (Lavandula angustifolia)" aparece em tipografia elegante]*

> "A lavanda contém linalol — um composto que actua sobre os receptores GABA do sistema nervoso central. São os mesmos receptores que os ansiolíticos convencionais activam."

*[Texto on-screen: "Linalol → Receptores GABA → Efeito calmante"]*

> "A diferença? O linalol da lavanda é mais suave, sem o risco de dependência."

---

**[Cena 3 — COMO USAR, 15-35s]**
*[Visual: mãos a colocar óleo de lavanda no pulso. Slow motion.]*

> "Como farmacêutica, o que me fascina é que a via de administração importa.

> Por inalação — difusor ou umas gotas na almofada — o linalol entra pelo nervo olfactivo directamente para o sistema límbico. É a via mais rápida.

> Por via tópica — pulsos, planta dos pés — a absorção é mais lenta mas mais prolongada.

> Por isso, para o sono: almofada. Para a ansiedade aguda: inalação directa."

*[Texto on-screen: "Sono → almofada / Ansiedade → inalação"]*

---

**[Cena 4 — CUIDADO IMPORTANTE, 35-45s]**
*[Visual: frascos de óleo essencial no atelier. Detalhe da Mariana a ler o rótulo.]*

> "Um cuidado: óleo essencial puro NÃO vai directamente na pele sem diluição. Uma ou duas gotas em óleo de amêndoa ou jojoba — sempre."

*[Texto on-screen: "Sempre diluir antes de aplicar na pele"]*

---

**[Cena 5 — ENCERRAMENTO, 45-55s]**
*[Visual: Mariana de costas, olhando janela com luz natural. A lavanda em plano próximo.]*

> "A lavanda não substitui tratamento médico para ansiedade ou insónia. Mas como aliada? É uma das plantas mais estudadas e mais bem toleradas que conheço."

*[Texto on-screen: "O corpo sabe o caminho de volta a si."]*

---

### LEGENDA DO REEL

A lavanda (Lavandula angustifolia) não cheira apenas bem — age sobre os receptores GABA do sistema nervoso central. Os mesmos receptores dos ansiolíticos. Mas sem o risco de dependência.

Como farmacêutica, esta planta é uma das minhas referências para apoio ao sono e gestão do stress diário.

No Reel de hoje: o mecanismo, as duas vias de administração, e o cuidado essencial que poucos mencionam.

Guarda este vídeo para quando precisares de te lembrar como usar a lavanda correctamente 🌿

#marianabotelho #lavanda #aromaterapia #fitoterapia #farmaceuticaholistica #oleosessenciais #saudeholistica #bemestar

*O corpo sabe o caminho de volta a si.*

---

## Exemplo 3 — Carrossel: As 5 Plantas Adaptogénicas para Mulheres em Transição

**Pilar:** Educativo Integrativo
**Ângulo:** Lista de Referência Salvável (formato que activa saves)
**Tom:** Educativo-Científico (Tom 2) + Urgência-Gentil (Tom 6)
**Formato:** Carrossel 7 slides + Legenda
**Objectivo:** Save (principal) + Comentários

---

### SLIDES

**Slide 1 — HOOK**
> **5 plantas que o teu sistema nervoso precisa de conhecer agora.**
> *(fundo terra, tipografia serifada branca)*

**Slide 2 — CONTEXTO**
> **O que é uma planta adaptogénica?**
>
> Adaptogénica não é um nome bonito de marketing.
>
> É uma classificação científica para plantas que ajudam o corpo a adaptar-se ao stress — regulando o cortisol, apoiando o eixo HPA, sem efeito estimulante ou sedativo extremo.
>
> São especialmente relevantes para mulheres em transição hormonal.

**Slide 3 — PLANTA 1**
> **🌿 Ashwagandha (Withania somnifera)**
>
> Actua sobre o eixo hipotálamo-hipófise-adrenal. Reduz cortisol em excesso.
>
> Ideal para: stress crónico, fadiga adrenal, dificuldade em adormecer por mente activa.
>
> Cuidado: pode interagir com medicação da tiróide. Consultar antes de tomar.

**Slide 4 — PLANTA 2**
> **🌿 Rhodiola (Rhodiola rosea)**
>
> Aumenta a resistência ao stress físico e mental. Estudada para fadiga cognitiva.
>
> Ideal para: períodos de sobrecarga de trabalho, "burnout" leve, dificuldade de concentração.
>
> Nota: tem efeito estimulante suave — tomar de manhã, nunca ao deitar.

**Slide 5 — PLANTA 3**
> **🌿 Maca (Lepidium meyenii)**
>
> Não é um estrogénio. Actua como modulador do eixo HPA e HPG (eixo reprodutor).
>
> Ideal para: transição da menopausa, suporte de energia e libido, fadiga relacionada com alterações hormonais.
>
> Escolher: maca gelatinizada (mais fácil de digerir do que a crua).

**Slide 6 — PLANTAS 4 E 5**
> **🌿 Eleuthero (Eleutherococcus senticosus)**
> Imuno-modulador + adaptogénico. Bom para quem adoece facilmente em stress.
>
> **🌿 Schisandra (Schisandra chinensis)**
> Hepatoprotectora + adaptogénica. Apoia fígado e sistema nervoso em simultâneo.
>
> Ambas com boa tolerabilidade — começar com dose baixa.

**Slide 7 — CTA + ASSINATURA**
> **Guarda este carrossel — é a tua referência de adaptogénicos.**
>
> Na próxima vez que estiveres numa loja de saúde ou à procura de apoio para o stress, já sabes o que procurar — e o que perguntar.
>
> Tens dúvidas sobre qual é a mais indicada para ti? Comenta ou envia mensagem directa 🌿
>
> *O corpo sabe o caminho de volta a si.*

---

### LEGENDA

Se tens mais de 40 anos e sentes que o teu corpo está a pedir mais apoio do que antes — esta lista é para ti.

Como farmacêutica, as plantas adaptogénicas são uma das minhas categorias de referência para mulheres em transição de vida. Não porque sejam a resposta para tudo — mas porque têm evidência científica séria sobre como actuam no eixo do stress.

Adaptogénico não é marketing. É uma classificação que descreve plantas que regulam a resposta ao cortisol sem criar dependência, sem estimular em excesso, sem sedar.

Desliza para conhecer as 5 que eu uso como referência clínica — com mecanismo de acção, indicação e o cuidado que ninguém te conta.

Guarda este carrossel. Vai querer consultar da próxima vez que fores a uma loja de produtos naturais ou tiveres consulta com o teu médico.

Qual destas plantas já conhecias? Comenta aqui 👇

*O corpo sabe o caminho de volta a si.*

#marianabotelho #adaptogenicos #fitoterapia #ashwagandha #farmaceuticaholistica #menopausa #saudeholistica #mulheres45
```
