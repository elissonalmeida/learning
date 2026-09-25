import argparse
import json
import re
import subprocess


def run_gh(args, input_text=None):
    result = subprocess.run(
        ["gh"] + args, input=input_text, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return result.stdout


_DEPENDS_RE = re.compile(r"<!-- depends-on:\s*(.+?)\s*-->")
_ISSUE_REF_RE = re.compile(r"#(\d+)")


def parse_depends_on(body):
    m = _DEPENDS_RE.search(body)
    if not m or m.group(1).strip().lower().startswith("none"):
        return []
    return [int(n) for n in _ISSUE_REF_RE.findall(m.group(1))]


CLAIMABLE_LABELS = ("status:pending", "status:blocked")


class TicketNotAvailable(Exception):
    """Raised when a ticket is no longer pending/blocked (already claimed or done)."""


def list_issues_by_label(repo, label, gh_runner=run_gh):
    out = gh_runner([
        "issue", "list", "--repo", repo, "--label", label,
        "--json", "number,title,body", "--state", "open",
    ])
    return json.loads(out)


def list_pending_issues(repo, gh_runner=run_gh):
    return list_issues_by_label(repo, "status:pending", gh_runner=gh_runner)


def list_pending_and_blocked_issues(repo, gh_runner=run_gh):
    """gh issue list combines multiple --label flags with AND, not OR, so
    querying pending-or-blocked takes two calls, combined and de-duplicated
    by issue number."""
    combined = []
    seen = set()
    for label in CLAIMABLE_LABELS:
        for issue in list_issues_by_label(repo, label, gh_runner=gh_runner):
            if issue["number"] not in seen:
                combined.append(issue)
                seen.add(issue["number"])
    return combined


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
    """Every status:pending or status:blocked issue whose dependencies are
    all status:done. status:blocked is included because nothing else ever
    relabels a blocked ticket back to pending once its dependency merges —
    this dependency check is the only thing that unblocks it."""
    candidates = list_pending_and_blocked_issues(repo, gh_runner=gh_runner)
    return [issue for issue in candidates if is_unblocked(issue, repo, gh_runner=gh_runner)]


def claim_ticket(repo, issue_number, claimant_note, gh_runner=run_gh):
    """Re-checks the issue is still pending/blocked (not already claimed or
    done) immediately before claiming, per the spec's race mitigation, then
    removes whichever status label is actually present."""
    labels = get_issue_labels(repo, issue_number, gh_runner=gh_runner)
    current_status = next((label for label in CLAIMABLE_LABELS if label in labels), None)
    if current_status is None:
        raise TicketNotAvailable(
            f"Issue #{issue_number} is no longer available (already claimed or done)"
        )

    gh_runner([
        "issue", "edit", str(issue_number), "--repo", repo,
        "--remove-label", current_status, "--add-label", "status:in-progress",
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
        try:
            claim_ticket(args.repo, args.claim, args.note)
        except TicketNotAvailable as exc:
            print(str(exc))
            return
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
