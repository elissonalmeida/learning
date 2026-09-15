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
