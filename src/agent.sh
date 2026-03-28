#!/bin/bash
set -euo pipefail
SELECTION="${1:?Selection argument required}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Concurrency guard
LOCKFILE="/tmp/grocery-agent.lock"
if [ -f "$LOCKFILE" ]; then
  echo "LOCKED"
  exit 0
fi
trap 'rm -f "$LOCKFILE"' EXIT
touch "$LOCKFILE"

cd "$PROJECT_ROOT"

# Placeholder: D3 will add claude -p invocation and agent_prompt.md here.
# For now, just invoke the orchestrator directly for testing.
python3 src/orchestrator.py "${SELECTION}"
