import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import merge_ticket


class FakeShell:
    def __init__(self, branch="feature", test_result=(0, "ok", ""), merge_result=(0, "merged", "")):
        self.calls = []
        self.branch = branch
        self.test_result = test_result
        self.merge_result = merge_result

    def __call__(self, args, cwd=None):
        self.calls.append((args, cwd))
        if args[:2] == ["git", "rev-parse"]:
            return (0, self.branch, "")
        if args[:2] == ["git", "merge"]:
            return self.merge_result
        return self.test_result


class FakeGh:
    def __init__(self, raise_on_edit=False):
        self.calls = []
        self.raise_on_edit = raise_on_edit

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        if self.raise_on_edit and args[:2] == ["issue", "edit"]:
            raise subprocess.CalledProcessError(1, ["gh"] + args, output="", stderr="boom")
        return ""


def test_merge_ticket_succeeds_when_merge_and_tests_pass():
    shell = FakeShell()
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is True
    assert any(c[:2] == ["issue", "edit"] for c in gh.calls)


def test_merge_ticket_runs_tests_after_merging_not_before():
    shell = FakeShell()
    gh = FakeGh()
    merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    merge_index = next(i for i, (args, _) in enumerate(shell.calls) if args[:2] == ["git", "merge"])
    test_index = next(i for i, (args, _) in enumerate(shell.calls) if args == ["pytest"])
    assert merge_index < test_index


def test_merge_ticket_aborts_when_branch_mismatch():
    shell = FakeShell(branch="some-other-branch")
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is False
    assert "some-other-branch" in message
    assert gh.calls == []
    assert not any(c[:2] == ["git", "merge"] for c, _ in shell.calls)


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


def test_merge_ticket_rolls_back_when_tests_fail_after_merge():
    shell = FakeShell(test_result=(1, "", "1 failed"))
    gh = FakeGh()
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is False
    assert "Test suite failed" in message
    assert gh.calls == []
    assert any(args[:3] == ["git", "reset", "--hard"] for args, _ in shell.calls)


def test_mark_done_relabels_and_comments():
    gh = FakeGh()
    merge_ticket.mark_done("o/r", 5, "abc..def", gh_runner=gh)
    edit_call = gh.calls[0]
    assert "--add-label" in edit_call
    assert edit_call[edit_call.index("--add-label") + 1] == "status:done"
    comment_call = gh.calls[1]
    assert "abc..def" in comment_call[comment_call.index("--body") + 1]


def test_merge_ticket_succeeds_overall_when_mark_done_fails():
    shell = FakeShell()
    gh = FakeGh(raise_on_edit=True)
    ok, message = merge_ticket.merge_ticket(
        "/proj", "o/r", 5, "feature", "ticket-5", ["pytest"], "abc..def",
        gh_runner=gh, shell_runner=shell,
    )
    assert ok is True
    assert "#5" in message
    assert "boom" in message
