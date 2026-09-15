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
