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
│   ├── telegram_bot.py           # Telegram polling + command routing (async, python-telegram-bot v20)
│   ├── agent.sh                  # Bridges Telegram to claude -p (includes lockfile)
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
│   └── test_*.py                 # One test file per source module
├── master_list.json              # Item master list (source of truth)
├── .claude/settings.json         # Claude Code tool permissions
├── PROMPT.md                     # Ralph loop implementation prompt
├── REVIEW_PROMPT.md              # Ralph loop adversarial review prompt
├── ralph.sh                      # Ralph loop orchestrator (two-pass: implement + review)
├── spec.md                       # Product spec
├── IMPLEMENTATION_PLAN.md        # Task checklist
└── SETUP.md                      # First-time setup and browser login guide
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

**Context7** (`npx @upstash/context7-mcp`): Used for looking up current library documentation during implementation. Helpful for python-telegram-bot v20 API, Playwright API, etc.

**Review pass model:** The review pass runs on Sonnet 4.6 (`--model claude-sonnet-4-6` in ralph.sh) regardless of what model the implementation pass uses. This gives a different perspective and is cheaper/faster. Configurable via `REVIEW_MODEL` in ralph.sh.

These MCP servers are configured at user scope (`~/.claude.json` or via `claude mcp add -s user`) and are available automatically in both interactive and headless (`claude -p`) mode.

## Language, Dependencies, and Setup

- Python 3.11+
- `python-telegram-bot==20.7` (async, ApplicationBuilder pattern — NOT the v13 synchronous API)
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

1. **`.claude/settings.json`** (for interactive sessions):
   ```json
   {
     "permissions": {
       "allow": [
         "Bash(*)",
         "Read(*)",
         "Write(*)",
         "Edit(*)",
         "MultiEdit(*)"
       ],
       "deny": []
     }
   }
   ```

2. **`--allowedTools` flag** (for headless mode in ralph.sh and agent.sh):
   ```
   --allowedTools "Bash" "Read" "Write" "Edit" "MultiEdit"
   ```

Both are required. The settings.json covers interactive use. The `--allowedTools` flag covers `claude -p` invocations.

## Common Pitfalls

- Amazon and Blinkit page layouts change without warning. If a selector breaks, update only the selector expression, not the surrounding extraction logic.
- Blinkit shows a location modal and an app-install banner on most page loads. `dismiss_modals()` must be called before any search interaction.
- Amazon shows different prices for Prime vs non-Prime. The agent must run within a logged-in Prime session. If prices look wrong, check that the session is valid.
- `python-telegram-bot` v20 is fully async. All handlers must be `async def`. Do not mix sync and async patterns in `telegram_bot.py`.
- Telegram messages have a 4096 character limit. Always call `formatter.split_message()` before sending. Do not assume the output will be short. With 15+ items, the comparison table alone can exceed 4096 chars.
- Master list IDs are never reused after deletion. Always compute next id as `max(existing_ids) + 1`, not `len(list) + 1`.
- `playwright install chromium` must be run after every fresh `pip install playwright`. The package alone does not include the browser binary.
- On macOS, use `gtimeout` instead of `timeout`. ralph.sh auto-detects this, but agent.sh may need manual adjustment.
- The match_utils `find_best_match()` includes unit normalization: "1 kg" and "1kg" are treated as equivalent during token matching. Both forms are generated and checked.

## Learned Conventions

*(This section is updated by Claude Code during Ralph iterations when new platform-specific quirks or patterns are discovered.)*

- Both scrapers cap results at 20 candidates per search to avoid processing noise from lower-relevance listings.
- Amazon brand extraction only recognizes three specific patterns: "by BrandName", "Visit the BrandName Store", "Brand: BrandName". Other secondary text is ignored.
- Blinkit brand extraction never infers brand from the product name (e.g., first word). Returns empty string if no brand-specific element is found, to avoid wrong results for multi-word brands like "Mother Dairy" or adjectives like "Low Fat".
- Blinkit uses multiple selector fallback lists for every UI interaction (product cards, names, prices, search bar, location widget). The first selector that matches wins. This makes scrapers more resilient to Blinkit's class name changes.
- Blinkit fee discovery always visits the cart page after reading the current page, not just as a fallback. The cart page is the most authoritative fee source.
- Amazon's `_check_session_expired` checks URL for "signin", "login", or "auth" keywords. Blinkit uses the same approach.
- `dismiss_modals()` on Blinkit includes a keyboard Escape press as a catch-all after trying all close-button selectors.

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
