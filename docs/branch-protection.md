# Branch Protection Guidance

Recommended branch protection rules for the `main` branch (configure in GitHub repository settings or via an admin workflow):

- Require pull request reviews before merging (at least 1 approver)
- Require status checks to pass (CI jobs: lint, test, verify)
- Require branches to be up to date before merging
- Restrict who can push to `main` (admins or CI)
- Use required linear history (optional)

Implement these rules as part of repository setup before allowing merges to `main`.
