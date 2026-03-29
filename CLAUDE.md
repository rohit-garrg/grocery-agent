# CLAUDE.md — Grocery Price Comparison Agent

## What This Project Is

A Telegram bot that compares grocery prices across Amazon (Prime) and Blinkit for a user in Gurugram 122001. The user selects items from a master list, the agent scrapes current prices via Python Playwright, optimizes the cart split factoring in delivery fees and cashback, and returns a recommendation via Telegram.

Full spec: `spec.md`
Task checklist: `IMPLEMENTATION_PLAN.md`

## Architecture

```
telegram_bot.py (long-running async process)
  └── agent.sh (shell bridge, invoked via subprocess)
        └── claude -p (orchestrator — reads agent_prompt.md)
              └── python3 src/orchestrator.py (main pipeline)
                    ├── selection_parser.py    (parses "1x2,4" syntax)
                    ├── master_list_manager.py (loads master_list.json)
                    ├── browser_manager.py     (Playwright persistent context)
                    ├── scraper_amazon.py      (Playwright, sync)
                    ├── scraper_blinkit.py     (Playwright, sync)
                    ├── match_utils.py         (heuristic matching)
                    ├── optimizer.py           (brute-force split)
                    ├── formatter.py           (Telegram formatting)
                    └── logger.py              (run logs + price history)
```

**Browser automation uses the Python Playwright library (sync API) — NOT Playwright MCP.** Scrapers are plain Python scripts that drive Chromium. There are no `mcp__playwright__*` tool calls. Claude Code's role is to invoke the orchestrator via bash and handle the output.

## Project Structure

```
grocery-agent/
├── src/                          # All source code
│   ├── telegram_bot.py           # Telegram polling + command routing (async, python-telegram-bot v22)
│   ├── agent.sh                  # Bridges Telegram to claude -p (includes lockdir guard)
│   ├── agent_prompt.md           # System prompt for claude -p agent
│   ├── orchestrator.py           # Pipeline coordinator (run as: python3 src/orchestrator.py "1x2,4")
│   ├── scraper_amazon.py         # Amazon price scraping via Playwright (sync)
│   ├── scraper_blinkit.py        # Blinkit price scraping via Playwright (sync)
│   ├── browser_manager.py        # Playwright persistent context lifecycle
│   ├── match_utils.py            # Shared find_best_match() heuristic
│   ├── optimizer.py              # Cart split optimization (brute-force, greedy fallback at N>20)
│   ├── formatter.py              # Telegram output formatting + message splitting
│   ├── selection_parser.py       # Parses "1x2,4,5x3" input syntax
│   ├── master_list_manager.py    # CRUD for master_list.json
│   └── logger.py                 # Run logging and price history
├── tests/
│   ├── conftest.py               # Registers pytest markers (integration)
│   ├── test_edge_cases.py        # Cross-module edge case tests (E2 hardening)
│   └── test_*.py                 # One test file per source module
├── master_list.json              # Item master list (source of truth)
├── .claude/
│   ├── settings.local.json       # Local Claude Code permissions + hooks (untracked)
│   └── agents/
│       └── security-reviewer.md  # Security review subagent definition
├── .env.example                  # Template for .env (all required vars documented)
├── setup_browser.sh              # Opens headed browser for manual platform login
├── SETUP.md                      # First-time setup guide
├── PROMPT.md                     # Ralph loop implementation prompt
├── REVIEW_PROMPT.md              # Ralph loop adversarial review prompt
├── ralph.sh                      # Ralph loop orchestrator (two-pass: implement + review)
├── spec.md                       # Product spec
└── IMPLEMENTATION_PLAN.md        # Task checklist
```

## Build Process: Ralph Wiggum Loop

This project is built using the Ralph Wiggum loop: autonomous iterative execution with fresh context per task.

**Two-pass iteration:** Each iteration has an implementation pass (PROMPT.md) followed by an adversarial review pass (REVIEW_PROMPT.md). The review pass uses Gemini via MCP for a second opinion. See ralph.sh for the full loop logic.

**Periodic maintenance tasks:** SIMPLIFY and SYNC-DOCS tasks appear at phase boundaries in IMPLEMENTATION_PLAN.md. These are treated as regular tasks (one per iteration) and follow the rules in PROMPT.md.

**Pre-flight (run once before starting the loop):**
1. Run `claude-code-setup` interactively to scaffold hooks, MCPs, and agents
2. Run `setup_browser.sh` to log into Amazon and Blinkit in the persistent browser profile
3. Verify MCP tools are available: `claude mcp list` should show Gemini and Context7
4. Run `./ralph.sh 25` to start the loop

## MCP Tools and Subagents (development-time only)

These are used during the Ralph loop build process. They are NOT used at runtime by the grocery agent itself.

**Gemini** (`npx gemini-mcp-tool`): Primary second-opinion tool in REVIEW_PROMPT.md via the `ask-gemini` tool. Authenticated via Gemini CLI with a Pro subscription. Available tools: `mcp__gemini__ask-gemini` (main tool for review), `mcp__gemini__brainstorm`, `mcp__gemini__fetch-chunk`, `mcp__gemini__Help`, `mcp__gemini__ping`, `mcp__gemini__timeout-test`. Pro tier rate limits apply (significantly higher than free tier).

**Task subagent** (built-in Claude Code tool): Fallback when Gemini rate-limits or errors. The review pass spawns a subagent via the `Task` tool with an adversarial review prompt. Runs on the same model as the review pass (Sonnet 4.6 by default, configured via `REVIEW_MODEL` in ralph.sh).

**Context7** (`npx @upstash/context7-mcp`): Used for looking up current library documentation during implementation. Helpful for python-telegram-bot v22 API, Playwright API, etc.

**Review pass model:** The review pass runs on Sonnet 4.6 (`--model claude-sonnet-4-6` in ralph.sh) regardless of what model the implementation pass uses. This gives a different perspective and is cheaper/faster. Configurable via `REVIEW_MODEL` in ralph.sh.

These MCP servers are configured at user scope (`~/.claude.json` or via `claude mcp add -s user`) and are available automatically in both interactive and headless (`claude -p`) mode.

## Language, Dependencies, and Setup

- Python 3.11+
- `python-telegram-bot==22.7` (async, ApplicationBuilder pattern — NOT the v13 synchronous API)
- `playwright==1.41.0` — sync API only in all scraper/browser files
- `python-dotenv==1.0.1` — load `.env` at the top of every module that needs env vars
- `pytest==7.4.4`, `pytest-asyncio==0.23.4`
- All dependencies in `requirements.txt` with pinned versions.
- After `pip install -r requirements.txt`, always run `playwright install chromium` to install the browser binary.

## Conventions

**File organization:** All source in `src/`. All tests in `tests/`. Test files mirror source: `src/optimizer.py` → `tests/test_optimizer.py`.

**Testing:** Use pytest. Run with: `python3 -m pytest tests/ -v -m "not integration"` to skip integration tests. Integration tests (requiring a live browser) are marked `@pytest.mark.integration` and will not run in CI.

**Functions return dicts, not custom classes.** Keep data structures simple and JSON-serializable.

**Error handling convention:**
- Use `ValueError` with a human-readable message for invalid input (wrong format, unknown id, etc.).
- Use `RuntimeError` for infrastructure failures (browser didn't load, network error, page layout unexpected).
- Return `None` only for "not found" cases (e.g., no matching product).
- Never return `None` for invalid input — raise `ValueError` instead.
- Never fail silently.

**Playwright API:** Use the sync API (`sync_playwright`, `playwright.chromium.launch_persistent_context`). Do NOT use async Playwright in scraper files. The scrapers are called from the orchestrator, which is a subprocess invoked from `agent.sh`. They do not run inside the async event loop of `telegram_bot.py`.

**JSON files:** 2-space indentation when written to disk.

**Environment variables:** Load from `.env` via `python-dotenv`. Call `load_dotenv()` at module level. Never hardcode credentials. Never print env vars to stdout.

**Commit messages:** Use format `Complete [TASK_ID]: [brief description]` for implementation commits. Use `Review fix: [brief description]` for changes made during the review pass. Use `Simplify: [what changed]` for simplify tasks. Use `Sync docs: [what changed]` for doc sync tasks.

## Key Design Decisions

**Search-based matching, not URL mapping.** Master list items have a `query` field used to search platforms. Matching is done by `match_utils.find_best_match()` — a keyword heuristic with unit normalization (e.g., "1 kg" matches "1kg"). No LLM judgment is involved in v1 matching.

**Brand matching uses the candidate's `brand` field, not the product name.** When `brand_constraint` is set, the filter checks `brand_constraint.lower() in candidate["brand"].lower()`. This is a substring match against the brand field specifically, not the product name.

**Dynamic fee discovery — from the page and the cart.** Amazon fees are read from delivery badges on the product listing page. Blinkit fees are read from page banners first, then the scraper always also navigates to the empty cart page (the most authoritative source for fee structure). Items are never added to the cart. Never hardcode fee structures.

**Symmetric fee structure across platforms.** Both Amazon and Blinkit use the same fee dict schema: `{"delivery_fee", "handling_fee", "free_delivery_threshold", "cashback_tiers"}`. Amazon's `handling_fee` is 0. This keeps the optimizer and formatter generic.

**Persistent browser sessions.** The agent reuses a Playwright browser profile stored at `BROWSER_PROFILE_PATH`. It never handles login credentials or attempts to log in. On session expiry, it alerts the user.

**Brute-force optimization with greedy fallback.** For N <= 20 dual-platform items, brute-force 2^N combinations. For N > 20, log a warning and use greedy: assign each item to its cheaper platform, then evaluate one-platform consolidation for fee threshold effects.

**Telegram message splitting with multi-level fallback.** Primary split point: between comparison table and recommendation section. If the table itself exceeds 4096 chars (large item count), split at row boundaries. Never split mid-row.

**No --resume flag.** `claude -p` is invoked fresh for each comparison run. No session persistence across runs.

## Permissions (headless mode)

Claude Code in headless mode (`claude -p`) requires explicit tool permissions. These are provided in two ways:

1. **`.claude/settings.local.json`** (for interactive sessions):
   Local settings file (untracked) with tool permissions and hooks. Contains `Bash(*)` patterns for common commands, plus `PreToolUse` hooks that block edits to credential/session files and `PostToolUse` hooks that auto-run tests after source file edits.

2. **`--allowedTools` flag** (for headless mode):
   - **ralph.sh** implementation pass: `--allowedTools "Bash" "Read" "Write" "Edit" "MultiEdit"`
   - **ralph.sh** review pass: `--allowedTools "Bash" "Read" "Write" "Edit" "MultiEdit" "Task" "mcp__gemini__ask-gemini" "Agent(security-reviewer)"`
   - **agent.sh** (runtime): `--allowedTools "Bash"` — the agent only needs to run `python3 src/orchestrator.py`

Both are required. The `settings.local.json` covers interactive use. The `--allowedTools` flag covers `claude -p` invocations.

## Common Pitfalls

- Amazon and Blinkit page layouts change without warning. If a selector breaks, update only the selector expression, not the surrounding extraction logic.
- Blinkit shows a location modal and an app-install banner on most page loads. `dismiss_modals()` must be called before any search interaction.
- Amazon shows different prices for Prime vs non-Prime. The agent must run within a logged-in Prime session. If prices look wrong, check that the session is valid.
- `python-telegram-bot` v20+ (currently v22.7) is fully async. All handlers must be `async def`. The only permitted sync/async bridge in `telegram_bot.py` is `asyncio.to_thread()` for subprocess calls — do not introduce any other sync/async mixing.
- Telegram messages have a 4096 character limit. Always call `formatter.split_message()` before sending. Do not assume the output will be short. With 15+ items, the comparison table alone can exceed 4096 chars.
- Master list IDs are never reused after deletion. Always compute next id as `max(existing_ids) + 1`, not `len(list) + 1`.
- `playwright install chromium` must be run after every fresh `pip install playwright`. The package alone does not include the browser binary.
- On macOS, both `ralph.sh` and `agent.sh` auto-detect `gtimeout` (from Homebrew coreutils) and fall back to `timeout`. If neither is installed, the timeout guard is skipped entirely.
- The match_utils `find_best_match()` includes unit normalization: "1 kg" and "1kg" are treated as equivalent during token matching. Both forms are generated and checked.

## Learned Conventions

*(This section is updated by Claude Code during Ralph iterations when new platform-specific quirks or patterns are discovered.)*

- Both scrapers cap results at 20 candidates per search to avoid processing noise from lower-relevance listings.
- Amazon brand extraction checks for a dedicated brand h2 (`h2.a-size-mini`) first (new Amazon layout for brand-filtered searches), then falls back to legacy "by BrandName" / "Visit the BrandName Store" / "Brand: BrandName" patterns.
- Amazon product name is extracted from the product link text (`a.a-link-normal.s-line-clamp-3`), not from h2 directly. Amazon restructured h2 elements — the link text is the most stable source for the product name.
- Blinkit brand extraction returns the full product name as brand when no dedicated brand element exists. This enables substring-based brand constraint matching in `find_best_match` (e.g., `"tata" in "Tata Sampann Toor Dal"` works).
- Blinkit search uses direct URL navigation (`/s/?q=<query>`) instead of interacting with the search bar. The homepage search bar is an `<a>` link, not an input.
- Blinkit uses multiple selector fallback lists for every UI interaction (product cards, names, prices, search bar, location widget). The first selector that matches wins. This makes scrapers more resilient to Blinkit's class name changes.
- Blinkit fee discovery always visits the cart page after reading the current page, not just as a fallback. However, if the cart is empty, Blinkit redirects to the homepage — the fee reader checks for `/cart` in the URL before extracting fees to avoid false matches from homepage content.
- Blinkit product cards use Tailwind CSS (`tw-*` classes) with `div[role="button"]` as the card container. Name: `div.tw-text-300.tw-font-semibold.tw-line-clamp-2`. Price: `div.tw-text-200.tw-font-semibold`. Unit: `div.tw-text-200.tw-font-medium.tw-line-clamp-1`.
- Blinkit blocks headless Chromium (returns error page). The browser runs in offscreen headed mode (`headless=False` with `--window-position=-10000,-10000`) on macOS.
- Amazon's `_check_session_expired` checks URL for "signin", "login", or "auth" keywords. Blinkit uses the same approach.
- `dismiss_modals()` on Blinkit includes a keyboard Escape press as a catch-all after trying all close-button selectors.
- Quantity tokens (e.g., 500g, 1kg, 4l) in queries are mandatory match criteria — candidates without a matching quantity token are filtered out before scoring. Unit aliases are normalized (ltr/litre/liter → l, piece/pieces → pcs) so "4 ltr" matches "4 L". The candidate's `unit` field is also checked, since Blinkit sometimes stores size info outside the product name.
- Both scrapers share a duck-typing interface: `set_location(page, pincode)`, `dismiss_modals(page)`, `search_items(page, query)`, `extract_results(page)`, `discover_fees(page)`. The orchestrator calls these generically via `scraper.fn(page, ...)`. Amazon's `dismiss_modals` is currently a no-op (Amazon rarely shows blocking overlays in a logged-in Prime session); Blinkit's dismisses banners/modals and presses Escape.
- The concurrency lock uses atomic `mkdir` (a directory, not a file) for race-free creation, with PID tracking (`$LOCKDIR/pid`) for stale lock recovery. `telegram_bot.py` pre-checks with `os.path.isdir()` before spawning the subprocess.
- The orchestrator enforces a daily run limit of 3 comparisons as a safety throttle against excessive automated requests. Count is determined by checking existing `run_YYYYMMDD_*.json` log files for the current date.
- Anti-bot-detection: the orchestrator adds random delays between item searches (2-5s) and between platform switches (3-8s) to reduce detection risk.
- `agent.sh` auto-detects the timeout command: uses `gtimeout` (macOS/Homebrew coreutils) if available, falls back to `timeout`, or runs without a timeout if neither is found.

## E2E Test Notes

*(This section is updated manually after Phase D7 end-to-end testing.)*

**Status:** Awaiting manual execution. Code review completed — no blocking issues found.

**Prerequisites before running:**
1. Add 5+ items to `master_list.json` via `/add` command or direct JSON edit (list is currently empty).
   Mix should include: items available on both platforms, at least one item available on only one platform, and at least one with a brand constraint.
2. Ensure browser profile has active Amazon Prime and Blinkit sessions (`setup_browser.sh` or manual login).
3. Set `TELEGRAM_TOKEN`, `ALLOWED_USER_ID`, `BROWSER_PROFILE_PATH`, `PINCODE` in `.env`.
4. Start the bot: `python3 src/telegram_bot.py`.

**Test checklist:**
- [ ] `/compare` displays master list grouped by category
- [ ] Valid selection (e.g., `1x2,3,4,5`) is acknowledged with "Fetching prices for N items..."
- [ ] Invalid selection shows error and allows re-entry
- [ ] Full formatted output appears in Telegram (comparison table + recommended split + totals)
- [ ] Spot-check 2 prices against live Amazon/Blinkit pages
- [ ] Run log created in `logs/run_YYYYMMDD_HHMMSS.json` with correct structure
- [ ] Price history appended to `price_history/prices.jsonl`
- [ ] Items unavailable on one platform show "N/A" in comparison table
- [ ] Session expiry warning appears if a platform session is invalid
- [ ] Message splitting works if output exceeds 4096 chars (test with 10+ items)
- [ ] Concurrent `/compare` while one is running shows "already running" message

**Code review notes (D7 prep):**
- Pipeline wiring (telegram_bot → agent.sh → claude -p → orchestrator) is consistent.
- Lock mechanism uses atomic `mkdir` in agent.sh with `os.path.isdir()` pre-check in telegram_bot.py.
- `agent.sh` only grants `Bash` tool to `claude -p`, matching agent_prompt.md's single-command design.
- Session expiry propagation path: scraper → `_scrape_platform()` → orchestrator output → Telegram message verified in code.
- Logging calls happen in `finally`-equivalent position (after format, before return) and are wrapped in try/except to never break the pipeline.

## Security Review (E3)

**Reviewed 2026-03-29. All items confirmed secure unless noted otherwise.**

### Input validation chain
- `selection_parser.py` enforces strict regex: `^\d+(x\d+)?(,\d+(x\d+)?)*$` — only digits, `x`, and commas.
- `telegram_bot.py` reconstructs the selection string from parsed integer dicts (lines 151-154), never passing raw user text to the shell.
- `agent.sh` receives the selection as a shell argument and embeds it into the `AGENT_PROMPT` string via `${SELECTION}` interpolation before passing to `--append-system-prompt`. This is safe because upstream regex validation guarantees only digits, `x`, and commas can reach this point — no shell metacharacters are possible.

### Authentication
- `is_allowed_user()` is called as the first check in every command handler and the text message handler. Unauthorized users receive no response.
- `ALLOWED_USER_ID` is validated as numeric at startup (`main()`). Missing or non-numeric values raise `RuntimeError` immediately.

### Concurrency lock
- `agent.sh` uses atomic `mkdir` for initial lock creation (POSIX race-free). The stale lock reclaim path (`rm -rf` + `mkdir`) is a two-step non-atomic sequence — two processes detecting a stale lock simultaneously would race, and the loser would exit early with no output (not a correctness failure for a single-user bot).
- `trap 'rm -rf "$LOCKDIR"' EXIT` covers all exit paths (normal exit, errors, signals except SIGKILL).
- `telegram_bot.py` pre-checks with `os.path.isdir()` before spawning subprocess (optimistic check, agent.sh is authoritative).

### Accepted risks
- **`.env` readable by the agent:** The `.env` file is in the project root. The `claude -p` agent invoked by `agent.sh` has `Bash` tool access and could read `.env` via `cat`. This is accepted because: (1) the agent already runs with the same OS user permissions as the bot process, so it has no elevated access, and (2) the agent prompt is tightly scoped to running the orchestrator only. Note: granting `Bash` is equivalent to granting file read — the distinction is only in the agent's intent, not its capability.
- **Telegram token in git history:** The `.env` file was accidentally committed in the initial project setup (`4eaee02`). It has been untracked (`git rm --cached .env`) but remains in git history. **Action required:** Regenerate the Telegram token via @BotFather, then clean git history with `git filter-repo --path .env --invert-paths` if the repo is ever shared.

### What's NOT logged
- No env vars, tokens, user IDs, or session data appear in logs or stdout.
- `logger.py` records only item IDs, names, prices, fees, and timing.
- Error messages in `orchestrator.py` are written to stderr and never include credentials.
