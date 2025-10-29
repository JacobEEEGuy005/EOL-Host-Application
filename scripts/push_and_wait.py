#!/usr/bin/env python3
from __future__ import annotations

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

import argparse
import subprocess
import sys
import shutil
import os
import json
from typing import Optional


def run(cmd, capture: bool = False):
    """Run a command and optionally capture output.

    Returns subprocess.CompletedProcess.
    """
    return subprocess.run(cmd, check=False, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None, text=True)


def current_branch() -> str:
    p = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    if p.returncode != 0:
        raise SystemExit("Failed to determine current git branch")
    return (p.stdout or "").strip()


def push(remote: str, branch: str) -> int:
    print(f"Pushing {branch} to {remote}...")
    p = run(["git", "push", remote, branch])
    return p.returncode


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_wait_for_pr(branch: str) -> int:
    # Find PR for branch
    print("Finding PR for branch via gh...")
    p = run(["gh", "pr", "view", "--json", "number,headRefName"], capture=True)
    if p.returncode != 0:
        print("gh pr view failed; will fall back to wait_for_pr_ci.py", file=sys.stderr)
        return 2
    try:
        pr_info = json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        print("gh pr view output could not be parsed; falling back", file=sys.stderr)
        return 2

    prnum = pr_info.get("number")
    if not prnum:
        print("No PR found for branch; falling back to branch-based wait")
        return 2

    # List recent runs for the branch and watch the most recent run id
    p2 = run(["gh", "run", "list", "--branch", branch, "--limit", "5", "--json", "databaseId"], capture=True)
    if p2.returncode != 0:
        print("gh run list failed; falling back to wait_for_pr_ci.py", file=sys.stderr)
        return 2
    try:
        runs = json.loads(p2.stdout or "[]")
    except json.JSONDecodeError:
        print("gh run list output could not be parsed; falling back", file=sys.stderr)
        return 2

    if not runs:
        print("No workflow runs found via gh; falling back")
        return 2
    latest = runs[0]
    run_id = latest.get("databaseId")
    if not run_id:
        print("Could not determine run id; falling back")
        return 2
    print(f"Watching run {run_id} via gh run watch...")
    p3 = run(["gh", "run", "watch", str(run_id), "--exit-status"])  # blocks until completion
    return p3.returncode


def fallback_wait(branch: str) -> int:
    # call scripts/wait_for_pr_ci.py --branch <branch>
    script = os.path.join(os.path.dirname(__file__), "wait_for_pr_ci.py")
    if not os.path.exists(script):
        print("No fallback script available: scripts/wait_for_pr_ci.py not found", file=sys.stderr)
        return 4
    p = run([sys.executable, script, "--branch", branch])
    return p.returncode


def main(argv: Optional[list[str]] = None) -> int:
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
    import os
