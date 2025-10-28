#!/usr/bin/env python3
"""Wait for the latest GitHub Actions workflow run for a PR or branch.

Usage:
  Set environment variable GITHUB_TOKEN (personal access token with repo scope).
  Then run:
    python scripts/wait_for_pr_ci.py --pr 6
  or
    python scripts/wait_for_pr_ci.py --branch feature/stage-1-backend-core

This script polls the GitHub Actions runs for the repo and waits until the latest
run for the given PR/branch completes (success or failure). It exits with 0 on
success and non-zero on failure or timeout.

Note: This script uses the GitHub REST API. It requires network access and a
valid GITHUB_TOKEN in the environment. Timeout and polling interval are
configurable via command-line options.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import typing as t
import requests


REPO_OWNER = "JacobEEEGuy005"
REPO_NAME = "EOL-Host-Application"


def gh_api_get(path: str, token: str, params: dict | None = None) -> dict:
    url = f"https://api.github.com{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def wait_for_branch_runs(token: str, branch: str, timeout: int, interval: int) -> int:
    """Poll workflow runs for a branch and return exit code 0 if latest run succeeded."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # list workflow runs for branch
        data = gh_api_get(f"/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs", token, params={"branch": branch, "per_page": 10})
        runs = data.get("workflow_runs", [])
        if not runs:
            print(f"No workflow runs found for branch {branch}; waiting...", flush=True)
            time.sleep(interval)
            continue

        latest = runs[0]
        status = latest.get("status")
        conclusion = latest.get("conclusion")
        run_id = latest.get("id")
        html_url = latest.get("html_url")
        print(f"Found run {run_id} status={status} conclusion={conclusion} url={html_url}")
        if status == "completed":
            if conclusion == "success":
                print("Latest workflow run succeeded.")
                return 0
            else:
                print(f"Latest workflow run finished with conclusion={conclusion}.")
                return 2

        print(f"Run {run_id} not completed yet (status={status}); sleeping {interval}s...")
        time.sleep(interval)

    print("Timed out waiting for workflow run to complete.")
    return 3


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pr", type=int, help="Pull Request number to monitor (optional)")
    g.add_argument("--branch", type=str, help="Branch name to monitor")
    p.add_argument("--timeout", type=int, default=900, help="Timeout seconds (default 900s)")
    p.add_argument("--interval", type=int, default=10, help="Polling interval seconds (default 10s)")
    args = p.parse_args(argv)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN environment variable is required to call the GitHub API.", file=sys.stderr)
        return 4

    if args.branch:
        return wait_for_branch_runs(token, args.branch, args.timeout, args.interval)

    # PR mode: find the head branch for the PR and monitor that branch
    prnum = args.pr
    pr = gh_api_get(f"/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{prnum}", token)
    head = pr.get("head", {}).get("ref")
    if not head:
        print(f"Could not determine head branch for PR {prnum}", file=sys.stderr)
        return 5
    print(f"PR {prnum} head branch is {head}; monitoring branch workflow runs.")
    return wait_for_branch_runs(token, head, args.timeout, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
