#!/bin/bash
set -euo pipefail
SELECTION="${1:?Selection argument required}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Concurrency guard — mkdir is atomic on POSIX filesystems (no TOCTOU race)
LOCKDIR="/tmp/grocery-agent.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
    # Check if the holding process is still alive (handles stale lock from SIGKILL/crash)
    if [ -f "$LOCKDIR/pid" ] && kill -0 "$(cat "$LOCKDIR/pid")" 2>/dev/null; then
        echo "LOCKED"
        exit 0
    fi
    # Stale lock — owning process is gone; reclaim
    rm -rf "$LOCKDIR"
    mkdir "$LOCKDIR"
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT

cd "$PROJECT_ROOT"

# Placeholder: D3 will add claude -p invocation and agent_prompt.md here.
# For now, just invoke the orchestrator directly for testing.
python3 src/orchestrator.py "${SELECTION}"
