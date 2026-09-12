# Mariana Content Studio — Design Spec

## Background

An earlier attempt at automating Instagram content for `@marianabotelho.pt` exists as a 10-agent OpenSquad squad (`marianabotelho-content-ig`, at `C:\Users\Elisson\Documents\Aura\opensquad\squads\marianabotelho-content-ig`). It never reached production quality — text and images were both weak, and no working carousel was ever produced. However, its brand/voice documents are genuinely solid and are reused as-is by this project:

- `pipeline/data/tone-of-voice.md` — 6 named tones (Íntimo-Poético, Educativo-Científico, Provocador-Suave, Narrativo-Pessoal, Ritual-Contemplativo, Urgência-Gentil), each with description, when-to-use, and example hook/copy.
- `pipeline/data/domain-framework.md` — the 4 content pillars (Terapias Energéticas, Cosmética Natural, Educativo Integrativo, Bastidores/Vida), carousel structure (hook slide → body slides → CTA+signature slide), caption structure (7-part: hook → contexto → ponte emocional → insight → reframe → CTA → assinatura), and the mandatory "pharmaceutical anchor" and brand-signature rules.
- `pipeline/data/quality-criteria.md` — 10 pass/fail criteria (save-worthiness, PT-PT compliance, pharmaceutical anchor, hook strength, CTA specificity, holistic-claim accuracy, PT legal compliance re: health claims, brand signature, hashtag rules, tone consistency).
- `pipeline/data/anti-patterns.md` — 12 concrete "never do this" patterns with wrong/right examples (e.g. "reike" → "reiki", PT-BR leakage, unproven cure claims, generic CTAs).
- `pipeline/data/output-examples.md` — full worked examples of finished carousels.

These five files are copied verbatim into this project's `brand/` folder as the source of truth for voice and quality.

## Purpose of this project

A **learning project**: build a small, understandable, real piece of software (not a black-box framework) that produces genuinely good Instagram carousel text (caption + slides) for `@marianabotelho.pt`, reusing the brand knowledge above. Secondary goal: produce a written spec detailed enough to redo this later in TypeScript as a second, separate learning exercise.

## Scope — v1

**In scope:**
- Text only: Instagram carousel slide copy + caption. No image/graphic generation.
- Input either a topic typed directly, or a pasted reference text (article, notes) from which the AI proposes multiple candidate topic angles.
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
- A TypeScript rewrite (deliberately deferred — this spec is written to make that possible later).

## User flow

1. **Input.** User pastes a reference text (max 6,000 words — hard cap, rejected above that with a message to trim/split) or types a topic directly.
2. **Topic extraction** (only if reference text given). AI proposes up to 5 distinct, non-overlapping topic angles genuinely well-supported by the material. Quality over quantity: the prompt explicitly instructs the model not to pad the list to hit a target count — 2 excellent angles beats 5 mediocre ones.
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
  db.py             SQLite schema + CRUD (ideas, drafts, api_calls)
  config.py         reads .env: ANTHROPIC_API_KEY, DB_PATH, MAX_DAILY_SPEND_USD
  brand/            copied from the old squad's pipeline/data/: tone-of-voice.md, domain-framework.md,
                     quality-criteria.md, anti-patterns.md, output-examples.md
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

Four Claude API calls, each a distinct function in `ai.py`:

- `extract_topics(reference_text) -> list[{topic, pillar_guess}]` — instructed to propose up to 5 angles, quality over quantity, never padding the list.
- `generate_draft(topic, tone, pillar) -> {caption, slides}` — prompt includes the relevant tone description/examples from tone-of-voice.md and the structural rules from domain-framework.md.
- `critique_draft(draft) -> list[failed_criteria]` — checks against quality-criteria.md and anti-patterns.md.
- `revise_draft(draft, failed_criteria) -> {caption, slides}` — fixes only the listed issues.

Loop control lives in `app.py`, not `ai.py`: generate → critique → (if failures and round < 2: revise → critique again) → stop after round 2 regardless, always surfacing remaining flags to the human.

Before any of this is wired into the app, prompts for each function are prototyped and iterated directly in Claude Code (using the existing Pro subscription, no API cost) against real brand docs and real example topics, until output quality looks right. Only once prompts are solid do they move into `ai.py` for real API-key testing.

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
- A TypeScript rewrite, using this spec as the blueprint.
