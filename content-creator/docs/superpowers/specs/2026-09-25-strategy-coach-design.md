# Strategy Coach — Design (Spec 1 of 4)

Part of the calendar cluster (backlog #1, #2, #4-adjacent, #5, #6). Build order:
**1. Coach (this doc)** → 2. Calendar → 3. Calendar↔Post-creator link → 4. Windsor feedback loop.
Status: **drafted without live review — needs user review before tickets.**

## Purpose

Users often don't know what to offer, what a funnel is, or what "authority" and
"social proof" mean. The Coach takes a few simple answers, does the research
itself, and hands back a complete, ranked, plain-language strategy the user can
react to and refine. **The user is the product** (lecture, workshop,
consultation, course, or a product they make) — the brand's content revolves
around the person, not a catalogue.

## Principles

1. **AI proposes, user reacts.** Never a long interview. Draft first, edit after.
2. **Research before asking.** The Coach gathers data (Windsor, Sherlock) before it bothers the user.
3. **Everything is explained** in one plain sentence (what a funnel/pillar/authority is), never jargon.
4. **Ranked and measurable.** Every goal has a metric, a target, a rank, reasons, and an evidence label.
5. **Gentle tone everywhere** (see Tone rule). PT-PT for all user-facing text.
6. **Nothing is lost.** State lives in the database, not in the chat.
7. **Never copy competitor content** — learn patterns (hooks, CTAs, structure), write fresh in the user's voice.

## Tone rule (applies to all four specs)

All text the app shows or the AI generates is gentle, comforting and
encouraging. No urgency, no "critical", no blame. Gaps are framed as
invitations: not "You haven't posted in a month — critical!" but "Whenever
you feel ready, here's an easy idea to ease back in." Every AI prompt that
produces feedback includes this rule. Tests assert a small banned-word list
(e.g. "crítico", "urgente", "erro seu", "falhaste") is absent from canned copy.

## User flow

1. **Three questions** (one screen, gentle):
   - **Who you are** — niche and what you do (free text).
   - **What you want** — up to 3 goals from the goal menu, for the next 3 months.
   - **What you can offer** — lecture, workshop, consultation, product, or "not sure yet" (Coach then suggests options).
   - *Optional:* 1–3 profiles/sites you admire (any URL or handle) → Sherlock.
2. **Research** — Coach pulls Windsor data (if connected) and Sherlock findings; shows a calm progress checklist (reuse `run_with_progress`).
3. **Strategy draft** — one screen with sections, each with **Accept / Edit / Not for me**:
   goals (ranked), offers, funnel, pillars (with %), authority & social-proof plan, posting rhythm (posts/reels/stories per week and when).
4. **Refinement loop** — free-text reactions ("warmer", "fewer reels", "not the workshop"); AI revises only affected sections and logs the decision.
5. **Accept** — accepted strategy becomes the input to the Calendar (Spec 2).

## Goal menu (plain language, with measurable defaults)

| Goal | Example metric |
|---|---|
| Grow my audience | new followers / month |
| Build trust and authority | saves + shares per post |
| Get more conversations | DMs + comments per week |
| Turn followers into leads | sign-ups / enquiries per month |
| Turn leads into clients | bookings / sales per month |
| Keep my community engaged | repeat engagers, replies |

Each chosen goal is turned into a target relative to the user's stage (from
Windsor when available, otherwise from what they typed).

## Ranking and evidence

Each goal (and later each offer/pillar) gets: **rank, score 0–100, reasons
(2–3 short bullets), evidence label**:
- **Data** — based on Windsor numbers.
- **Pattern** — based on Sherlock findings from reference profiles.
- **Reasoned** — AI marketing reasoning only; the UI says "reasoned, not proven".

Scoring is behind one function `score_goals(inputs) -> list[ScoredGoal]` so the
scorer can be swapped: v1 uses Claude with structured JSON output; **JEV**
(TypeSafe AI, early-access structured-output model with confidence scores,
$0.042/M input tokens) is a candidate drop-in later, not a dependency.
Users can reorder ranks; the Coach explains the trade-off gently and re-plans.

## Sherlock (information gathering) — part of this spec

**Input:** 1–3 sources of any kind: website URL, Instagram handle/URL, TikTok
handle/URL, YouTube URL, or uploaded files/pasted text.
**Two stages:**
1. **Gather** → raw material per source (captions, alt text, metrics where available, transcripts).
2. **Distill** → a short **findings brief** (content mix, hook types, CTA styles,
   structure, tone/rhythm, what seems to drive engagement, adaptable ideas).
   The Coach only ever sees the brief, never raw dumps.

**Writing patterns:** Distill also emits reusable pattern entries
(`hook`, `cta`, `structure`) *described abstractly*, never verbatim content.
These feed the draft prompts in the post creator later.

**Free-only fallback chain** (each step tried in order, next on failure/block):
1. Website: plain HTTP fetch + text extraction.
2. Official Instagram **Business Discovery** API (needs the user's own Business/Creator account token; reads public captions/likes/comments of other Business/Creator accounts; no alt text).
3. **yt-dlp + whisper** for public video metadata/transcripts (TikTok/YouTube/Reels). Already proven in OpenSquad.
4. **Dummy-account crawl** with Playwright and a saved login of a *secondary* account (opt-in, off by default, slow read-only pacing, calm warning about platform rules; never the brand's main account). Playwright already a dependency (`render.py`).
5. **Guided upload** — last resort. On a block Sherlock says so kindly and shows per-platform instructions to provide: PDF export, screenshots, pasted captions **and alt text/photo descriptions** (they carry extra information). Uploaded images are read with the vision model.

Every source result records which method worked and when. No paid scraping
services in v1 (see backlog "Paid scraping services for Sherlock").

## Data model (SQLite, in `db.py`)

- `strategies(id, brand_pack, version, status[draft|accepted], created_at, accepted_at)` — versioned.
- `strategy_sections(strategy_id, kind[goals|offers|funnel|pillars|authority|rhythm], content_json, state[draft|accepted|revisit], evidence)`.
- `strategy_decisions(id, strategy_id, section_kind, action, user_reason, created_at)` — decision log.
- `research_findings(id, brand_pack, source_ref, method, brief_text, patterns_json, fetched_at)`.
- `coach_turns(id, strategy_id, role, text, created_at)` — transcript, stored but **not replayed**.
Columns include `brand_pack`; one brand = one profile for now (see backlog "Multiple social profiles per brand").

## Context handling

Each Coach call is built from: current strategy sections + last N decisions +
relevant findings briefs + the user's latest message. No full-chat replay.
The Coach can reference past decisions ("last time the workshop wasn't for
you, so I left it out"). Versions allow "go back to the previous strategy".

## Modules (isolated, testable)

- `coach.py` — orchestrates flow: `start_strategy`, `draft_strategy`, `refine_section`, `accept_strategy`.
- `scoring.py` — `score_goals` (swappable scorer).
- `sherlock/` — `gather.py` (one function per fallback step), `distill.py`, `chain.py`.
- `prompts/coach_*.md`, `prompts/sherlock_distill.md`.
- New Streamlit tab **Estratégia**; strategy tab uses `theme.py` components.
Cost: every AI call checks `db.would_exceed_daily_cap` and logs cost, as elsewhere.

## Error handling

Any failure is reported gently with a next step ("I couldn't reach that
profile — would you like to upload a screenshot instead?"). Budget-cap hits
say "let's pick this up tomorrow" style, never alarmist.

## Testing

Mocked AI + mocked network for unit tests; scoring and chain-fallback order
tested with fakes; tone banned-word test on canned copy; AppTest for the
three-question screen and section accept/edit. **One real paid end-to-end run
before calling it done** (repo convention).

## Out of scope

Paid scrapers; multi-profile brands; auto-publishing; scheduling (Spec 2).

## Open decisions for review

- Exact Business Discovery setup steps and token handling (verify against current Meta docs at plan time).
- Whether the dummy-account crawl ships in v1 or right after the other four steps.
- Default posting-rhythm numbers per goal.
