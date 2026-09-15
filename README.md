# learning

A repo hosting multiple independent projects, developed with Claude Code using Subagent-Driven Development (SDD) and a GitHub-Issues-backed parallel ticket workflow.

## Projects

- **[content-creator](content-creator/)** — AI-assisted Instagram content pipeline (idea → draft → critique → approved carousel/images) for the `marianabotelho-ig` brand. See `content-creator/docs/` for its spec, decisions log, and backlog.

## Working guidelines

Project-wide conventions (think-before-coding, simplicity, surgical changes, goal-driven execution) live in [CLAUDE.md](CLAUDE.md) and apply to all work in this repo.

## Parallel ticket workflow

Plans are normally executed by a single Claude Code thread using `subagent-driven-development` (fresh subagent per task, review after each, final whole-branch review). When a plan is large enough to benefit from splitting across multiple threads/sessions, this repo also has a **ticket workflow**: each plan task becomes a GitHub Issue ("ticket") carrying its own dependency and status metadata, so independent threads can each claim and work exactly one ticket at a time without colliding.

- **Design spec:** [`docs/superpowers/specs/2026-09-14-parallel-ticket-workflow-design.md`](docs/superpowers/specs/2026-09-14-parallel-ticket-workflow-design.md)
- **Implementation plan:** [`docs/superpowers/plans/2026-09-14-parallel-ticket-workflow-implementation.md`](docs/superpowers/plans/2026-09-14-parallel-ticket-workflow-implementation.md)
- **Tooling:** [`scripts/`](scripts/) — `plan_parser.py`, `generate_tickets.py`, `pick_ticket.py`, `merge_ticket.py`, with tests in `scripts/tests/`.

### Ticket lifecycle

Each ticket (GitHub Issue) carries exactly one status label at a time:

`status:pending` → `status:blocked` → `status:in-progress` → `status:review` → `status:done`

### How it works, end to end

1. Write and approve a plan as usual (`superpowers:writing-plans`).
2. Generate tickets from the plan: `python scripts/generate_tickets.py <plan-file> --repo <owner/repo>`. This opens one GitHub Issue per task, labeled `status:pending` or `status:blocked` based on its `Depends on` list.
3. A person starts a new thread and picks up exactly **one** ticket: `python scripts/pick_ticket.py --repo <owner/repo> --claim <issue-number>` (or without `--claim` to just list unblocked pending tickets). The thread creates a dedicated git worktree/branch for that ticket (`superpowers:using-git-worktrees`, `ticket-<issue-number>` naming), then runs the normal implementer → task-review → fix-loop flow scoped to that one task.
4. On a clean task review, merge back: `python scripts/merge_ticket.py --repo <owner/repo> --issue <issue-number> --feature-branch <branch> --test-command "<command>"`. This runs the full test suite against the merged tree and rolls back if it fails, then relabels the issue `status:done`.
5. **The thread stops.** It never auto-picks the next ticket — starting another one (same thread or a new one) is always a separate, deliberate action by the person.
6. Once every ticket for a plan is `status:done`, run the plan's final whole-branch review as usual before merging the feature branch to `main`.

### Why

- Keeps each thread's context window small and bounded to one task.
- Lets a person work on more than one ticket "in flight" (across threads) without them stepping on each other's files.
- Preserves the safety properties of single-session SDD: per-task review, a stop after every task, and a mandatory final cross-task review before shipping.

See the design spec for what this deliberately does *not* solve (true distributed locking, automated test-impact analysis) and why.

### Orientation for a new thread

Read [`docs/superpowers/HANDOFF.md`](docs/superpowers/HANDOFF.md) first — it's the always-current, repo-committed status doc: what's active, what's next, and how to resume, kept up to date at the end of every thread's work session.
