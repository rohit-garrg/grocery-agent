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

# Detect timeout command (macOS uses gtimeout from coreutils)
if command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout"
elif command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout"
else
    TIMEOUT_CMD=""
fi

# Selection is regex-validated upstream (digits, x, commas only).
# Pass via --append-system-prompt to avoid shell interpolation in the prompt string.
AGENT_PROMPT="$(cat src/agent_prompt.md)

User's item selection: ${SELECTION}"

CLAUDE_CMD=(claude -p "Compare grocery prices for the items selected by the user." \
    --append-system-prompt "$AGENT_PROMPT" \
    --allowedTools "Bash" \
    --output-format text)

if [ -n "$TIMEOUT_CMD" ]; then
    CLAUDE_CMD=("$TIMEOUT_CMD" 900 "${CLAUDE_CMD[@]}")
fi

result=$("${CLAUDE_CMD[@]}" 2>&1) || {
    [ -z "$result" ] && result="ERROR: claude -p failed or timed out"
}

echo "$result"
