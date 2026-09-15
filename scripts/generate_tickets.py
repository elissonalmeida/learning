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
        f"Depends on: {depends_text}\n"
        f"<!-- depends-on: {depends_text} -->"
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
