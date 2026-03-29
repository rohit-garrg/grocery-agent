# Implementation Plan — Grocery Price Comparison Agent

Reference: `spec.md` for full requirements.

---

## Phase 0: Project bootstrap (must complete before any other phase)

- [x] **P0: Project scaffolding and tooling.** Create directory structure per spec (`src/`, `tests/`, `logs/`, `price_history/`, `browser_profile/`). Create `.env.example` with all required env vars documented (TELEGRAM_TOKEN, ALLOWED_USER_ID, BROWSER_PROFILE_PATH, PINCODE). Create `.gitignore` (exclude `.env`, `browser_profile/`, `logs/`, `price_history/`, `node_modules/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `ralph.log`). Create `requirements.txt` with **pinned** versions:
  ```
  python-telegram-bot==20.7
  playwright==1.41.0
  python-dotenv==1.0.1
  pytest==7.4.4
  pytest-asyncio==0.23.4
  ```
  Create empty `master_list.json` as `[]`. Create `.claude/settings.json` only if it does not already exist (check first with `test -f`):
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
  If `.claude/settings.json` already exists, verify it contains the permissions above and add any missing entries. Do not overwrite other settings that may already be present.
  Run `pip install -r requirements.txt --break-system-packages`. Run `playwright install chromium`. Create `tests/conftest.py`:
  ```python
  import pytest
  def pytest_configure(config):
      config.addinivalue_line("markers", "integration: mark test as requiring a live browser profile")
  ```
  Initialize git (only if `.git/` does not exist): `git init && git add -A && git commit -m "Initial project scaffolding"`. If `.git/` already exists, just `git add -A && git commit -m "Complete P0: Project scaffolding"`. Verify: all directories exist, `python3 -m pytest tests/ -v` runs without marker warnings (no tests yet, that's fine), `.gitignore` is correct.

---

## Phase A: Foundation (pure unit tests, no external dependencies)

- [x] **A1: Master list manager.** Create `src/master_list_manager.py`. Functions: `load_list(filepath)` returns list of items (returns `[]` if file is empty or contains `[]`). `add_item(filepath, name, category="uncategorized")` adds item with id = max existing id + 1 (or 1 if list is empty), sets `name` and `query` to provided name, `brand` to `null`. Returns the new item dict. `remove_item(filepath, item_id)` removes item by id. Returns `True` if removed, raises `ValueError` if id not found. `get_item(filepath, item_id)` returns single item dict or `None`. IDs are never reused: always compute next id as `max(existing_ids) + 1`, not `len(list) + 1`. Write `tests/test_master_list.py` covering: add to empty list, add to non-empty list, remove existing item, remove nonexistent item (raises ValueError), get existing item, get nonexistent item (returns None), id-never-reused after deletion (delete id 3, next add gets id 4 not 3), load empty file, load file with items. Verify: `python3 -m pytest tests/test_master_list.py -v` passes.

- [x] **A2: Selection parser.** Create `src/selection_parser.py`. Function: `parse_selection(input_string, valid_ids)` takes a string like `"1x2,4,5x3,8"` and a set/list of valid ids, returns a list of `{"id": int, "qty": int}` dicts. Rules: strip whitespace before parsing; plain numbers default to qty 1; validate input matches regex `^\d+(x\d+)?(,\d+(x\d+)?)*$`; all ids must exist in valid_ids; no duplicate ids; all quantities must be positive integers (no zero, no negative). Raises `ValueError` with a human-readable message for any invalid input. Write `tests/test_selection_parser.py` covering: valid input with quantities, valid input without quantities (default qty 1), mixed (some with x, some without), single item, whitespace stripping, invalid regex (letters, spaces), unknown ids, duplicate ids, zero quantity, negative quantity, quantity of x0. Verify: tests pass.

- [x] **A3: Match utilities.** Create `src/match_utils.py`. Function: `find_best_match(candidates, query, brand_constraint=None)`. Input: `candidates` is a list of dicts, each with at minimum `{"name": str, "price": float, "brand": str}`. `query` is the search string from the master list. `brand_constraint` is an optional string. Logic: (1) normalize `query`: lowercase, strip punctuation (keep digits and letters), split on whitespace into tokens; (2) generate joined unit tokens: for each pair of adjacent tokens where the first is all digits and the second is a common unit string (kg, g, ml, l, lb, oz, pack, pcs, piece, pieces, ltr, litre, liter), create a joined token (e.g., tokens ["1", "kg"] also produce "1kg"); combine original tokens and joined tokens into a `query_token_set`; (3) for each candidate, normalize the candidate's `name` field the same way (lowercase, strip punctuation, split, generate joined unit tokens) into a `candidate_token_set`; (4) score: count how many tokens from the original query tokens (not the joined extras) appear in the `candidate_token_set` — also check joined query tokens against candidate_token_set; the score is the count of original query tokens that matched via either their original form or their joined form; (5) if `brand_constraint` is set, filter to candidates where `brand_constraint.lower()` is a substring of `candidate["brand"].lower()` — if no candidates pass this filter, return `None`; (6) from surviving candidates, keep those with score >= 0.5 * len(original_query_tokens); (7) return the candidate with the lowest price among those, or `None` if none survive. Write `tests/test_match_utils.py` covering: exact query match, partial match above threshold, partial match below threshold (returns None), brand filtering (exact case, different case), brand filter with no match (returns None), cheapest selected among multiple valid matches, empty candidates list (returns None), single candidate, unit normalization — query "1 kg" matches candidate name containing "1kg" AND query "1kg" matches candidate name containing "1 kg". Verify: tests pass.

- [x] **A4: Optimizer.** Create `src/optimizer.py`. Function: `optimize_cart(items, platform_fees)`. Input `items`: list of dicts, each with `{"id": int, "name": str, "qty": int, "prices": {"amazon": {"price": float, "brand": str} | None, "blinkit": {"price": float, "brand": str} | None}}`. Input `platform_fees`: dict with a consistent schema per platform: `{"amazon": {"delivery_fee": float, "handling_fee": float, "free_delivery_threshold": float | None, "cashback_tiers": [{"min_order": float, "cashback": float}]}, "blinkit": {...}}`. Note: Amazon's `handling_fee` is typically 0 but the schema is the same for all platforms to keep the optimizer generic. Logic: (1) pre-assign items available on only one platform; (2) for dual-platform items, brute-force all 2^N assignments; (3) if N > 20, log a warning and use greedy heuristic (assign each to cheaper platform, then evaluate one-platform consolidation); (4) for each assignment, compute per-platform subtotals (price × qty), apply delivery fee waiver if subtotal >= free_delivery_threshold, always apply handling_fee, apply best cashback tier (highest `cashback` where `min_order <= subtotal`), compute net total; (5) return the assignment with the lowest combined total. Output: `{"recommendation": {"amazon": [item_dicts], "blinkit": [item_dicts]}, "amazon_subtotal": float, "blinkit_subtotal": float, "amazon_delivery_fee": float, "blinkit_delivery_fee": float, "amazon_handling_fee": float, "blinkit_handling_fee": float, "amazon_cashback": float, "blinkit_cashback": float, "amazon_total": float, "blinkit_total": float, "combined_total": float, "all_amazon_total": float | None, "all_blinkit_total": float | None, "savings": float, "fee_warning": bool}`. `all_amazon_total` / `all_blinkit_total` are `None` if any item is unavailable on that platform. `fee_warning` is `True` if total fees (delivery + handling across both platforms) > 20% of total item cost. Write `tests/test_optimizer.py` covering: all items on one platform, items split across both, single item, delivery fee waiver triggered, delivery fee not waived, cashback applied, no cashback tiers, N > 20 items triggers greedy (mock large item list), fee warning triggered, fee warning not triggered, savings = 0 when single platform is optimal, all_amazon_total is None when an item is missing on Amazon, handling_fee always applied even when delivery is free. Verify: tests pass.

- [x] **A5: Output formatter.** Create `src/formatter.py`. Function: `format_comparison(optimizer_result, item_details)` returns a string or list of strings. `item_details` provides display names and quantities. Output sections in order: (1) header + item comparison table; (2) recommended split with per-platform itemization, fees, cashback, totals; (3) combined total + single-platform alternatives + savings. Function: `split_message(text, max_length=4096)` splits with the following priority: (a) if text fits, return as single-element list; (b) split at the `\n✅ RECOMMENDED SPLIT:\n` boundary into two messages; (c) if the first part (comparison table) still exceeds max_length, split it further at row boundaries (lines starting with `├`) — never mid-row; (d) if a single chunk still exceeds max_length after row-boundary splitting, hard-split at the last newline before max_length. Returns list of strings. Function: `format_unavailable(items)` formats a short note listing items not found on any platform. Write `tests/test_formatter.py` covering: basic output structure, quantity display (x2 items), N/A items in table, message splitting at section boundary, message splitting at row boundaries when table exceeds 4096, single-platform result (no split needed), fee warning display, cashback display, handling fee display (including when handling_fee is 0 for Amazon). Verify: tests pass.

- [x] **A-SIMPLIFY: Code health pass for Phase A.** Review all source files in `src/` created during Phase A (master_list_manager, selection_parser, match_utils, optimizer, formatter). Simplify without changing behavior. See PROMPT.md "SIMPLIFY tasks" rules.

- [x] **A-SYNC-DOCS: Documentation sync after Phase A.** Verify spec.md, CLAUDE.md, and IMPLEMENTATION_PLAN.md match the actual code. See PROMPT.md "SYNC-DOCS tasks" rules.

---

## Phase B: Telegram bot

- [x] **B1: Telegram bot core.** Create `src/telegram_bot.py`. Load env vars from `.env` using `python-dotenv` (TELEGRAM_TOKEN, ALLOWED_USER_ID). Set up `python-telegram-bot` v20 async polling using `ApplicationBuilder`. Implement user validation as the first handler in every command: reject any `update.effective_user.id != int(ALLOWED_USER_ID)` silently (no response to unknown users). In-memory conversation state: `state = {}` dict keyed by user_id, stores current flow step and pending data. Implement `/help` handler showing available commands. Verify: bot starts, connects to Telegram, responds to `/help` from allowed user, ignores messages from other users (manual test).

- [x] **B2: List display and selection flow.** In `telegram_bot.py`, implement `/compare` handler. Step 1: load master list, format as numbered items grouped by category (per spec), send to user, set `state[user_id] = {"step": "awaiting_selection"}`. Step 2: on next plain-text message from user (detected via `state` lookup), if step is "awaiting_selection": pass text to `selection_parser.parse_selection()`. If valid: store parsed selection in state, set step to "comparing", send "Got it. Fetching prices for N items... (this takes 2-5 minutes)", and call `agent.sh` via `subprocess.run()`. If invalid: send error message and ask to re-enter (don't change state). Verify: `/compare` shows formatted list, valid selection is acknowledged, invalid input shows re-entry prompt, second attempt works.

- [x] **B3: Add and remove commands.** Implement `/add <name>` handler: parse everything after `/add ` as the item name, call `master_list_manager.add_item()`, confirm to user with id, name, and instructions to edit JSON for brand/query tuning. Implement `/remove <id>` handler: parse id, look up item name, send confirmation request ("Remove #14 Toor Dal 1kg? Reply yes to confirm"), set `state[user_id] = {"step": "awaiting_remove_confirm", "item_id": id}`. On next message, if step is "awaiting_remove_confirm" and text is "yes" (case-insensitive), remove item and confirm. Any other response: cancel and inform. Verify: add, remove flow, invalid id on remove, cancellation works.

---

## Phase C: Browser automation (integration tests require live browser)

- [x] **C1: Playwright browser manager.** Create `src/browser_manager.py`. Function: `get_browser_context(profile_path)` uses `sync_playwright().start()` then `playwright.chromium.launch_persistent_context(profile_path, headless=True)`. Returns the context object. Function: `close_context(context, playwright_instance)` closes both. Store `playwright_instance` alongside context so it can be properly stopped. Do NOT use `with` statement — the context needs to persist across multiple function calls in the orchestrator. Smoke test `tests/test_browser_smoke.py` (marked `@pytest.mark.integration`): open persistent context from a test profile path, navigate to `https://example.com`, verify page title, close. Verify: smoke test passes when browser profile directory exists.

- [x] **C2: Amazon — location, search, and fee discovery.** Create `src/scraper_amazon.py`. Functions: `set_location(page, pincode)` — navigate to amazon.in, check current delivery address shown in the location widget. If it already contains the pincode, return True. Otherwise, click the location widget, enter the pincode, select the address, confirm. Return True on success, raise `RuntimeError` on failure. `search_items(page, query)` — type query in search bar, submit, wait for results page to load. `extract_results(page)` — from search results, extract a list of candidate dicts: `{"name": str, "price": float, "brand": str, "unit": str, "url": str}`. Skip sponsored results (detect by "Sponsored" label). Skip results with no visible price. `discover_fees_amazon(page)` — read delivery fee information from visible product listing cards or banners on the current page. Look for text patterns like "FREE delivery" with a threshold amount, and cashback banners. Return `{"delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [...]}`. If nothing found, return defaults (free above ₹99, ₹0 handling, no cashback). Also detect session expiry: if current URL contains "signin" or "login", return `{"status": "session_expired"}`. All functions marked `@pytest.mark.integration` in tests. Write integration tests in `tests/test_scrapers.py` for Amazon: test set_location works for 122001, test search returns results, test extract_results returns structured data, test session expiry detection. Verify: tests pass with a valid logged-in browser profile.

- [x] **C3: Blinkit — location, search, and fee discovery.** Add Blinkit functions to `src/scraper_blinkit.py`. `set_location(page, pincode)` — navigate to blinkit.com, handle location modal if present, set pincode to 122001. `dismiss_modals(page)` — dismiss app-install banners and any overlay modals. Must be called before searching. `search_items(page, query)` — use Blinkit's search. `extract_results(page)` — extract candidates: `{"name": str, "price": float, "brand": str, "unit": str}`. `discover_fees_blinkit(page)` — read fee thresholds from visible banners (e.g., "Free delivery above ₹X", "₹Y delivery fee"). If no banner found, navigate to cart page (without having added any items), read any visible fee structure text, navigate back. If no fee info visible anywhere, return defaults (₹25 delivery, ₹9 handling, free above ₹199, no cashback). Do NOT add items to the cart for fee discovery. Session expiry detection: check for login redirect. Write integration tests in `tests/test_scrapers.py` for Blinkit. Verify: tests pass with valid browser profile.

- [x] **C4: Match utils integration.** Add integration tests (marked `@pytest.mark.integration`) to verify `find_best_match()` works correctly with real scraped results from both platforms. Test: search "toor dal 1 kg" on both platforms, pass results to `find_best_match()`, verify a reasonable match is returned. Test: search for a brand-constrained item, verify brand filter works on real results. Verify: tests pass.

- [x] **C-SIMPLIFY: Code health pass for Phase C.** Review browser_manager, scraper_amazon, scraper_blinkit. Simplify without changing behavior. See PROMPT.md "SIMPLIFY tasks" rules.

- [x] **C-SYNC-DOCS: Documentation sync after Phase C.** Update docs to match actual scraper implementations, selectors, and any platform quirks discovered. See PROMPT.md "SYNC-DOCS tasks" rules.

---

## Phase D: Integration

- [x] **D1: Comparison orchestrator.** Create `src/orchestrator.py`. Accept command-line argument: `python3 src/orchestrator.py "1x2,4,5,8,12"`. Pipeline: (1) parse selection and load master list; (2) open browser context; (3) for each platform, run scraping loop (set location, dismiss modals, search each item, extract results, run find_best_match, discover fees); (4) on platform failure (RuntimeError or session_expired), record error and continue with other platform; (5) on two consecutive failures per platform, mark platform as unavailable; (6) compile price data; (7) call optimizer; (8) call formatter; (9) print formatted output to stdout; (10) log run to `logs/` and append to `price_history/prices.jsonl`; (11) close browser. Return exit code 0 on success, 1 on total failure (no platforms available). Write `tests/test_orchestrator.py` with mocked scrapers (monkeypatch the scraper functions): test successful pipeline, test single-platform failure (one platform session expired), test both platforms failed, test logging is called. Verify: tests pass.

- [x] **D2: Concurrency guard.** Add lockfile mechanism to `src/agent.sh`. Before invoking `claude -p`, check for `/tmp/grocery-agent.lock`. If it exists, output "LOCKED" to stdout and exit 0. If not, create the lock with `touch /tmp/grocery-agent.lock`, set a trap to remove it on exit (`trap 'rm -f /tmp/grocery-agent.lock' EXIT`), then proceed. In `telegram_bot.py`, if `agent.sh` outputs "LOCKED", send "A comparison is already running. Please wait and try again in a few minutes." to the user. Verify: run two concurrent agent.sh invocations, confirm the second outputs LOCKED and the first completes normally.

- [x] **D3: Agent prompt and claude -p bridge.** Create `src/agent_prompt.md` — the system prompt for the comparison agent when invoked via `claude -p`. It instructs Claude to: read the user's selection from the prompt, run `python3 src/orchestrator.py "<selection>"` using the Bash tool, capture stdout, and return it as the response. If the orchestrator exits with code 1, Claude reports the failure. If stdout is empty, Claude reports that no output was produced. The prompt must be concise (every token is context budget). Create `src/agent.sh`:
  ```bash
  #!/bin/bash
  set -euo pipefail
  SELECTION="${1:?Selection argument required}"
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

  # Concurrency guard
  LOCKFILE="/tmp/grocery-agent.lock"
  if [ -f "$LOCKFILE" ]; then
    echo "LOCKED"
    exit 0
  fi
  trap 'rm -f "$LOCKFILE"' EXIT
  touch "$LOCKFILE"

  cd "$PROJECT_ROOT"

  # Selection is regex-validated upstream (digits, x, commas only).
  # Pass via --append-system-prompt to avoid shell interpolation in the prompt string.
  result=$(timeout 900 claude -p "Compare grocery prices for the items selected by the user." \
    --append-system-prompt "$(cat src/agent_prompt.md)
User's item selection: ${SELECTION}" \
    --allowedTools "Bash" "Read" \
    --output-format text 2>&1) || result="ERROR: claude -p failed or timed out"

  echo "$result"
  ```
  Note: on macOS, replace `timeout` with `gtimeout`. Verify: invoke `agent.sh "1,2,3"` manually and confirm it produces output (with real or mocked orchestrator data).

- [x] **D4: Wire Telegram to agent.** Update `telegram_bot.py`: after receiving a valid selection, call `agent.sh` via `subprocess.run(["bash", "src/agent.sh", selection], capture_output=True, text=True, timeout=600)`. If subprocess raises `TimeoutExpired`, send "Comparison timed out after 10 minutes. The platforms may be slow — please try again." If stdout contains "LOCKED", send the locked message. If stdout contains "ERROR:", send "Something went wrong during the comparison. Check logs for details." Otherwise, pass stdout to `formatter.split_message()` and send each part as a Telegram message. Send a "still working..." follow-up message if 60 seconds have elapsed (use asyncio task with a delay). Verify: full flow from Telegram command to formatted response.

- [x] **D5: Logging.** Create `src/logger.py`. Function: `log_run(log_dir, run_data)` writes `logs/run_YYYYMMDD_HHMMSS.json` per the spec format. Function: `log_prices(history_dir, items_with_prices)` appends to `price_history/prices.jsonl`. For unavailable items: `price` is `null`, `brand` is `null`, `status` is `"unavailable"` or `"session_expired"`. Wire into `orchestrator.py`: call both at the end of every run regardless of success or failure. Write `tests/test_logger.py`: test log file is created with correct structure, test price history appends correctly, test null handling for unavailable items. Verify: tests pass.

- [x] **D6: Session expiry and error handling.** Update scraper modules: session expiry is already detected in C2/C3 — ensure the return format `{"status": "session_expired", "platform": "amazon"}` is propagated correctly up through orchestrator and into the Telegram message. Update orchestrator: if session_expired is returned for a platform, include a prominent message in the formatted output: "⚠️ Amazon session expired — please re-login in the browser profile." Add retry logic to all scraper navigation functions: wrap in a retry loop with 2 retries and 10-second pause. Final failure raises `RuntimeError`. Verify: simulate expired session by manually clearing cookies for one platform in the browser profile, confirm the correct message appears in Telegram.

- [x] **D7: End-to-end integration test.** With real browser profiles and both platforms logged in: send `/compare` via Telegram, select 5 items (mix of items available on both platforms and one available on only one platform), confirm the full output appears correctly in Telegram. Spot-check 2 prices manually against the platforms. Confirm log file is created. Confirm price history is appended. Document any layout changes or selector fixes needed. This is a manual test — no automated test file. Document results in a short comment in CLAUDE.md under "E2E Test Notes."

- [x] **D-SIMPLIFY: Code health pass for Phase D.** Review orchestrator, agent bridge, logger, and all integration wiring. Simplify without changing behavior. See PROMPT.md "SIMPLIFY tasks" rules.

- [ ] **D-SYNC-DOCS: Documentation sync after Phase D.** Full sync of all docs against the complete codebase. See PROMPT.md "SYNC-DOCS tasks" rules.

---

## Phase E: Edge cases and hardening

- [ ] **E1: Manual login and profile setup.** Create `setup_browser.sh`: launches Playwright with the persistent profile in **headed** (visible) mode so the user can manually log into Amazon and Blinkit. The script opens the browser, navigates to amazon.in and blinkit.com in separate tabs, then waits for the user to press Enter before closing. Document first-time setup process in a `SETUP.md` file. Verify: after manual login, headless runs can access logged-in pages.

- [ ] **E2: Edge case testing.** Test: single item selection. Test: all items unavailable on one platform (session expired). Test: one platform down (disable network to that domain). Test: large selection (20+ items — verify brute-force handles it or greedy kicks in). Test: brand-constrained item. Test: quantity `x` syntax (`1x3,4x2`). Test: Telegram message splitting with a very long output (15+ items to trigger table overflow splitting). Document results and fix any failures.

- [ ] **E3: Security and input hardening review.** Review `telegram_bot.py`: confirm ALLOWED_USER_ID check happens before ANY processing. Confirm selection string is shell-quoted when passed to `agent.sh`. Confirm `.env` is not readable by the agent (it's in project root, agent has Read tool — this is acceptable since the agent already has bash access; document this accepted risk in CLAUDE.md). Review `agent.sh`: confirm selection is passed via --append-system-prompt rather than interpolated into the main prompt string. Confirm lockfile trap covers all exit paths.

- [ ] **E-SIMPLIFY: Final code health pass.** Review the entire `src/` directory. Final simplification pass before project is considered complete. See PROMPT.md "SIMPLIFY tasks" rules.

- [ ] **E-SYNC-DOCS: Final documentation sync.** Comprehensive sync of all docs. Ensure SETUP.md, spec.md, CLAUDE.md all reflect the finished project. See PROMPT.md "SYNC-DOCS tasks" rules.
