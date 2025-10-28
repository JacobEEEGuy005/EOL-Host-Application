#!/usr/bin/env python3
"""Push current branch (or specified) and wait for CI to complete.

This is a thin wrapper around `git push` and `scripts/wait_for_pr_ci.py`.

Usage:
  python scripts/push_and_wait.py            # push current branch
  python scripts/push_and_wait.py --branch feature/foo
  python scripts/push_and_wait.py --pr 6

Requirements:
  - GITHUB_TOKEN set in env for wait_for_pr_ci.py when using PR/branch monitoring
  - git and python on PATH
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import os


def current_branch() -> str:
    p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"Could not determine current branch: {p.stderr.strip()}")
    return p.stdout.strip()


def git_push(remote: str, branch: str) -> None:
    print(f"Pushing {branch} to {remote}...")
    p = subprocess.run(["git", "push", remote, branch])
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def run_wait_script(pr: int | None, branch: str | None, timeout: int, interval: int) -> int:
    cmd = [sys.executable, os.path.join("scripts", "wait_for_pr_ci.py")]
    if pr is not None:
        cmd += ["--pr", str(pr)]
    elif branch is not None:
        cmd += ["--branch", branch]
    else:
        raise SystemExit("Either --pr or --branch must be provided to wait for CI")

    cmd += ["--timeout", str(timeout), "--interval", str(interval)]
    print("Waiting for CI to complete...\n    " + " ".join(cmd))
    p = subprocess.run(cmd)
    return p.returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pr", type=int, help="Pull request number to monitor")
    g.add_argument("--branch", type=str, help="Branch name to push/monitor")
    p.add_argument("--remote", type=str, default="origin", help="Git remote to push to (default: origin)")
    p.add_argument("--timeout", type=int, default=900, help="Timeout in seconds to wait for CI (default: 900)")
    p.add_argument("--interval", type=int, default=10, help="Polling interval seconds (default: 10)")
    args = p.parse_args(argv)

    try:
        branch = args.branch or current_branch()
    except SystemExit as e:
        print(e)
        return 2

    try:
        git_push(args.remote, branch)
    except SystemExit as e:
        print(f"git push failed: {e}")
        return 3

    # Prefer PR monitoring if PR provided, otherwise monitor the branch
    rc = run_wait_script(args.pr, branch if args.pr is None else None, args.timeout, args.interval)
    if rc == 0:
        print("CI succeeded.")
    else:
        print(f"CI failed or timed out (code {rc}).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Push current branch and wait for PR/branch CI to finish.

This script wraps a git push and then waits for the corresponding GitHub
Actions workflow run for the branch or PR to complete. It prefers the GitHub
CLI (`gh`) if available, otherwise falls back to the repo's
`scripts/wait_for_pr_ci.py` helper which requires GITHUB_TOKEN.

Usage:
  python scripts/push_and_wait.py [--remote origin] [--branch current]

Behavior:
  - Runs: git push <remote> <branch>
  - Identifies the PR for the current branch (if exists) and waits for the
    latest workflow run to complete.
  - Exits with 0 if CI succeeds, non-zero otherwise.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import shutil
import os
from typing import Optional


def run(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None, text=True)


def current_branch() -> str:
    p = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    if p.returncode != 0:
        raise SystemExit("Failed to determine current git branch")
    return p.stdout.strip()


def push(remote: str, branch: str) -> int:
    print(f"Pushing {branch} to {remote}...")
    p = run(["git", "push", remote, branch])
    return p.returncode


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_wait_for_pr(branch: str) -> int:
    # Find PR for branch
    print("Finding PR for branch via gh...")
    p = run(["gh", "pr", "view", "--json", "number,headRefName", "--jq", ".number, .headRefName"], capture=True)
    if p.returncode != 0:
        print("gh pr view failed; will fall back to wait_for_pr_ci.py", file=sys.stderr)
        return 2
    out = p.stdout.strip().splitlines()
    if not out:
        print("No PR found for branch; falling back to branch-based wait")
        return 2
    # The above may return multiple fields; we'll just attempt branch wait via gh run list
    # List recent runs for the branch and watch the most recent in_progress or queued run
    p2 = run(["gh", "run", "list", "--branch", branch, "--limit", "5", "--json", "databaseId,status,conclusion"], capture=True)
    if p2.returncode != 0:
        print("gh run list failed; falling back to wait_for_pr_ci.py", file=sys.stderr)
        return 2
    # Use gh to watch the latest run id if found
    # Try to get the first run id via jq-like approach using gh's --jq isn't reliable here; parse minimal JSON
    import json
    runs = json.loads(p2.stdout)
    if not runs:
        print("No workflow runs found via gh; falling back")
        return 2
    latest = runs[0]
    run_id = latest.get("databaseId")
    if not run_id:
        print("Could not determine run id; falling back")
        return 2
    print(f"Watching run {run_id} via gh run watch...")
    p3 = run(["gh", "run", "watch", str(run_id), "--exit-status"])  # this will block until completion
    return p3.returncode


def fallback_wait(branch: str) -> int:
    # call scripts/wait_for_pr_ci.py --branch <branch>
    script = os.path.join(os.path.dirname(__file__), "wait_for_pr_ci.py")
    if not os.path.exists(script):
        print("No fallback script available: scripts/wait_for_pr_ci.py not found", file=sys.stderr)
        return 4
    p = run([sys.executable, script, "--branch", branch])
    return p.returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default=None)
    args = p.parse_args(argv)

    branch = args.branch or current_branch()
    rc = push(args.remote, branch)
    if rc != 0:
        print("git push failed", file=sys.stderr)
        return rc

    # After push, wait for CI to complete.
    if gh_available():
        rc2 = gh_wait_for_pr(branch)
        if rc2 == 0:
            print("CI succeeded (gh).")
            return 0
        print("gh path did not determine success; falling back to script.")

    rc3 = fallback_wait(branch)
    if rc3 == 0:
        print("CI succeeded (fallback script).")
        return 0
    print("CI reported failure or timed out.")
    return rc3


if __name__ == "__main__":
    raise SystemExit(main())
