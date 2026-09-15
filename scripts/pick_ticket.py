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
