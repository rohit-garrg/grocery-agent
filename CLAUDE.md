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
              └── python src/orchestrator.py (main pipeline)
                    ├── scraper_amazon.py     (Playwright, sync)
                    ├── scraper_blinkit.py    (Playwright, sync)
                    ├── match_utils.py        (heuristic matching)
                    ├── optimizer.py          (brute-force split)
                    ├── formatter.py          (Telegram formatting)
                    └── logger.py             (run logs + price history)
```

**Browser automation uses the Python Playwright library (sync API) — NOT Playwright MCP.** Scrapers are plain Python scripts that drive Chromium. There are no `mcp__playwright__*` tool calls. Claude Code's role is to invoke the orchestrator via bash and handle the output.

## Project Structure

```
grocery-agent/
├── src/                          # All source code
│   ├── telegram_bot.py           # Telegram polling + command routing (async, python-telegram-bot v20)
│   ├── agent.sh                  # Bridges Telegram to claude -p (includes lockfile)
│   ├── agent_prompt.md           # System prompt for claude -p agent
│   ├── orchestrator.py           # Pipeline coordinator (run as: python src/orchestrator.py "1x2,4")
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
└── .claude/settings.json        # Claude Code tool permissions (Bash, Read, Write)
```

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

**Testing:** Use pytest. Run with: `python -m pytest tests/ -v -m "not integration"` to skip integration tests. Integration tests (requiring a live browser) are marked `@pytest.mark.integration` and will not run in CI.

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

## Key Design Decisions

**Search-based matching, not URL mapping.** Master list items have a `query` field used to search platforms. Matching is done by `match_utils.find_best_match()` — a keyword heuristic. No LLM judgment is involved in v1 matching.

**Dynamic fee discovery — from the page, not from the cart.** Amazon fees are read from delivery badges on the product listing page. Blinkit fees are read from page banners or a lightweight cart page check. Never add items to the cart as part of fee discovery. Never hardcode fee structures.

**Persistent browser sessions.** The agent reuses a Playwright browser profile stored at `BROWSER_PROFILE_PATH`. It never handles login credentials or attempts to log in. On session expiry, it alerts the user.

**Brute-force optimization with greedy fallback.** For N <= 20 dual-platform items, brute-force 2^N combinations. For N > 20, log a warning and use greedy: assign each item to its cheaper platform, then evaluate one-platform consolidation for fee threshold effects.

**Telegram message splitting at section boundaries only.** Never split mid-table. The split point is always between the comparison table section and the recommendation section.

**No --resume flag.** `claude -p` is invoked fresh for each comparison run. No session persistence across runs.

## Common Pitfalls

- Amazon and Blinkit page layouts change without warning. If a selector breaks, update only the selector expression, not the surrounding extraction logic.
- Blinkit shows a location modal and an app-install banner on most page loads. `dismiss_modals()` must be called before any search interaction.
- Amazon shows different prices for Prime vs non-Prime. The agent must run within a logged-in Prime session. If prices look wrong, check that the session is valid.
- `python-telegram-bot` v20 is fully async. All handlers must be `async def`. Do not mix sync and async patterns in `telegram_bot.py`.
- Telegram messages have a 4096 character limit. Always call `formatter.split_message()` before sending. Do not assume the output will be short.
- Master list IDs are never reused after deletion. Always compute next id as `max(existing_ids) + 1`, not `len(list) + 1`.
- `playwright install chromium` must be run after every fresh `pip install playwright`. The package alone does not include the browser binary.

## Learned Conventions

*(This section is updated by Claude Code during Ralph iterations when new platform-specific quirks or patterns are discovered.)*

- (Empty at project start. Add entries here as the build progresses.)

## E2E Test Notes

*(This section is updated manually after Phase D7 end-to-end testing.)*

- (Empty at project start.)
