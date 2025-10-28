#!/usr/bin/env bash
set -euo pipefail

mkdir -p build/verify_environment
TS=$(date -u +"%Y%m%dT%H%M%SZ")
OUT="build/verify_environment/verification-$(uname -s)-${TS}.txt"
{
  echo "timestamp: ${TS}"
  echo "uname: $(uname -a)"
  echo "os-release:"
  cat /etc/os-release 2>/dev/null || true
  echo "python version: $(python3 --version 2>&1 || python --version 2>&1)"
  echo "pip freeze:"
  (python3 -m pip freeze 2>/dev/null || python -m pip freeze 2>/dev/null) || true
  echo "node version: $(node --version 2>&1 || true)"
  echo "npm version: $(npm --version 2>&1 || true)"
  echo "npm list --depth=0 (frontend deps):"
  (npm ls --depth=0 2>/dev/null || true)
} > "${OUT}"

echo "Wrote ${OUT}"

exit 0
