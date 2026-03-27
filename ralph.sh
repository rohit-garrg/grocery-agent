#!/bin/bash

# Ralph Wiggum Loop — Grocery Price Comparison Agent
# Each iteration: fresh Claude Code instance, one task, commit, exit.
# Progress tracked via IMPLEMENTATION_PLAN.md checkboxes and git history.
#
# Usage: ./ralph.sh <max_iterations>
# Example: ./ralph.sh 25

set -euo pipefail

# ─── Preflight checks ────────────────────────────────────────────────────────

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <max_iterations>"
  echo "Example: $0 25"
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Error: 'claude' not found in PATH."
  echo "Is Claude Code installed? See: https://docs.claude.ai/claude-code"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Error: 'git' not found in PATH."
  exit 1
fi

# ─── Configuration ────────────────────────────────────────────────────────────

MAX_ITERATIONS=$1
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$PROJECT_DIR/ralph.log"
TIMEOUT_SECONDS=900  # 15 minutes per iteration max

cd "$PROJECT_DIR"

# ─── Git initialization ───────────────────────────────────────────────────────

if [ ! -d ".git" ]; then
  echo "Initializing git repository..."
  git init
  git add -A
  git commit -m "Initial project setup"
fi

# ─── Interrupt handling ───────────────────────────────────────────────────────

cleanup() {
  echo "" >&2
  echo "Interrupted. Check IMPLEMENTATION_PLAN.md for current task state." >&2
  echo "Any in-progress task may be partially implemented but not committed." >&2
  exit 130
}
trap cleanup INT TERM

# ─── Rate limit detection ─────────────────────────────────────────────────────

is_rate_limited() {
  local output="$1"
  if echo "$output" | grep -qi "rate.limit\|too many requests\|quota exceeded\|429"; then
    return 0
  fi
  return 1
}

# ─── Main loop ────────────────────────────────────────────────────────────────

echo "=== Ralph Wiggum Loop ===" | tee -a "$LOG_FILE"
echo "Project: $PROJECT_DIR" | tee -a "$LOG_FILE"
echo "Max iterations: $MAX_ITERATIONS" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  ITER_START=$(date)
  echo "=========================================" | tee -a "$LOG_FILE"
  echo "=== Iteration $i of $MAX_ITERATIONS ===" | tee -a "$LOG_FILE"
  echo "=== Started: $ITER_START ===" | tee -a "$LOG_FILE"
  echo "=========================================" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"

  # Run Claude Code with a per-iteration timeout.
  # stdout is captured; stderr is shown live for debugging.
  # || true: we handle failures explicitly below via result inspection.
  result=$(timeout "$TIMEOUT_SECONDS" claude -p "$(cat PROMPT.md)" \
    --output-format text 2>&1) || {
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "ERROR: claude -p timed out after ${TIMEOUT_SECONDS}s on iteration $i." | tee -a "$LOG_FILE"
      echo "This may indicate a hung browser or network issue." | tee -a "$LOG_FILE"
      echo "Stopping loop. Review logs and restart if appropriate." | tee -a "$LOG_FILE"
      exit 1
    fi
    echo "WARNING: claude -p exited with code $exit_code on iteration $i." | tee -a "$LOG_FILE"
    result=""
  }

  echo "$result" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  echo "=== Finished: $(date) ===" | tee -a "$LOG_FILE"

  # Check for completion signal
  if echo "$result" | grep -q "<promise>COMPLETE</promise>"; then
    echo "" | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    echo "All tasks complete after $i iterations." | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    exit 0
  fi

  # Check for failed tasks (anchored to line start to avoid false matches)
  if grep -qE '^\- \[!\]' IMPLEMENTATION_PLAN.md; then
    echo "" | tee -a "$LOG_FILE"
    echo "WARNING: A task was marked as failed [!] in IMPLEMENTATION_PLAN.md." | tee -a "$LOG_FILE"
    echo "Review the task, fix the underlying issue, then resume:" | tee -a "$LOG_FILE"
    echo "  $0 $((MAX_ITERATIONS - i))" | tee -a "$LOG_FILE"
    exit 1
  fi

  # Detect rate limiting and pause before next iteration
  if is_rate_limited "$result"; then
    echo "" | tee -a "$LOG_FILE"
    echo "Rate limit detected in iteration $i output. Pausing 60 seconds before next iteration..." | tee -a "$LOG_FILE"
    sleep 60
  fi

  # Brief pause between iterations to avoid hammering the API
  if [ $i -lt $MAX_ITERATIONS ]; then
    echo "--- Pausing 5 seconds before iteration $((i+1)) ---" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    sleep 5
  fi

done

echo "" | tee -a "$LOG_FILE"
echo "=========================================" | tee -a "$LOG_FILE"
echo "Reached max iterations ($MAX_ITERATIONS) without completing all tasks." | tee -a "$LOG_FILE"
echo "Check IMPLEMENTATION_PLAN.md for remaining tasks." | tee -a "$LOG_FILE"
echo "To continue: $0 <additional_iterations>" | tee -a "$LOG_FILE"
echo "=========================================" | tee -a "$LOG_FILE"
exit 1
