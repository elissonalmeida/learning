# Handoff

Read this first if you're a new thread picking up work in this repo. This
file is always kept current — it is not a log; see `docs/decisions.md` (per
project) for history.

## Where things stand

- **content-creator** (`content-creator/`): v1 (text drafting pipeline) and
  v1.1 (AI image generation for carousel slides) are both shipped, merged to
  `main`, and working end-to-end against the real Gemini/Anthropic APIs.
- **Parallel ticket workflow**: built; `status:*` labels exist on
  `elissonalmeida/learning`.
- **All planned work is broken into GitHub tickets** (labels `status:*`).
  Done (`status:done`): #13 (look-and-feel theme); #16-#20, #23 (strategy-coach:
  tone guard, coach store, Sherlock gather, goal scoring); and the 2026-09-26 fix pass:
  #46 (readable slide card/hero renderer), #47 ("Ver maior" dialog with Fechar), #48
  ("Gerar todas as imagens" / "Recriar todas" / per-slide "Recriar", spend-cap aware,
  paid-tested), #49 (Instagram-style carousel preview), #50-#52 (draft lost on reload,
  Gemini returning no image, screens not refreshing). Everything else is still specs,
  plans and tickets:

  | Plan (`content-creator/docs/superpowers/plans/`) | Old feature branch (merged, retired) | Tickets |
  |---|---|---|
  | `2026-09-15-look-and-feel.md` | `look-and-feel` | #13-#15 |
  | `2026-09-25-strategy-coach.md` (includes Sherlock) | `strategy-coach` | #16-#25 |
  | `2026-09-25-content-calendar.md` | `content-calendar` | #26-#32 |
  | `2026-09-25-calendar-post-link.md` | `calendar-post-link` | #33-#36 |
  | `2026-09-25-windsor-results.md` | `windsor-results` | #37-#45 |

  Specs live in `content-creator/docs/superpowers/specs/` (the four
  `2026-09-25-*` specs were drafted without live review and got one
  decisions pass on 2026-09-25).

## What's next

- **Fix pass finished (2026-09-26):** every user-reported bug/feature (#46-#52) is merged,
  reviewed and pushed; the app was checked on a copy of the real DB. Next is regular ticket
  work. Pending right now: #26, #27 (content-calendar), #33 (calendar-post-link), #37, #38,
  #40 (windsor-results). #14, #15, #21 carry `status:blocked` although their listed deps
  look done: check with `pick_ticket.py` / the issue's `Depends on:` before unblocking.
  #25 is correctly blocked (it was wrongly marked done once and reverted).
- Parked from the #48 review: after "Recriar todas" an idea keeps status `images_ready`
  while its new images wait for approval (same as the old per-slide regenerate). Harmless
  today; revisit before any publish step relies on `images_ready`.
- **Single-branch workflow (since 2026-09-25):** ALL work lives on `main`. The five
  feature branches (`look-and-feel`, `strategy-coach`, `content-calendar`,
  `calendar-post-link`, `windsor-results`) were merged into `main` and are retired; do not
  branch from or merge into them. No PRs. Ticket branches (`ticket-<n>`) are cut from `main`
  in a worktree under `../learning-worktrees/` and merged back with
  `merge_ticket.py ... --feature-branch main`.
- **Keep the main folder (`Documents/learning`) on `main`.** The user runs the app from it
  (`content-creator/run.bat`); never check out other branches in it. Use worktrees. Check
  `ListAgents` for other Claude sessions before touching shared state.
- Note: strategy-coach and look-and-feel were merged **without** their final whole-branch
  reviews. Do a whole-`main` review before shipping a coach or theme change to users.
- Claim tickets with `pick_ticket.py` (it only lists unblocked ones; never
  claim a `status:blocked` ticket by number). One ticket per thread.
- Ticket dependencies (`Depends on: #N`) still gate order; the old cross-plan
  "wait for the other plan to be merged" rule is moot now that everything is on `main`.
- Guard: `scripts/tests/test_encoding.py` keeps the Windows UTF-8 fix in the ticket scripts.
- Tickets modify `app.py` in small, separate spots; expect trivial merge
  conflicts there and in `requirements.txt`, resolve by keeping both sides.
- Product tone rule: all app text gentle and encouraging, never urgent
  (`content-creator/tone_guard.py` once built).
- Windsor field names in `windsor.py` must be verified against the real
  connector (windsor-results Task 1, Step 1).

## One-time setup per repo

Before generating tickets in a target repo for the first time, create the
five status labels the workflow relies on (only needed once per repo —
`gh issue create`/`gh issue edit` fail with a raw traceback if a label
doesn't exist yet):

```
gh label create status:pending --repo <owner/repo> --color ededed
gh label create status:blocked --repo <owner/repo> --color d93f0b
gh label create status:in-progress --repo <owner/repo> --color fbca04
gh label create status:review --repo <owner/repo> --color 0e8a16
gh label create status:done --repo <owner/repo> --color 5319e7
```

## How to resume

1. Read this file.
2. If a plan for the current work already has a `docs/superpowers/plans/*.md`
   file, read it and check for open tasks (checkboxes not yet ticked, or
   GitHub Issues not yet `status:done` if tickets have been generated for it).
3. If no plan exists yet for what you're being asked to do, invoke
   `superpowers:brainstorming` first — do not start writing code.
4. To generate tickets from an approved plan: `python3 scripts/generate_tickets.py <plan-path> --repo <owner/repo>`.
5. To pick up one ticket: `python3 scripts/pick_ticket.py --repo <owner/repo>` to see unblocked
   options, then `python3 scripts/pick_ticket.py --repo <owner/repo> --claim <issue-number>` to
   claim exactly one. Work that one ticket via
   `superpowers:subagent-driven-development`, then stop — do not claim
   another ticket in the same invocation. Starting the next one is always a
   separate, deliberate action.
6. Before starting work on the claimed ticket, create its isolated
   worktree/branch via `superpowers:using-git-worktrees`, off `main` (the plan's
   old feature branch is retired). Convention: name the branch (and worktree) after the
   issue number, e.g. `ticket-<issue-number>`.
7. To merge a finished ticket back: `python3 scripts/merge_ticket.py <project-dir> --repo <owner/repo> --issue <n> --feature-branch <name> --ticket-branch <name> --test-command "<command>" --commit-range <a..b>`.
8. Before stopping work, update this file (`docs/superpowers/HANDOFF.md`) to
   reflect what's now done and what's next — it is read first by the next
   thread and must stay current.

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

## Notes for upcoming Sherlock tickets

- `sherlock.gather.gather_website` needs a scheme: prepend `https://` to scheme-less
  URLs before calling it (detect_platform classes `www.x.pt` as website but the
  fetch fails without a scheme). Raised in the #18 review.
- `sherlock.gather.gather_video` takes `transcribe=None`: the orchestrator (#22) must pass
  `transcribe=gather.whisper_transcribe` if it wants whisper transcripts.
- `gather_instagram_discovery(source, ig_user_id, access_token)` uses Graph `GRAPH_VERSION = "v21.0"`;
  Meta's docs now show v25.0. Bump when doing the real end-to-end test (needs a Business/Creator
  account and token; without them it returns `NeedsUpload`).
