wait_for_pr_ci.py
-----------------

This small helper script polls GitHub Actions workflow runs for a branch or pull
request and waits until the latest run completes. It's intended to support a
developer workflow where new commits are pushed and you want to wait for CI
before pushing further commits.

Requirements
- Python 3.8+
- `requests` library (`pip install requests`)
- A GitHub personal access token available in the environment as `GITHUB_TOKEN`
  (scopes: `repo` and `workflow` are sufficient).

Example
-------
Set your token and run for the current branch:

```powershell
$env:GITHUB_TOKEN = "ghp_..."
python .\scripts\wait_for_pr_ci.py --branch feature/stage-1-backend-core --timeout 600
```

Or monitor a PR by number:

```powershell
python .\scripts\wait_for_pr_ci.py --pr 6
```

Behavior
- Exit code 0: latest run succeeded
- Exit code 2: latest run completed with non-success conclusion
- Exit code 3: timed out waiting
- Exit code 4/5: misconfiguration or API error

push_and_wait.py
----------------

Small wrapper that pushes the current branch and waits for the associated CI
run to complete. The script prefers the GitHub CLI (`gh`) to find and watch the
workflow run; if `gh` is not available it falls back to `wait_for_pr_ci.py` and
requires `GITHUB_TOKEN` in the environment.

Usage examples:

```powershell
python .\scripts\push_and_wait.py
python .\scripts\push_and_wait.py --branch feature/serve-ws-test
```

Exit codes mirror the underlying wait helpers (0 = success, non-zero = failure).
