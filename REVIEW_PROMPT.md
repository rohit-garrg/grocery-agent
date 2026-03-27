# Ralph Wiggum Loop — Adversarial Review Prompt

You are a senior staff engineer performing adversarial review of the last completed task.

Read these files first:
1. `spec.md` — source of truth
2. `IMPLEMENTATION_PLAN.md` — find the most recently completed task (the last `- [x]` item)
3. `CLAUDE.md` — project conventions

Then identify the files changed in the last commit. Run:
```
git log --oneline -2
```

If there are at least 2 commits, read the diff:
```
git diff HEAD~1 --name-only
git diff HEAD~1
```

If there is only 1 commit (first iteration), read the full file listing instead:
```
git show --stat HEAD
git diff --cached HEAD
```

Read the changed files in full.

## Step 1: Your own critique

Evaluate the implementation against the spec and conventions. Identify:
1. The three weakest decisions and propose concrete alternatives.
2. Unnecessary complexity that could be simplified without losing functionality.
3. Assumptions the code makes but does not validate.
4. Any drift from spec.md or CLAUDE.md conventions.

## Step 2: Second opinion (Gemini first, subagent fallback)

Try the Gemini MCP `ask-gemini` tool first. Send it the diff and ask it to act as an adversarial senior staff engineer. Tell it to focus on:
- Bugs that will cascade in later tasks
- Edge cases not covered by tests
- Spec violations
- Naming, structure, or API contract issues that will be painful to fix later

If the Gemini MCP tool fails (rate limit, timeout, connection error, or any error), use the `Task` tool instead to spawn a subagent for the second opinion. Give the subagent this instruction:

> You are a senior staff engineer performing adversarial code review. Here is the diff from the last commit. Your job is NOT approval. Identify: (1) the three weakest decisions and propose concrete alternatives, (2) unnecessary complexity, (3) unvalidated assumptions, (4) spec violations. Be specific. Reference function names and line numbers.

Pass the diff content to the subagent. Use its critique in Step 3 the same way you would use Gemini's.

Do not fail the review because of a tool error. If both Gemini and the Task subagent fail, proceed with your own critique from Step 1 only.

## Step 2.5: Security review (Phase B and later only)

If the most recently completed task ID starts with B, C, D, or E (not A or P0), spawn the `security-reviewer` agent via the Agent tool. Pass it the diff from Step 1. Include its findings in Step 3 alongside the Gemini/subagent critique.

Skip this step for Phase A and P0 tasks — they have no credential or session handling.

## Step 3: Decide and act

You are the decision-maker. For each point from both critiques:
- **Accept**: implement the fix, run tests, commit with `git commit -am "Review fix: [brief description]"`
- **Reject**: note briefly why (one line)
- **Adapt**: modify the suggestion and implement

Run tests after any change: `python3 -m pytest tests/ -v -m "not integration"`

Do NOT mark any tasks in IMPLEMENTATION_PLAN.md.
Do NOT pick new tasks.
Do NOT output `<promise>COMPLETE</promise>`.
