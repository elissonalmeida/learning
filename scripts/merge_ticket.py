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
