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
