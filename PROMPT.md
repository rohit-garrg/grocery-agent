# Ralph Wiggum Loop — Per-Iteration Prompt

You are implementing a grocery price comparison agent. Read the following files thoroughly before doing anything else:

1. `spec.md` — the source of truth for all requirements and architecture decisions
2. `IMPLEMENTATION_PLAN.md` — the task checklist; pick from here
3. `CLAUDE.md` — project conventions, patterns, and learned quirks; follow these exactly

The working directory is the project root (the directory containing this PROMPT.md file). All file paths in the spec and implementation plan are relative to this root.

## Your task for this iteration

Pick the **highest-priority unchecked task** (first `- [ ]` item in IMPLEMENTATION_PLAN.md).

Before writing any code:
- Check what source files already exist in `src/` that are relevant to this task. Read only those files — not the entire directory. On early iterations, `src/` may be empty; that is expected.
- If the task depends on functions defined in other modules (e.g., the optimizer uses data structures from the scrapers), read those modules too.
- Verify the task's requirements against `spec.md`. If there is any ambiguity, the spec takes precedence over the task description.

## Implementation rules

- Write clean, minimal code that satisfies the current task only. Do not implement features from future tasks.
- Follow the conventions in `CLAUDE.md` exactly: function signatures return dicts, error handling uses ValueError, sync Playwright API, no hardcoded credentials.
- If you discover a new convention, quirk, or platform-specific workaround during implementation, add it to the "Learned conventions" section of `CLAUDE.md` before committing.
- For integration tests (those marked `@pytest.mark.integration`): implement the test but do not run it — it requires a live browser profile. Leave a comment in the test: `# Integration test: requires browser profile with [platform] login`.
- For all other tests: run them, and they must pass.

## Test and commit flow

Run tests with: `python -m pytest tests/ -v -m "not integration"`

If tests pass:
1. Stage only the files you created or modified in this task. Do not use `git add -A` blindly — verify with `git status` that you are not staging unintended files (logs, browser profiles, `.env`).
2. Commit: `git add <specific files> && git commit -m "Complete [TASK_ID]: [brief description]"`
3. Mark the task complete in `IMPLEMENTATION_PLAN.md` by changing `- [ ]` to `- [x]`.
4. Commit the updated plan: `git add IMPLEMENTATION_PLAN.md && git commit -m "Mark [TASK_ID] complete"`

If tests fail:
1. Read the error output carefully.
2. Fix the implementation — not the test. Tests encode the spec requirements and must not be weakened.
3. Re-run tests. Repeat up to 3 times.
4. If the issue is a flaky test unrelated to your implementation (e.g., an import error from a module that doesn't exist yet), document this clearly and proceed.
5. If you genuinely cannot fix it after 3 attempts, mark the task `- [!]` in IMPLEMENTATION_PLAN.md, add a code comment explaining exactly what failed and why, commit, and exit.

## Dependencies

If `requirements.txt` dependencies are not yet installed, run:
`pip install -r requirements.txt --break-system-packages`

If `playwright install chromium` has not been run, run it before any Playwright-related task.

## Completion

Output `<promise>COMPLETE</promise>` **only** when every task in IMPLEMENTATION_PLAN.md is marked `[x]`. Do not output this string if any tasks are `[ ]` or `[!]`.
