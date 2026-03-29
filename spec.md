# Grocery Price Comparison Agent — Spec

## What This Is

A Telegram-connected agent that compares grocery prices across Amazon (with Prime) and Blinkit for a user in Gurugram 122001. The user selects items from a stored master list, the agent fetches current prices from both platforms using a headless browser, calculates the optimal cart split factoring in delivery fees and order thresholds, and returns the recommendation via Telegram.

## Architecture Overview

The system has three layers:

1. **Telegram bot** (`telegram_bot.py`): A long-running Python process that polls for messages, validates the user, routes commands, and shells out to `agent.sh`.
2. **Agent bridge** (`agent.sh`): Invokes `claude -p` with the user's selection and the agent system prompt. Claude Code orchestrates the comparison pipeline by running Python scripts via bash.
3. **Python pipeline** (`orchestrator.py`, scrapers, optimizer, formatter): Pure Python modules that do the actual work — browser scraping, price optimization, and output formatting. Invoked by Claude Code via bash.

The agent runs via `claude -p` (Claude Code headless mode) on a Max plan. **Browser automation uses the Python Playwright library (sync API) — not Playwright MCP.** Scrapers are Python scripts that drive a persistent Chromium browser profile. Claude Code's role is to orchestrate the pipeline, handle errors, and pass the formatted output back to the Telegram bot.

## Platforms

### Amazon (amazon.in — Fresh / Now section)

- User has Amazon Prime.
- Free delivery above ₹99 for Prime users. Zero platform fees.
- Cashback tiers exist (e.g., ₹50 back above ₹399, ₹100 back above ₹749). These are promotional and change. The scraper reads whatever cashback/offer banners are visible on the **search results page or category page** — not by navigating to cart. If no offers are visible, fee structure defaults to: delivery free above ₹99, no cashback tiers.
- Prices may differ for Prime vs non-Prime. The agent must operate within a logged-in Prime session.
- Location must be set to Gurugram 122001. Amazon uses address selection, not just pincode.

**Fee discovery for Amazon:** After searching items, read the delivery badge text from product listing cards (e.g., "FREE delivery on orders over ₹99"). Read any visible cashback banners on the page. Do NOT navigate to the cart to discover fees.

### Blinkit (blinkit.com)

- User does NOT have Blinkit Plus.
- Delivery fees and handling charges vary by order value. The scraper reads the current fee thresholds from the **delivery info widget or banner** visible on the search/category page (e.g., "Free delivery above ₹199" or "₹25 delivery fee").
- After reading fees from the current page, also navigate to the empty cart page and read any fee structure text displayed there (the cart page is the most authoritative source). Do NOT add items to the cart for fee discovery. If no fee info is found on either the search page or the cart page, use defaults: ₹25 delivery, ₹9 handling, free delivery above ₹199, no cashback.
- Location must be set to pincode 122001. Blinkit typically prompts for location on first visit or when location isn't set.
- May show app-install prompts or location modals that need dismissing before searching.

### Platform availability handling

If a platform is unreachable (site down, CAPTCHA, layout changed beyond recognition), retry twice with a 10-second pause between attempts. If still failing after retries, proceed with whatever platforms responded and report the failure in the Telegram output.

## Authentication

The agent uses a persistent Playwright browser profile stored on disk. The user logs into each platform once manually in this browser profile. The agent reuses the stored session (cookies, local storage) on every run. The browser profile directory is set via the `BROWSER_PROFILE_PATH` environment variable.

**Session expiry detection:** If the scraper encounters a login page or authentication prompt (detected by URL pattern containing "signin", "login", or "auth", OR by presence of a login form element), it stops scraping that platform and returns a structured error: `{"status": "session_expired", "platform": "<name>"}`. The orchestrator converts this to a Telegram message: "Session expired on [Platform]. Please re-login in the browser profile and try again." The agent does NOT attempt to log in on the user's behalf. It does NOT store credentials.

## Master List

Stored as a JSON file: `master_list.json`.

Schema per item:

```json
{
  "id": 1,
  "name": "Toor Dal 1kg",
  "query": "toor dal 1 kg",
  "brand": null,
  "category": "pulses"
}
```

Fields:
- `id`: Auto-incrementing integer based on max existing id. Never reused after deletion.
- `name`: Display name shown to user in Telegram.
- `query`: Search string used on each platform. May differ from display name for better search results. Editable directly in the JSON file.
- `brand`: Optional. If set, the match function only considers candidates whose `brand` field contains this string (case-insensitive substring match). If null, the match function picks the cheapest result that meets the relevance threshold.
- `category`: For display grouping only (dairy, pulses, grains, snacks, etc.). Does not affect pricing logic.

**Adding items via Telegram:** `/add Amul Butter 500g`. The agent creates a new entry with next available id, sets both `name` and `query` to the full text after `/add`, sets `brand` to null, and `category` to "uncategorized." The user can edit `master_list.json` directly to tune the `query` string or set a `brand`. The agent confirms: "Added #42: Amul Butter 500g. You can edit master_list.json to set brand or tune the search query."

**Removing items:** `/remove 42` (by id). Agent asks for confirmation, then removes on "yes."

## Interaction Flow

### Price Comparison (primary flow)

1. User sends `/compare` (or any unrecognized message, which shows help including `/compare`).
2. `telegram_bot.py` loads `master_list.json`, formats the numbered list grouped by category, sends to user:

```
🧺 Your grocery list:

Pulses
1. Toor Dal 1kg
2. Moong Dal 1kg
3. Chana Dal 500g

Dairy
4. Amul Butter 500g
5. Amul Taaza Milk 1L

Reply with item numbers separated by commas.
For multiple units, use Nx format (e.g., 1x2 = two units of item 1).
Example: 1x2,4,5,8,12
```

3. User replies with selection: `1x2,4,5,8,12`.
4. `telegram_bot.py` validates the selection via `selection_parser.py`. If invalid, sends error and asks to re-enter. If valid, sends "Got it. Fetching prices for N items... (this takes 2-5 minutes)."
5. `telegram_bot.py` calls `agent.sh` with the validated selection string as an argument.
6. `agent.sh` invokes `claude -p` with the agent system prompt and selection.
7. Claude Code runs `python3 src/orchestrator.py "1x2,4,5,8,12"` via bash.
8. `orchestrator.py` runs the full pipeline (see below), writes the formatted output to stdout.
9. Claude Code captures the output and returns it.
10. `agent.sh` captures Claude's output and returns it to `telegram_bot.py`.
11. `telegram_bot.py` sends the output to the user (splitting if needed).

### Orchestrator pipeline (inside orchestrator.py)

1. Parses the selection string, loads `master_list.json`, resolves item names and quantities.
2. Opens a Playwright persistent browser context from `BROWSER_PROFILE_PATH`.
3. For each platform (Amazon, then Blinkit), in sequence:
   a. Verify location is set to 122001. If not, set it.
   b. Dismiss any modals or banners (Blinkit).
   c. For each selected item: search, extract candidate results (all reasonable matches), pass to `find_best_match()`.
   d. Read fee structure from the page (see fee discovery rules per platform above).
   e. Record: per-item prices, brands, and fee structure. Record "unavailable" for items with no match.
4. Calls `optimizer.py` with collected prices and fees.
5. Calls `formatter.py` with optimization result.
6. Writes the formatted Telegram message to stdout (may be multiple messages if split needed).
7. Logs the run to `logs/` and appends to `price_history/prices.jsonl`.
8. Closes the browser.

### Add Item

1. User sends: `/add Ghee 1L`
2. Agent adds to `master_list.json`. Confirms: "Added #42: Ghee 1L (category: uncategorized). Edit master_list.json to set brand or tune the query."

### Remove Item

1. User sends: `/remove 42`
2. Agent confirms the item name: "Remove #42 Ghee 1L? Reply yes to confirm."
3. User replies "yes".
4. Agent removes from `master_list.json` and confirms.
5. State for "awaiting confirmation" is stored in `telegram_bot.py`'s in-memory conversation state dict (keyed by user_id). This state is lost on bot restart, which is acceptable.

## Product Match Selection

**This is a Python heuristic, not LLM judgment.** The `find_best_match()` function in `src/match_utils.py` (shared by both scrapers) implements the following rules:

1. Normalize the `query` string: collapse whitespace, strip punctuation, lowercase. Then tokenize by splitting on spaces. Additionally, normalize common unit patterns: join any digit token followed by a unit token into a single token (e.g., tokens ["1", "kg"] also produce "1kg"; tokens ["500", "g"] also produce "500g"). This gives a combined token set for matching.
2. For each candidate, normalize its `name` field the same way. Score by counting how many query tokens (including the joined unit tokens) appear in the candidate's normalized token set.
3. If `brand` is set in the master list item, filter to candidates where `brand.lower()` is a substring of `candidate["brand"].lower()`. If no candidates pass this filter, return `None` (item unavailable with that brand constraint).
4. From remaining candidates, return the cheapest one with a relevance score above a minimum threshold (at least 50% of the original query tokens matched — count against the pre-join token count, not the expanded set).
5. If no results exceed the threshold, return `None`.

A future version could replace this with an LLM call for ambiguous cases. That is explicitly out of scope for v1.

## Optimization Logic

The optimizer takes as input:
- List of selected items with prices per platform (some may be None/"unavailable") and requested quantities
- Fee structure per platform: `{"delivery_fee": float, "handling_fee": float, "free_delivery_threshold": float | None, "cashback_tiers": [{"min_order": float, "cashback": float}]}`. All platforms use the same fee structure schema. Amazon's `handling_fee` is 0.
- Visible cashback tiers per platform (list of `{min_order, cashback}` dicts; may be empty)

The optimizer outputs a dict with: per-platform item assignments, subtotals, fees (delivery and handling per platform), cashback applied, platform totals, combined total, single-platform totals (for comparison), and savings vs best single-platform option.

### Rules

1. Items only available on one platform are pre-assigned. No choice to make.
2. For items available on both platforms, brute-force all 2^N assignments (where N = number of dual-platform items). For each combination, compute per-platform subtotals (unit price × quantity), apply fee rules (delivery fee waived if subtotal >= free_delivery_threshold; handling fee always applies), apply best cashback tier (highest cashback where min_order <= subtotal), compute total. Pick the combination with the lowest combined total.
3. Brute force is feasible for up to 20 dual-platform items (2^20 ≈ 1M combinations runs in under 1 second). If N > 20, log a warning and use greedy: assign each dual-platform item to its cheapest platform, then evaluate whether consolidating onto one platform would cross a fee threshold and save money.
4. If delivery fees can't be determined for a platform, assume worst-case defaults: Amazon ₹40 delivery + ₹0 handling, Blinkit ₹25 delivery + ₹9 handling, no cashback.

### Edge cases

- All items cheaper on one platform: recommend single-platform order. Still show the comparison.
- Very small order (1-2 items): if total delivery + handling fees exceed 20% of item cost, flag this in the output.
- Platform unavailable: optimize across available platforms only. Note the unavailable platform in output.

## Output Format

Telegram messages, split if the total exceeds 4096 characters.

**Splitting rules (in priority order):**
1. If total output fits in 4096 characters, send as one message.
2. Split at the `\n✅ RECOMMENDED SPLIT:\n` boundary: comparison table as message 1, recommendation + totals as message 2.
3. If the comparison table alone exceeds 4096 characters (large item count), split the table across messages at row boundaries (between `├──...` separator lines). Never split mid-row.
4. If a single row exceeds 4096 characters (should not happen in practice), truncate the item name.

```
📊 Price Comparison Results

ITEM COMPARISON:
┌──────────────────┬─────┬──────────┬──────────┐
│ Item             │ Qty │ Amazon   │ Blinkit  │
├──────────────────┼─────┼──────────┼──────────┤
│ Toor Dal 1kg     │ x2  │ ₹135 ea  │ ₹128 ea  │
│ (Tata)           │     │          │          │
├──────────────────┼─────┼──────────┼──────────┤
│ Amul Butter 500g │ x1  │ ₹295     │ ₹290     │
├──────────────────┼─────┼──────────┼──────────┤
│ Olive Oil 1L     │ x1  │ ₹449     │ N/A      │
│ (Figaro)         │     │          │          │
└──────────────────┴─────┴──────────┴──────────┘

✅ RECOMMENDED SPLIT:

From Amazon (3 items, 4 units):
  • Toor Dal 1kg x2 — Tata — ₹135 x2 = ₹270
  • Olive Oil 1L — Figaro — ₹449
  Subtotal: ₹719
  Delivery: Free (Prime, above ₹99)
  Cashback: ₹50 (above ₹399)
  Platform total: ₹669

From Blinkit (1 item):
  • Amul Butter 500g — ₹290
  Subtotal: ₹290
  Delivery: ₹25
  Handling: ₹9
  Platform total: ₹324

💰 COMBINED TOTAL: ₹993
vs all from Amazon: ₹1,082
vs all from Blinkit: N/A (Olive Oil unavailable)
Savings with split: ₹89
```

## Tech Stack

- **Runtime:** Claude Code via `claude -p` on Max plan (invoked without `--resume`; fresh context per run)
- **Browser automation:** Python Playwright library (`playwright` package), sync API, headless Chromium
- **Messaging:** Telegram Bot API (`python-telegram-bot` v22.x, async)
- **Language:** Python 3.11+
- **Optimization:** Pure Python brute-force (no external solver)
- **Data storage:** JSON files on disk
- **Session management:** Playwright persistent browser context (`playwright.sync_api.sync_playwright().chromium.launch_persistent_context(path)`)
- **Process management:** Shell scripts for Telegram polling + `claude -p` invocation

## Directory Structure

```
grocery-agent/
├── .env                          # TELEGRAM_TOKEN, ALLOWED_USER_ID, BROWSER_PROFILE_PATH, PINCODE
├── .gitignore
├── .claude/
│   └── settings.json             # Claude Code tool permissions (headless + interactive)
├── CLAUDE.md                     # Project conventions (auto-read by Claude Code)
├── spec.md                       # This file
├── IMPLEMENTATION_PLAN.md        # Ralph loop task checklist
├── PROMPT.md                     # Ralph loop per-iteration implementation prompt
├── REVIEW_PROMPT.md              # Ralph loop per-iteration adversarial review prompt
├── ralph.sh                      # Ralph loop orchestrator (two-pass: implement + review)
├── SETUP.md                      # First-time setup guide (browser login, MCP verification)
├── requirements.txt              # Pinned Python dependencies
├── master_list.json              # Grocery item master list
├── src/
│   ├── telegram_bot.py           # Telegram polling + command routing + user validation
│   ├── agent.sh                  # Bridges Telegram to claude -p
│   ├── agent_prompt.md           # System prompt for claude -p agent
│   ├── orchestrator.py           # Main pipeline coordinator (called by agent via bash)
│   ├── scraper_amazon.py         # Amazon search + price extraction via Playwright
│   ├── scraper_blinkit.py        # Blinkit search + price extraction via Playwright
│   ├── browser_manager.py        # Playwright persistent context management
│   ├── match_utils.py            # Shared find_best_match() heuristic
│   ├── optimizer.py              # Cart split optimization
│   ├── formatter.py              # Telegram output formatting
│   ├── selection_parser.py       # Parses "1x2,4,5x3" syntax
│   ├── master_list_manager.py    # CRUD for master_list.json
│   └── logger.py                 # Run logging and price history
├── tests/
│   ├── conftest.py               # Pytest marker registration (integration, etc.)
│   ├── test_optimizer.py
│   ├── test_formatter.py
│   ├── test_master_list.py
│   ├── test_selection_parser.py
│   ├── test_match_utils.py
│   ├── test_scrapers.py          # Integration tests (marked, require browser)
│   ├── test_browser_smoke.py     # Browser context smoke test (integration)
│   ├── test_orchestrator.py      # Orchestrator pipeline tests (mocked scrapers)
│   ├── test_logger.py            # Logging unit tests
│   └── test_telegram_bot.py      # Telegram bot unit tests
├── browser_profile/              # Playwright persistent context (gitignored)
├── logs/                         # Agent run logs (gitignored)
└── price_history/                # Historical price data (gitignored)
```

## Environment Variables

```
TELEGRAM_TOKEN=         # Bot token from @BotFather
ALLOWED_USER_ID=        # Your Telegram user ID (integer)
BROWSER_PROFILE_PATH=   # Absolute path to Playwright persistent browser context directory
PINCODE=122001          # Delivery pincode
```

## Security

- `ALLOWED_USER_ID` is validated in `telegram_bot.py` BEFORE any message reaches `agent.sh` or `claude -p`. Hard gate, not a prompt instruction.
- `.env`, `browser_profile/`, `logs/`, `price_history/`, `ralph.log` are gitignored.
- Agent's bash access is scoped via `--allowedTools "Bash"` in `agent.sh` (headless mode requires explicit tool permissions; no interactive prompts).
- Telegram messages from the user are passed to `agent.sh` as shell-quoted arguments. Never interpolated unquoted.
- Item selection validated against regex `^\d+(x\d+)?(,\d+(x\d+)?)*$` in `telegram_bot.py` before being passed to `agent.sh`.
- No credentials stored in code. All secrets in `.env` loaded via `python-dotenv`.

## Concurrency

A lock directory (`/tmp/grocery-agent.lock`) prevents concurrent `claude -p` invocations. `agent.sh` creates the directory atomically with `mkdir` (race-free on POSIX) and writes its PID to `$LOCKDIR/pid`. On exit, the directory is removed via `trap`. If another process holds the lock, `agent.sh` checks whether the PID is still alive — if not, it reclaims the stale lock. On the Telegram side, `telegram_bot.py` pre-checks with `os.path.isdir()` before spawning the subprocess, sending "A comparison is already running. Please wait." if the lock exists.

## Logging

Every comparison run logs to `logs/run_YYYYMMDD_HHMMSS.json`:

```json
{
  "timestamp": "2026-03-26T10:00:00",
  "selected_items": [{"id": 1, "qty": 2}, {"id": 4, "qty": 1}],
  "platforms": {
    "amazon": {"status": "success", "items_found": 4, "items_not_found": 1, "fees": {...}, "session_valid": true},
    "blinkit": {"status": "session_expired"}
  },
  "recommendation": {},
  "total_cost": 1234,
  "run_duration_seconds": 120
}
```

## Price History

Appends to `price_history/prices.jsonl` (one JSON object per item per run):

```json
{"date": "2026-03-26", "item_id": 1, "item_name": "Toor Dal 1kg", "amazon_price": 135, "amazon_brand": "Tata", "blinkit_price": null, "blinkit_brand": null, "blinkit_status": "unavailable"}
```

For unavailable items: `price` is `null`, `brand` is `null`, `status` field is set to `"unavailable"` or `"session_expired"`.

## Non-Goals (v1)

- No Zepto or Flipkart Minutes support (Phase 2).
- No Playwright MCP — Python Playwright library only.
- No card-specific discount optimization.
- No automated checkout or cart addition. (Navigating to an empty cart page to read fee banners is allowed; adding items to cart is not.)
- No price alerts ("tell me when X drops below ₹Y").
- No multi-address support. Single address: pincode 122001.
- No scheduled/cron comparisons. On-demand via Telegram only.
- No web UI. Telegram only.
- No LLM-based product matching. Heuristic only in v1.

## Acceptance Criteria

1. User sends `/compare` to Telegram bot and receives a numbered master list within 5 seconds.
2. User replies with item numbers. Agent acknowledges within 3 seconds and begins comparison.
3. Agent fetches prices from Amazon and Blinkit using Python Playwright with a persistent browser profile. Total scraping time under 5 minutes for 15 items across 2 platforms.
4. Agent produces a correctly optimized cart split that factors in item prices and dynamically discovered delivery/handling fees.
5. Output shows per-item price and brand comparison, the recommended split with per-platform totals, and savings vs single-platform ordering.
6. If a platform is unreachable after 2 retries, the agent proceeds with available platforms and reports the failure.
7. If a session is expired, the agent detects it and alerts the user instead of returning wrong data.
8. `/add` and `/remove` commands correctly modify `master_list.json`.
9. Every comparison run produces a log entry and price history records (with null for unavailable items).
10. No credentials stored in code or config. Lockfile prevents concurrent runs.
