import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate_tickets
import pick_ticket
import plan_parser


VALID_STATUS_LABELS = {
    "status:pending",
    "status:blocked",
    "status:in-progress",
    "status:review",
    "status:done",
}

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


def test_build_issue_body_round_trips_through_parse_depends_on():
    task = plan_parser.parse_plan(SAMPLE_PLAN)[1]
    body = generate_tickets.build_issue_body(task, "plan.md", depends_text="#101, #102")
    assert pick_ticket.parse_depends_on(body) == [101, 102]


def test_build_issue_body_round_trips_none():
    task = plan_parser.parse_plan(SAMPLE_PLAN)[0]
    body = generate_tickets.build_issue_body(task, "plan.md", depends_text="None")
    assert pick_ticket.parse_depends_on(body) == []


class FakeGh:
    """Records every gh_runner call and returns plausible responses for
    create_tickets, list_unblocked_pending, and claim_ticket so all three
    can be exercised against the real modules end-to-end."""

    def __init__(self):
        self.calls = []
        self._next_issue_number = 100
        self.labels_by_issue = {}

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        if args[:2] == ["issue", "create"]:
            self._next_issue_number += 1
            number = self._next_issue_number
            label = args[args.index("--label") + 1]
            self.labels_by_issue[number] = label
            return f"https://github.com/o/r/issues/{number}\n"
        if args[:2] == ["issue", "edit"]:
            number = int(args[2])
            if "--add-label" in args:
                self.labels_by_issue[number] = args[args.index("--add-label") + 1]
            return ""
        if args[:2] == ["issue", "list"]:
            label = args[args.index("--label") + 1]
            issues = [
                {"number": n, "title": f"Task {n}", "body": "<!-- depends-on: None -->"}
                for n, lbl in self.labels_by_issue.items() if lbl == label
            ]
            return json.dumps(issues)
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            return json.dumps({"labels": [{"name": self.labels_by_issue[number]}]})
        return ""


def test_only_the_five_status_labels_are_ever_used_across_create_pick_and_claim():
    fake = FakeGh()
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    generate_tickets.create_tickets(tasks, "o/r", "plan.md", gh_runner=fake)

    pick_ticket.list_unblocked_pending("o/r", gh_runner=fake)

    # Claim the first pending issue found via create_tickets (task 1, no deps).
    pending_issue_number = next(
        n for n, lbl in fake.labels_by_issue.items() if lbl == "status:pending"
    )
    pick_ticket.claim_ticket("o/r", pending_issue_number, "thread A", gh_runner=fake)

    label_flags = {"--label", "--add-label", "--remove-label"}
    used_labels = set()
    for call in fake.calls:
        for i, token in enumerate(call):
            if token in label_flags and i + 1 < len(call):
                used_labels.add(call[i + 1])

    assert used_labels, "expected at least one label to have been used"
    assert used_labels <= VALID_STATUS_LABELS
