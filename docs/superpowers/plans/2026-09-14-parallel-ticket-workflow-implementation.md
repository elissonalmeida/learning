# Parallel Ticket Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person split a plan's tasks across multiple independent Claude Code threads, each claiming and working exactly one GitHub-Issue-backed ticket at a time, with dependency tracking, per-ticket worktree isolation, and merge-back regression protection.

**Architecture:** A `plan_parser` module reads a plan file's `### Task N:` sections and each task's `Interfaces` block to build a dependency graph (a Consumes bullet annotated `(Task N)` means "depends on Task N" — see Global Constraints). Three small CLI scripts (`generate_tickets`, `pick_ticket`, `merge_ticket`) wrap the `gh` CLI and `git`/test-runner calls behind an injectable "runner" function each, so all logic is unit-testable without hitting the network or a real repo. A living `docs/superpowers/HANDOFF.md` is the project-level orientation doc a new thread reads first.

**Tech Stack:** Python 3 standard library only (`argparse`, `re`, `json`, `subprocess`, `dataclasses`) — no new dependencies. `pytest` for tests. The `gh` CLI (already authenticated in this environment) and `git` are invoked as external processes, never as libraries.

**Spec:** `docs/superpowers/specs/2026-09-14-parallel-ticket-workflow-design.md`

## Global Constraints

- All new scripts live under `scripts/` at the repo root (`C:\Users\Elisson\Documents\learning\scripts\`) — this tooling applies across every project in the repo, not just `content-creator`.
- **Dependency format requirement (refines the spec's "compare Consumes against Produces" mechanism into something mechanically parseable):** a plan intended for ticket generation must annotate every `- Consumes:` bullet that depends on another task in the *same* plan with `(Task N)`, e.g. `` - Consumes: `image_gen.generate_image(client, prompt) -> (bytes, int, int, float)` (Task 5) ``. This is already how most bullets in this project's existing plans (v1, v1.1) are written. Dependency extraction reads these annotations directly — it does not attempt fuzzy text-matching between Consumes and Produces signatures, which would be far less reliable for the same result.
- Ticket status is tracked with exactly one of these GitHub Issue labels at a time: `status:pending`, `status:blocked`, `status:in-progress`, `status:review`, `status:done`.
- Every function that shells out to `gh` or to `git`/a test command takes an injectable runner parameter (`gh_runner=run_gh`, `shell_runner=run_shell`) defaulting to the real subprocess-based implementation, so tests inject a fake and never touch the network or a real git repo.
- No new external pip dependencies — standard library only for the scripts themselves; `pytest` is a dev-only test dependency.

---

## File Structure

```
learning/                              (repo root)
  docs/
    superpowers/
      HANDOFF.md                       NEW — living project-status doc
  scripts/
    plan_parser.py                     NEW — parses a plan file into Task objects
    generate_tickets.py                NEW — plan file -> GitHub Issues
    pick_ticket.py                     NEW — list/claim next unblocked pending ticket
    merge_ticket.py                    NEW — test, merge, relabel done
    tests/
      test_plan_parser.py              NEW
      test_generate_tickets.py         NEW
      test_pick_ticket.py              NEW
      test_merge_ticket.py             NEW
```

---

### Task 1: `docs/superpowers/HANDOFF.md`

**Files:**
- Create: `docs/superpowers/HANDOFF.md`

**Interfaces:**
- Consumes: none
- Produces: none (this is a documentation artifact, not code)

- [ ] **Step 1: Create the file**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "Add HANDOFF.md as the persistent project-status doc"
```

---

### Task 2: `scripts/plan_parser.py`

**Files:**
- Create: `scripts/plan_parser.py`
- Test: `scripts/tests/test_plan_parser.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `plan_parser.Task` — dataclass with fields `number: int`, `name: str`, `body: str`, `depends_on: list[int]`, `produces: list[str]`
  - `plan_parser.parse_plan(text: str) -> list[Task]`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_plan_parser.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import plan_parser


SAMPLE_PLAN = """
# Sample Implementation Plan

### Task 1: First thing

**Interfaces:**
- Consumes: none
- Produces: `foo.bar(x) -> int`

- [ ] Step 1: do a thing

### Task 2: Second thing

**Interfaces:**
- Consumes: `foo.bar(x) -> int` (Task 1)
- Produces: `foo.baz(y) -> str`

- [ ] Step 1: do another thing

### Task 3: Third thing

**Interfaces:**
- Consumes: `foo.bar(x) -> int` (Task 1), `foo.baz(y) -> str` (Task 2)
- Produces: `foo.qux() -> None`

- [ ] Step 1: do a third thing
"""


def test_parse_plan_extracts_task_numbers_and_names():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert [t.number for t in tasks] == [1, 2, 3]
    assert tasks[0].name == "First thing"
    assert tasks[1].name == "Second thing"
    assert tasks[2].name == "Third thing"


def test_parse_plan_task_with_no_task_references_has_no_dependencies():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[0].depends_on == []


def test_parse_plan_extracts_single_dependency():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[1].depends_on == [1]


def test_parse_plan_extracts_multiple_dependencies_from_one_consumes_line():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[2].depends_on == [1, 2]


def test_parse_plan_extracts_produces_signatures():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[0].produces == ["foo.bar(x) -> int"]
    assert tasks[1].produces == ["foo.baz(y) -> str"]
    assert tasks[2].produces == ["foo.qux() -> None"]


def test_parse_plan_includes_full_task_body():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert "do a thing" in tasks[0].body
    assert "do another thing" not in tasks[0].body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_plan_parser.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'plan_parser'`)

If `pytest` isn't installed: `python3 -m pip install --user pytest` first.

- [ ] **Step 3: Write `scripts/plan_parser.py`**

```python
import re
from dataclasses import dataclass, field


@dataclass
class Task:
    number: int
    name: str
    body: str
    depends_on: list = field(default_factory=list)
    produces: list = field(default_factory=list)


_TASK_HEADER_RE = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_CONSUMES_LINE_RE = re.compile(r"^- Consumes:(.*)$", re.MULTILINE)
_TASK_REF_RE = re.compile(r"\(Task (\d+)\)")
_PRODUCES_RE = re.compile(r"^- Produces:\s*`([^`]+)`", re.MULTILINE)


def parse_plan(text):
    headers = list(_TASK_HEADER_RE.finditer(text))
    tasks = []
    for i, m in enumerate(headers):
        number = int(m.group(1))
        name = m.group(2).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].strip()

        depends_on = set()
        for line_match in _CONSUMES_LINE_RE.finditer(body):
            depends_on.update(int(n) for n in _TASK_REF_RE.findall(line_match.group(1)))

        produces = _PRODUCES_RE.findall(body)

        tasks.append(Task(
            number=number, name=name, body=body,
            depends_on=sorted(depends_on), produces=produces,
        ))
    return tasks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_plan_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/plan_parser.py scripts/tests/test_plan_parser.py
git commit -m "Add plan_parser: parse plan tasks and their Task-N dependencies"
```

---

### Task 3: `scripts/generate_tickets.py`

**Files:**
- Create: `scripts/generate_tickets.py`
- Test: `scripts/tests/test_generate_tickets.py`

**Interfaces:**
- Consumes: `plan_parser.parse_plan(text: str) -> list[Task]` (Task 2), `plan_parser.Task` fields `number`, `name`, `body`, `depends_on` (Task 2)
- Produces:
  - `generate_tickets.run_gh(args: list[str], input_text: str | None = None) -> str`
  - `generate_tickets.create_tickets(tasks: list[Task], repo: str, plan_path: str, gh_runner=run_gh) -> dict[int, int]`
  - `generate_tickets.main(argv: list[str] | None = None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_generate_tickets.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate_tickets
import plan_parser


SAMPLE_PLAN = """
### Task 1: First

**Interfaces:**
- Consumes: none
- Produces: `foo.bar() -> int`

- [ ] Step 1: do it

### Task 2: Second

**Interfaces:**
- Consumes: `foo.bar() -> int` (Task 1)
- Produces: `foo.baz() -> str`

- [ ] Step 1: do it
"""


class FakeGh:
    def __init__(self):
        self.calls = []
        self._next_issue_number = 100

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        if args[:2] == ["issue", "create"]:
            self._next_issue_number += 1
            return f"https://github.com/o/r/issues/{self._next_issue_number}\n"
        return ""


def test_creates_one_issue_per_task():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    fake = FakeGh()
    issue_numbers = generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)
    create_calls = [c for c in fake.calls if c[:2] == ["issue", "create"]]
    assert len(create_calls) == 2
    assert set(issue_numbers.keys()) == {1, 2}


def test_task_with_no_dependencies_is_labeled_pending():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    fake = FakeGh()
    generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)
    first_create = fake.calls[0]
    assert first_create[first_create.index("--label") + 1] == "status:pending"


def test_task_with_dependency_is_labeled_blocked():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    fake = FakeGh()
    generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)
    second_create = fake.calls[1]
    assert second_create[second_create.index("--label") + 1] == "status:blocked"


def test_second_pass_resolves_real_issue_numbers_in_depends_on():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    fake = FakeGh()
    issue_numbers = generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)
    edit_calls = [c for c in fake.calls if c[:2] == ["issue", "edit"]]
    assert len(edit_calls) == 2
    task2_edit = edit_calls[1]
    body = task2_edit[task2_edit.index("--body") + 1]
    assert f"Depends on: #{issue_numbers[1]}" in body


def test_task_with_no_dependencies_gets_depends_on_none():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    fake = FakeGh()
    generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)
    edit_calls = [c for c in fake.calls if c[:2] == ["issue", "edit"]]
    task1_edit = edit_calls[0]
    body = task1_edit[task1_edit.index("--body") + 1]
    assert "Depends on: None" in body


def test_extract_issue_number_parses_url():
    assert generate_tickets._extract_issue_number("https://github.com/o/r/issues/42\n") == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_generate_tickets.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'generate_tickets'`)

- [ ] **Step 3: Write `scripts/generate_tickets.py`**

```python
import argparse
import subprocess
from pathlib import Path

import plan_parser


def run_gh(args, input_text=None):
    result = subprocess.run(
        ["gh"] + args, input=input_text, capture_output=True, text=True, check=True,
    )
    return result.stdout


def build_issue_body(task, plan_path, depends_text):
    return (
        f"{task.body}\n\n"
        f"_From plan: `{plan_path}`_\n\n"
        f"Depends on: {depends_text}"
    )


def _extract_issue_number(gh_output):
    url = gh_output.strip().splitlines()[-1]
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def create_tickets(tasks, repo, plan_path, gh_runner=run_gh):
    """Create one GitHub Issue per task. Returns {task_number: issue_number}.
    Two passes: create every issue first (dependency issue numbers don't
    exist yet), then rewrite each body once every real number is known."""
    issue_numbers = {}
    for task in tasks:
        label = "status:blocked" if task.depends_on else "status:pending"
        body = build_issue_body(task, plan_path, depends_text="(resolving...)")
        out = gh_runner([
            "issue", "create", "--repo", repo,
            "--title", f"Task {task.number}: {task.name}",
            "--body", body,
            "--label", label,
        ])
        issue_numbers[task.number] = _extract_issue_number(out)

    for task in tasks:
        depends_text = (
            ", ".join(f"#{issue_numbers[n]}" for n in task.depends_on)
            if task.depends_on else "None"
        )
        body = build_issue_body(task, plan_path, depends_text)
        gh_runner([
            "issue", "edit", str(issue_numbers[task.number]), "--repo", repo,
            "--body", body,
        ])

    return issue_numbers


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create GitHub issue tickets from a plan file")
    parser.add_argument("plan_path")
    parser.add_argument("--repo", required=True, help="owner/repo")
    args = parser.parse_args(argv)

    text = Path(args.plan_path).read_text(encoding="utf-8")
    tasks = plan_parser.parse_plan(text)
    issue_numbers = create_tickets(tasks, args.repo, args.plan_path)
    for task in tasks:
        print(f"Task {task.number} -> issue #{issue_numbers[task.number]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_generate_tickets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_tickets.py scripts/tests/test_generate_tickets.py
git commit -m "Add generate_tickets: convert a plan's tasks into GitHub Issue tickets"
```

---

### Task 4: `scripts/pick_ticket.py`

**Files:**
- Create: `scripts/pick_ticket.py`
- Test: `scripts/tests/test_pick_ticket.py`

**Interfaces:**
- Consumes: none from earlier tasks (independent CLI; does not import `plan_parser` or `generate_tickets`)
- Produces:
  - `pick_ticket.run_gh(args: list[str], input_text: str | None = None) -> str`
  - `pick_ticket.parse_depends_on(body: str) -> list[int]`
  - `pick_ticket.get_issue_labels(repo: str, issue_number: int, gh_runner=run_gh) -> set[str]`
  - `pick_ticket.is_unblocked(issue: dict, repo: str, gh_runner=run_gh) -> bool`
  - `pick_ticket.list_unblocked_pending(repo: str, gh_runner=run_gh) -> list[dict]`
  - `pick_ticket.claim_ticket(repo: str, issue_number: int, claimant_note: str, gh_runner=run_gh) -> None`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_pick_ticket.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pick_ticket


class FakeGh:
    def __init__(self, view_responses=None):
        self.calls = []
        self.view_responses = view_responses or {}

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        if args[:2] == ["issue", "view"]:
            return self.view_responses[args[2]]
        return ""


def test_parse_depends_on_extracts_issue_numbers():
    assert pick_ticket.parse_depends_on("blah\nDepends on: #10, #11\n") == [10, 11]


def test_parse_depends_on_returns_empty_for_none():
    assert pick_ticket.parse_depends_on("Depends on: None") == []


def test_get_issue_labels_returns_label_names():
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:done"}]})})
    assert pick_ticket.get_issue_labels("o/r", 10, gh_runner=fake) == {"status:done"}


def test_is_unblocked_true_when_all_deps_done():
    issue = {"number": 5, "body": "Depends on: #10"}
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:done"}]})})
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is True


def test_is_unblocked_false_when_a_dep_is_not_done():
    issue = {"number": 5, "body": "Depends on: #10"}
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:in-progress"}]})})
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is False


def test_is_unblocked_true_when_no_dependencies():
    issue = {"number": 5, "body": "Depends on: None"}
    fake = FakeGh()
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is True


def test_claim_ticket_relabels_and_comments():
    fake = FakeGh()
    pick_ticket.claim_ticket("o/r", 7, "thread A", gh_runner=fake)
    edit_call = fake.calls[0]
    assert edit_call[:4] == ["issue", "edit", "7", "--repo"]
    assert "--add-label" in edit_call
    assert edit_call[edit_call.index("--add-label") + 1] == "status:in-progress"
    comment_call = fake.calls[1]
    assert comment_call[:2] == ["issue", "comment"]
    assert "thread A" in comment_call[comment_call.index("--body") + 1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_pick_ticket.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'pick_ticket'`)

- [ ] **Step 3: Write `scripts/pick_ticket.py`**

```python
import argparse
import json
import re
import subprocess


def run_gh(args, input_text=None):
    result = subprocess.run(
        ["gh"] + args, input=input_text, capture_output=True, text=True, check=True,
    )
    return result.stdout


_DEPENDS_RE = re.compile(r"Depends on:\s*(.+)")
_ISSUE_REF_RE = re.compile(r"#(\d+)")


def parse_depends_on(body):
    m = _DEPENDS_RE.search(body)
    if not m or m.group(1).strip().lower().startswith("none"):
        return []
    return [int(n) for n in _ISSUE_REF_RE.findall(m.group(1))]


def list_pending_issues(repo, gh_runner=run_gh):
    out = gh_runner([
        "issue", "list", "--repo", repo, "--label", "status:pending",
        "--json", "number,title,body", "--state", "open",
    ])
    return json.loads(out)


def get_issue_labels(repo, issue_number, gh_runner=run_gh):
    out = gh_runner(["issue", "view", str(issue_number), "--repo", repo, "--json", "labels"])
    data = json.loads(out)
    return {label["name"] for label in data["labels"]}


def is_unblocked(issue, repo, gh_runner=run_gh):
    for dep_number in parse_depends_on(issue["body"]):
        if "status:done" not in get_issue_labels(repo, dep_number, gh_runner=gh_runner):
            return False
    return True


def list_unblocked_pending(repo, gh_runner=run_gh):
    pending = list_pending_issues(repo, gh_runner=gh_runner)
    return [issue for issue in pending if is_unblocked(issue, repo, gh_runner=gh_runner)]


def claim_ticket(repo, issue_number, claimant_note, gh_runner=run_gh):
    gh_runner([
        "issue", "edit", str(issue_number), "--repo", repo,
        "--remove-label", "status:pending", "--add-label", "status:in-progress",
    ])
    gh_runner([
        "issue", "comment", str(issue_number), "--repo", repo,
        "--body", f"Claimed: {claimant_note}",
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description="List or claim the next unblocked, pending ticket")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--claim", type=int, metavar="ISSUE_NUMBER", help="Claim this specific issue number")
    parser.add_argument("--note", default="thread session", help="Note recorded in the claim comment")
    args = parser.parse_args(argv)

    if args.claim:
        claim_ticket(args.repo, args.claim, args.note)
        print(f"Claimed issue #{args.claim}")
        return

    unblocked = list_unblocked_pending(args.repo)
    if not unblocked:
        print("No unblocked, pending tickets available.")
        return
    for issue in unblocked:
        print(f"#{issue['number']}: {issue['title']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_pick_ticket.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/pick_ticket.py scripts/tests/test_pick_ticket.py
git commit -m "Add pick_ticket: list and claim exactly one unblocked pending ticket"
```

---

### Task 5: `scripts/merge_ticket.py`

**Files:**
- Create: `scripts/merge_ticket.py`
- Test: `scripts/tests/test_merge_ticket.py`

**Interfaces:**
- Consumes: none from earlier tasks (independent CLI; does not import `plan_parser`, `generate_tickets`, or `pick_ticket`)
- Produces:
  - `merge_ticket.run_gh(args: list[str], input_text: str | None = None) -> str`
  - `merge_ticket.run_shell(args: list[str], cwd=None) -> tuple[int, str, str]`
  - `merge_ticket.run_test_suite(project_dir, test_command: list[str], shell_runner=run_shell) -> tuple[bool, str]`
  - `merge_ticket.merge_branch(project_dir, feature_branch: str, ticket_branch: str, shell_runner=run_shell) -> tuple[bool, str]`
  - `merge_ticket.mark_done(repo: str, issue_number: int, commit_range: str, gh_runner=run_gh) -> None`
  - `merge_ticket.merge_ticket(project_dir, repo, issue_number, feature_branch, ticket_branch, test_command, commit_range, gh_runner=run_gh, shell_runner=run_shell) -> tuple[bool, str]`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_merge_ticket.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import merge_ticket


class FakeShell:
    def __init__(self, test_result=(0, "ok", ""), merge_result=(0, "merged", "")):
        self.calls = []
        self.test_result = test_result
        self.merge_result = merge_result

    def __call__(self, args, cwd=None):
        self.calls.append((args, cwd))
        if args[0] == "git" and args[1] == "merge":
            return self.merge_result
        return self.test_result


class FakeGh:
    def __init__(self):
        self.calls = []

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        return ""


def test_merge_ticket_succeeds_when_tests_and_merge_pass():
    shell = FakeShell()
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is True
    assert any(c[:2] == ["issue", "edit"] for c in gh.calls)


def test_merge_ticket_aborts_when_tests_fail():
    shell = FakeShell(test_result=(1, "", "1 failed"))
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is False
    assert "Test suite failed" in message
    assert gh.calls == []


def test_merge_ticket_aborts_when_merge_fails():
    shell = FakeShell(merge_result=(1, "", "conflict"))
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is False
    assert "Merge failed" in message
    assert gh.calls == []


def test_mark_done_relabels_and_comments():
    gh = FakeGh()
    merge_ticket.mark_done("o/r", 5, "abc..def", gh_runner=gh)
    edit_call = gh.calls[0]
    assert "--add-label" in edit_call
    assert edit_call[edit_call.index("--add-label") + 1] == "status:done"
    comment_call = gh.calls[1]
    assert "abc..def" in comment_call[comment_call.index("--body") + 1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_merge_ticket.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'merge_ticket'`)

- [ ] **Step 3: Write `scripts/merge_ticket.py`**

```python
import argparse
import subprocess


def run_gh(args, input_text=None):
    result = subprocess.run(
        ["gh"] + args, input=input_text, capture_output=True, text=True, check=True,
    )
    return result.stdout


def run_shell(args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def run_test_suite(project_dir, test_command, shell_runner=run_shell):
    returncode, stdout, stderr = shell_runner(test_command, cwd=project_dir)
    return returncode == 0, stdout + stderr


def merge_branch(project_dir, feature_branch, ticket_branch, shell_runner=run_shell):
    returncode, stdout, stderr = shell_runner(
        ["git", "merge", "--no-edit", ticket_branch], cwd=project_dir,
    )
    return returncode == 0, stdout + stderr


def mark_done(repo, issue_number, commit_range, gh_runner=run_gh):
    gh_runner([
        "issue", "edit", str(issue_number), "--repo", repo,
        "--remove-label", "status:review", "--remove-label", "status:in-progress",
        "--add-label", "status:done",
    ])
    gh_runner([
        "issue", "comment", str(issue_number), "--repo", repo,
        "--body", f"Merged: {commit_range}",
    ])


def merge_ticket(
    project_dir, repo, issue_number, feature_branch, ticket_branch, test_command,
    commit_range, gh_runner=run_gh, shell_runner=run_shell,
):
    """Run the full test suite, then merge the ticket branch, then mark the
    issue done. Returns (success, message). Never touches the issue or
    merges if the test suite fails first."""
    tests_ok, test_output = run_test_suite(project_dir, test_command, shell_runner=shell_runner)
    if not tests_ok:
        return False, f"Test suite failed, merge aborted:\n{test_output}"

    merged_ok, merge_output = merge_branch(project_dir, feature_branch, ticket_branch, shell_runner=shell_runner)
    if not merged_ok:
        return False, f"Merge failed:\n{merge_output}"

    mark_done(repo, issue_number, commit_range, gh_runner=gh_runner)
    return True, "Merged and marked done."


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run tests, merge a ticket branch, and mark its issue done")
    parser.add_argument("project_dir")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--feature-branch", required=True)
    parser.add_argument("--ticket-branch", required=True)
    parser.add_argument("--test-command", required=True, help="e.g. 'python3 -m pytest -q'")
    parser.add_argument("--commit-range", required=True)
    args = parser.parse_args(argv)

    ok, message = merge_ticket(
        args.project_dir, args.repo, args.issue, args.feature_branch,
        args.ticket_branch, args.test_command.split(), args.commit_range,
    )
    print(message)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/test_merge_ticket.py -v`
Expected: PASS

- [ ] **Step 5: Run the full new test suite together, then commit**

Run: `cd C:\Users\Elisson\Documents\learning && python3 -m pytest scripts/tests/ -v`
Expected: PASS (all tests from Tasks 2-5)

```bash
git add scripts/merge_ticket.py scripts/tests/test_merge_ticket.py
git commit -m "Add merge_ticket: test, merge, and mark a ticket done"
```

---

## Self-Review Notes

- **Spec coverage:** ticket lifecycle labels (Task 4, `pick_ticket`), ticket generation from a plan with dependency links (Task 3, `generate_tickets`, backed by Task 2's parsing), the pick-up flow's claim step (Task 4's `claim_ticket`), merge-back regression protection via full test suite before merge (Task 5's `run_test_suite` gating `merge_branch`), and `HANDOFF.md` (Task 1) are all covered. The spec's per-ticket git-worktree isolation and the interface-overlap re-test are deliberately left to the existing `superpowers:using-git-worktrees` skill and to human/thread judgment at merge time respectively — building bespoke tooling for either would be premature machinery for a solo-operator workflow, matching the spec's own "deliberately not solve" section.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code.
- **Type consistency:** `Task.depends_on` (Task 2) is `list[int]` everywhere it's consumed (Task 3's `create_tickets` iterates `task.depends_on` expecting ints, matching). `gh_runner`/`shell_runner` signatures are consistent across all three CLI scripts (`(args, input_text=None) -> str` and `(args, cwd=None) -> (int, str, str)` respectively) even though the scripts don't share code — deliberate, since Task 4 and Task 5 are independent CLIs with no cross-task Consumes relationship to each other.
