# Calendar ↔ Post Creator Link — Design (Spec 3 of 4)

Depends on Spec 2 (slots) and the existing post creator (Nova Ideia → drafts →
Gerar Imagens → Biblioteca). Status: **drafted without live review — needs user review before tickets.**

## Purpose

Make the tools one workflow: from any calendar slot, create the post with
one click, with the slot's topic, pillar, tone, angle, funnel phase and CTA
already filled in, and have progress flow back to the calendar.

## Flow

1. Slot shows **"Criar este post"**.
2. App creates an `ideas` row (`db.create_idea`) pre-filled from the slot
   (topic, pillar, tone via `ai.suggest_default_tone`) and stores
   `calendar_slots.idea_id`.
3. Post creator opens on that idea; the draft prompt receives extra context:
   angle, funnel phase, goal, CTA keyword, relevant Sherlock writing patterns
   (hook/CTA/structure — abstract patterns, never copied content), and the niche
   date if any. The brand-pack rules and quality gates still apply unchanged.
4. Existing pipeline runs (draft → critique → revise), then images, then approval.
5. Slot status follows the idea: `idea/reviewed → in_production`,
   `approved → ready`, `images_ready → ready`. Publishing stays manual.
6. Rejected/archived ideas return the slot to `planned` with a gentle note
   ("no rush — want a fresh angle for this day?").

## Refinement loop in the creator

Draft results gain a plain-language feedback box ("mais caloroso", "mais curto",
"não sou eu"). AI revises via existing `revise_draft`-style call, with the user's
feedback in the prompt. Accepted tone edits are stored as brand-level tone
preferences so future drafts start closer to the user's voice. All feedback
copy follows the gentle tone rule.

## Changes

- `prompts/` — draft prompt gets optional context block (empty when no slot; existing behavior unchanged).
- `ai.generate_draft(...)` — new optional `context` argument (defaults `None`).
- `pipeline.py` — `create_idea_from_slot(conn, slot)` and `sync_slot_status(conn, idea_id)`.
- `db.py` — `calendar_slots.idea_id` already in Spec 2; add `tone_preferences(brand_pack, note, created_at)`.
- App: button on slot panel; Biblioteca items show their slot date.

## Testing

Existing pipeline tests must pass unchanged; new tests for context-block
rendering (present/absent), slot↔idea status sync in both directions, idempotent
"create post" (second click opens the same idea), and tone-preference storage.
AppTest for the slot → creator hand-off. One real paid end-to-end run.

## Out of scope

Bulk "create all posts of the month" (possible later); auto-publish.

## Open decisions for review

- Whether "create all for the week" is worth a first version.
- How many stored tone preferences to feed into prompts before it gets noisy.
