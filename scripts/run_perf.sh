#!/usr/bin/env bash
# Run EOL Host GUI under Linux perf (samples for the whole run, then opens report).
# Usage: ./scripts/run_perf.sh [duration_seconds]
#   If duration is omitted, perf runs until you exit the GUI.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

DURATION="${1:-0}"
PERF_DATA="${REPO_ROOT}/perf.data"

echo "Starting EOL Host GUI under perf..."
echo "  Repo root:   $REPO_ROOT"
echo "  Perf data:   $PERF_DATA"
echo "  Duration:    ${DURATION}s (0 = until you close the GUI)"
echo ""

if [[ "$DURATION" -gt 0 ]]; then
  python -m host_gui.main &
  APP_PID=$!
  sleep 2
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "Failed to start GUI (PID $APP_PID)."
    exit 1
  fi
  echo "Recording for ${DURATION}s (PID $APP_PID)..."
  sudo perf record -F 99 -g -p "$APP_PID" -o "$PERF_DATA" -- sleep "$DURATION"
  kill -INT "$APP_PID" 2>/dev/null || true
  wait "$APP_PID" 2>/dev/null || true
else
  # Run GUI as current user (so venv is used); attach perf to it.
  python -m host_gui.main &
  APP_PID=$!
  sleep 2
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "Failed to start GUI (PID $APP_PID)."
    exit 1
  fi
  echo "Recording until you close the GUI (PID $APP_PID)..."
  sudo perf record -F 99 -g -p "$APP_PID" -o "$PERF_DATA" &
  PERF_PID=$!
  wait "$APP_PID"
  kill -INT "$PERF_PID" 2>/dev/null || true
  wait "$PERF_PID" 2>/dev/null || true
fi

echo ""
echo "Recording finished. Opening perf report..."
perf report -i "$PERF_DATA"
