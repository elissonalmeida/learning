# Content Calendar — Design (Spec 2 of 4)

Depends on Spec 1 (accepted strategy). Backlog items #2 and #5.
Status: **drafted without live review — needs user review before tickets.**

## Purpose

Turn the accepted strategy into a monthly calendar that organizes what to
post, when, in which format, and why — to increase engagement, turn contacts
into leads and leads into clients, build authority and social proof. It also
researches **niche dates** (for a holistic niche: portals such as 7/7,
moon phases, zodiac transits, seasonal moments) and proposes posts for them.

## Principles

Same as Spec 1: AI proposes and the user reacts; gentle tone (no urgency or
blame — an empty week is an invitation, not an alarm); PT-PT; state in DB;
every AI call respects the spend cap. The reference's dead grid view is not a
design to copy (backlog #2 note); the month grid is built fresh.

## Concepts

- **Slot** — a planned piece of content on a date: format (`post`, `carousel`, `reel`, `story`), pillar, funnel phase, goal it serves, topic/angle, status.
- **Funnel phase** per slot (e.g. reativação / consistência / conversão), mapped across the month.
- **Pillar allocation** — percentages from the strategy, validated to sum to 100, tracked against planned slots ("your educational pillar is at 20% of the plan, target 35%" phrased gently).
- **Keyword-CTA taxonomy** — categorized CTAs (services / education / community / products) attached to slots; implies comment-keyword → DM later.
- **Theme of the month**, **quarterly featured-offer rotation**, **cap on offer-heavy posts** (default max 2/month), and a **north-star metric** for the month (from the strategy's top goal).
- **Social-proof and authority slots** — the Coach's plan reserves slots for testimonials, results, behind-the-scenes expertise.

## Calendar generation

`generate_month(strategy, month, findings, niche_dates)` produces slots:
1. Rhythm from strategy (posts/reels/stories per week).
2. Pillar % and funnel-phase distribution.
3. Niche dates placed first (fixed anchors), then remaining slots filled.
4. Topics/angles per slot, using Sherlock patterns (hooks/CTA styles) as guidance, never copied content.
The user reacts in a refinement loop ("move the reel", "fewer offers this week", "swap the theme"); AI revises only affected slots and logs decisions.

## Niche dates research

`niche_dates(niche, month) -> list[NicheDate]` with `date, name, why_it_matters (1 sentence), suggested_post_ideas, source, confidence`.
- Astronomical data (moon phases, eclipses, equinoxes/solstices, planetary transits) computed with a library or reliable dataset where possible — **not** invented by the AI; the AI only interprets relevance for the niche.
- Cultural/energetic dates (portals like 7/7, 8/8, seasonal celebrations) from AI research with `confidence` shown.
- Each proposal is **accept / skip**; accepted ones become slots. Results cached per (niche, month).
- Niche comes from the strategy's "who you are" answer; no hard-coded brand text in the engine (brand-pack pattern).

## UI (new tab **Calendário**, using `theme.py`)

- Month grid with per-day badges (format icon/color by pillar) and a list toggle.
- Side panel for the selected slot: details, edit, status.
- "Sugerir datas do nicho" panel listing niche-date proposals.
- Gentle empty states ("This week is open — want me to suggest something light?").
- Status colors reuse the status-pill component.

## Status pipeline

Existing idea statuses (`idea → reviewed → approved/rejected → images_ready → archived`) are reconciled with slot statuses:
`planned → in_production → ready → published`. A slot links to an idea (Spec 3) and its state is derived from the idea's status; `published` is manual until auto-publish exists (backlog #9).

## Data model

- `calendar_slots(id, brand_pack, strategy_id, date, format, pillar, funnel_phase, goal, topic, angle, cta_keyword, status, idea_id NULL, niche_date_id NULL, notes)`.
- `niche_dates(id, brand_pack, month, date, name, why, ideas_json, source, confidence, decision[proposed|accepted|skipped])`.
- `month_plans(id, brand_pack, month, theme, featured_offer, north_star_metric, strategy_id)`.
- `calendar_decisions(...)` mirrors `strategy_decisions`.

## Modules

`calendar_plan.py` (generation, validation, rhythm math), `niche_dates.py`,
`prompts/calendar_*.md`, tab code kept small; date math and validation are pure functions.

## Testing

Pure-function tests (pillar sum = 100, offer cap, rhythm counts, anchors
placed before fills), mocked AI, deterministic astronomy data tests, tone
banned-word test, AppTest for grid render and accept/skip of niche dates.
One real paid end-to-end run before done.

## Out of scope

Auto-publish; Stories content generation (backlog #4, follows this spec);
Google Calendar sync; multi-profile.

## Open decisions for review

- Astronomy library/dataset choice.
- Whether to ship the list view first and the grid second.
- Export-to-Markdown of a month (backlog #5) — attach here or separate small spec.
