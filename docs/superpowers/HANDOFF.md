# Handoff

Read this first if you're a new thread picking up work in this repo. This
file is always kept current — it is not a log; see `docs/decisions.md` (per
project) for history.

## Where things stand

- **content-creator** (`content-creator/`): v1 (text drafting pipeline) and
  v1.1 (AI image generation for carousel slides) are both shipped, merged to
  `main`, and working end-to-end against the real Gemini/Anthropic APIs.
- **Parallel ticket workflow** (this doc, plus `scripts/`): being built now,
  from `docs/superpowers/specs/2026-09-14-parallel-ticket-workflow-design.md`
  and `docs/superpowers/plans/2026-09-14-parallel-ticket-workflow-implementation.md`.

## What's next

Check the plan above for remaining tasks. Once this workflow itself is
built, the next real feature work is picked from
`content-creator/docs/backlog.md` — notably, decomposing the "full AURA
functionality" vision into its own sub-project specs (calendar first, per
the backlog's own note).

## How to resume

1. Read this file.
2. If a plan for the current work already has a `docs/superpowers/plans/*.md`
   file, read it and check for open tasks (checkboxes not yet ticked, or
   GitHub Issues not yet `status:done` if tickets have been generated for it).
3. If no plan exists yet for what you're being asked to do, invoke
   `superpowers:brainstorming` first — do not start writing code.
4. To generate tickets from an approved plan: `python3 scripts/generate_tickets.py <plan-path> --repo <owner/repo>`.
5. To pick up one ticket: `python3 scripts/pick_ticket.py --repo <owner/repo>` to see unblocked
   options, then `--claim <issue-number>` to claim exactly one. Work that one
   ticket via `superpowers:subagent-driven-development`, then stop — do not
   claim another ticket in the same invocation. Starting the next one is
   always a separate, deliberate action.
6. To merge a finished ticket back: `python3 scripts/merge_ticket.py <project-dir> --repo <owner/repo> --issue <n> --feature-branch <name> --ticket-branch <name> --test-command "<command>" --commit-range <a..b>`.

## Standing conventions a new thread needs

- **Brand-agnostic engine / brand-pack pattern** (content-creator): engine
  code never contains brand-specific text; brand knowledge lives in
  `content-creator/brands/<pack>/*.md`.
- **PT-PT only** for all content-creator user-facing and generated text.
- **Cost-conscious AI calls**: every AI-calling function checks a daily
  spend cap before calling (`db.would_exceed_daily_cap`) and logs real
  cost after.
- **No AI-generated text baked into images**: text is always composited
  afterward via templates, never rendered by an image model.
- **One real, paid, end-to-end test before calling an AI-calling feature
  done.** No amount of mocked-test coverage substitutes for this — see
  `content-creator/docs/decisions.md` for three real bugs mocks missed.
- **Working guidelines**: see `CLAUDE.md` at the repo root (think before
  coding, simplicity first, surgical changes, goal-driven execution).

## Links, not copies

- `content-creator/docs/decisions.md` — why things are the way they are.
- `content-creator/docs/backlog.md` — deferred ideas, not forgotten.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` (repo root, and
  `content-creator/docs/superpowers/` for that project's own specs/plans).
