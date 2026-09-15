import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import pick_ticket


class FakeGh:
    def __init__(self, view_responses=None, list_responses=None):
        self.calls = []
        self.view_responses = view_responses or {}
        self.list_responses = list_responses or {}

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        if args[:2] == ["issue", "view"]:
            return self.view_responses[args[2]]
        if args[:2] == ["issue", "list"]:
            label = args[args.index("--label") + 1]
            return json.dumps(self.list_responses.get(label, []))
        return ""


def test_parse_depends_on_extracts_issue_numbers():
    body = "blah\nDepends on: #10, #11\n<!-- depends-on: #10, #11 -->"
    assert pick_ticket.parse_depends_on(body) == [10, 11]


def test_parse_depends_on_returns_empty_for_none():
    assert pick_ticket.parse_depends_on("Depends on: None\n<!-- depends-on: None -->") == []


def test_parse_depends_on_ignores_lookalike_text_in_task_body():
    # Regression: the real marker must win even if the task's own prose
    # contains text that looks like a (fake) Depends on line earlier in
    # the body, e.g. quoted example text or a test fixture string.
    body = (
        "Here's an example ticket body:\n"
        "Depends on: #999\n\n"
        "_From plan: `plan.md`_\n\n"
        "Depends on: #10, #11\n"
        "<!-- depends-on: #10, #11 -->"
    )
    assert pick_ticket.parse_depends_on(body) == [10, 11]


def test_get_issue_labels_returns_label_names():
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:done"}]})})
    assert pick_ticket.get_issue_labels("o/r", 10, gh_runner=fake) == {"status:done"}


def test_is_unblocked_true_when_all_deps_done():
    issue = {"number": 5, "body": "<!-- depends-on: #10 -->"}
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:done"}]})})
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is True


def test_is_unblocked_false_when_a_dep_is_not_done():
    issue = {"number": 5, "body": "<!-- depends-on: #10 -->"}
    fake = FakeGh(view_responses={"10": json.dumps({"labels": [{"name": "status:in-progress"}]})})
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is False


def test_is_unblocked_true_when_no_dependencies():
    issue = {"number": 5, "body": "<!-- depends-on: None -->"}
    fake = FakeGh()
    assert pick_ticket.is_unblocked(issue, "o/r", gh_runner=fake) is True


def test_list_unblocked_pending_includes_blocked_issue_whose_dep_is_now_done():
    # Regression: status:blocked is not a dead end. Once its dependency
    # merges (status:done), the blocked issue must show up as claimable.
    blocked_issue = {"number": 20, "title": "Blocked task", "body": "<!-- depends-on: #10 -->"}
    fake = FakeGh(
        list_responses={
            "status:pending": [],
            "status:blocked": [blocked_issue],
        },
        view_responses={"10": json.dumps({"labels": [{"name": "status:done"}]})},
    )
    result = pick_ticket.list_unblocked_pending("o/r", gh_runner=fake)
    assert result == [blocked_issue]


def test_list_unblocked_pending_excludes_still_blocked_issue():
    blocked_issue = {"number": 20, "title": "Blocked task", "body": "<!-- depends-on: #10 -->"}
    fake = FakeGh(
        list_responses={
            "status:pending": [],
            "status:blocked": [blocked_issue],
        },
        view_responses={"10": json.dumps({"labels": [{"name": "status:in-progress"}]})},
    )
    assert pick_ticket.list_unblocked_pending("o/r", gh_runner=fake) == []


def test_claim_ticket_relabels_and_comments():
    fake = FakeGh(view_responses={"7": json.dumps({"labels": [{"name": "status:pending"}]})})
    pick_ticket.claim_ticket("o/r", 7, "thread A", gh_runner=fake)
    edit_call = fake.calls[1]
    assert edit_call[:4] == ["issue", "edit", "7", "--repo"]
    assert "--add-label" in edit_call
    assert edit_call[edit_call.index("--add-label") + 1] == "status:in-progress"
    comment_call = fake.calls[2]
    assert comment_call[:2] == ["issue", "comment"]
    assert "thread A" in comment_call[comment_call.index("--body") + 1]


def test_claim_ticket_removes_blocked_label_when_that_is_the_one_present():
    fake = FakeGh(view_responses={"7": json.dumps({"labels": [{"name": "status:blocked"}]})})
    pick_ticket.claim_ticket("o/r", 7, "thread A", gh_runner=fake)
    edit_call = fake.calls[1]
    assert "--remove-label" in edit_call
    assert edit_call[edit_call.index("--remove-label") + 1] == "status:blocked"


def test_claim_ticket_does_not_proceed_if_already_claimed():
    fake = FakeGh(view_responses={"7": json.dumps({"labels": [{"name": "status:in-progress"}]})})
    with pytest.raises(pick_ticket.TicketNotAvailable):
        pick_ticket.claim_ticket("o/r", 7, "thread A", gh_runner=fake)
    assert not any(c[:2] == ["issue", "edit"] for c in fake.calls)
    assert not any(c[:2] == ["issue", "comment"] for c in fake.calls)
