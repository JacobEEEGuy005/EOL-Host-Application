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
