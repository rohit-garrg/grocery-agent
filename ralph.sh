#!/bin/bash

# Ralph Wiggum Loop — Grocery Price Comparison Agent
# Each iteration: fresh Claude Code instance, one task, commit, exit.
# Two-pass per iteration: implement, then adversarial review (with Gemini via MCP).
# Progress tracked via IMPLEMENTATION_PLAN.md checkboxes and git history.
#
# Usage: ./ralph.sh <max_iterations>
# Example: ./ralph.sh 25
#
# Pre-flight: run claude-code-setup interactively before first use.
# See SETUP.md for one-time browser login and project bootstrapping.

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

# timeout command: GNU coreutils ships 'timeout' on Linux, 'gtimeout' on macOS via Homebrew
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD="gtimeout"
else
  echo "Error: neither 'timeout' nor 'gtimeout' found."
  echo "On macOS: brew install coreutils"
  exit 1
fi

# ─── Configuration ────────────────────────────────────────────────────────────

MAX_ITERATIONS=$1
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$PROJECT_DIR/ralph.log"
TIMEOUT_SECONDS=900   # 15 minutes per implementation pass
REVIEW_TIMEOUT=600    # 10 minutes per review pass

# Review pass runs on Sonnet (faster, cheaper, different perspective from implementation model)
REVIEW_MODEL="claude-sonnet-4-6"

cd "$PROJECT_DIR"

# ─── Required file checks ────────────────────────────────────────────────────

for required_file in PROMPT.md REVIEW_PROMPT.md IMPLEMENTATION_PLAN.md; do
  if [ ! -f "$required_file" ]; then
    echo "Error: $required_file not found in $PROJECT_DIR."
    echo "The Ralph loop requires PROMPT.md, REVIEW_PROMPT.md, and IMPLEMENTATION_PLAN.md."
    exit 1
  fi
done

# Sanity check: at least one unchecked task exists
if ! grep -qE '^\- \[ \]' IMPLEMENTATION_PLAN.md; then
  echo "No unchecked tasks found in IMPLEMENTATION_PLAN.md. Nothing to do."
  exit 0
fi

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

  # ── Pass 1: Implementation ──────────────────────────────────────────────

  result=$($TIMEOUT_CMD "$TIMEOUT_SECONDS" claude -p "$(cat PROMPT.md)" \
    --allowedTools "Bash" "Read" "Write" "Edit" "MultiEdit" \
    --output-format text 2>&1) || {
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "ERROR: Implementation pass timed out after ${TIMEOUT_SECONDS}s on iteration $i." | tee -a "$LOG_FILE"
      echo "Stopping loop. Review logs and restart if appropriate." | tee -a "$LOG_FILE"
      exit 1
    fi
    echo "WARNING: Implementation pass exited with code $exit_code on iteration $i." | tee -a "$LOG_FILE"
    result=""
  }

  echo "$result" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  echo "=== Implementation pass finished: $(date) ===" | tee -a "$LOG_FILE"

  # Check for completion signal
  if echo "$result" | grep -q "<promise>COMPLETE</promise>"; then
    echo "" | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    echo "All tasks complete after $i iterations." | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"
    exit 0
  fi

  # Check for failed tasks
  if grep -qE '^\- \[!\]' IMPLEMENTATION_PLAN.md; then
    echo "" | tee -a "$LOG_FILE"
    echo "WARNING: A task was marked as failed [!] in IMPLEMENTATION_PLAN.md." | tee -a "$LOG_FILE"
    echo "Review the task, fix the underlying issue, then resume:" | tee -a "$LOG_FILE"
    echo "  $0 $((MAX_ITERATIONS - i))" | tee -a "$LOG_FILE"
    exit 1
  fi

  # ── Pass 2: Adversarial review (Claude + Gemini via MCP) ────────────────
  # Skip review for scaffolding tasks (P0) and if implementation produced no output

  LAST_DONE=$(grep '^\- \[x\]' IMPLEMENTATION_PLAN.md | tail -1 || true)

  if [ -n "$result" ] && ! echo "$LAST_DONE" | grep -qi "P0:"; then
    echo "--- Review pass for iteration $i ---" | tee -a "$LOG_FILE"

    review=$($TIMEOUT_CMD "$REVIEW_TIMEOUT" claude -p "$(cat REVIEW_PROMPT.md)" \
      --model "$REVIEW_MODEL" \
      --allowedTools "Bash" "Read" "Write" "Edit" "MultiEdit" "Task" "mcp__gemini__ask-gemini" "Agent(security-reviewer)" \
      --output-format text 2>&1) || {
      review_exit=$?
      echo "WARNING: Review pass exited with code $review_exit. Continuing." | tee -a "$LOG_FILE"
      review=""
    }

    echo "$review" | tee -a "$LOG_FILE"
    echo "=== Review pass finished: $(date) ===" | tee -a "$LOG_FILE"

    # Rate limit check on review pass too
    if is_rate_limited "${review:-}"; then
      echo "Rate limit detected in review pass. Pausing 60 seconds..." | tee -a "$LOG_FILE"
      sleep 60
    fi
  else
    echo "--- Skipping review (scaffolding task or empty result) ---" | tee -a "$LOG_FILE"
  fi

  # ── Rate limit check on implementation pass ─────────────────────────────

  if is_rate_limited "$result"; then
    echo "" | tee -a "$LOG_FILE"
    echo "Rate limit detected. Pausing 60 seconds..." | tee -a "$LOG_FILE"
    sleep 60
  fi

  # Brief pause between iterations
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
