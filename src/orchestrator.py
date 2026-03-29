"""Comparison pipeline coordinator.

Run as: python3 src/orchestrator.py "1x2,4,5,8,12"
Exits 0 on success, 1 on total failure (no platforms available).
"""

import os
import random
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from selection_parser import parse_selection
from master_list_manager import load_list
from browser_manager import get_browser_context, close_context
from match_utils import find_best_match
from optimizer import optimize_cart
from formatter import format_comparison, format_unavailable

import scraper_amazon
import scraper_blinkit
from logger import log_run, log_prices

MASTER_LIST_PATH = os.path.join(os.path.dirname(__file__), "..", "master_list.json")
BROWSER_PROFILE_PATH = os.environ.get("BROWSER_PROFILE_PATH", "browser_profile")
PINCODE = os.environ.get("PINCODE", "122001")
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
PRICE_HISTORY_DIR = os.path.join(os.path.dirname(__file__), "..", "price_history")

DEFAULT_FEES = {
    "amazon": {
        "delivery_fee": 40,
        "handling_fee": 0,
        "free_delivery_threshold": 99.0,
        "cashback_tiers": [],
    },
    "blinkit": {
        "delivery_fee": 25,
        "handling_fee": 9,
        "free_delivery_threshold": 199.0,
        "cashback_tiers": [],
    },
}


def _retry(fn, *args, retries=2, pause=10, **kwargs):
    """Call fn with retry on RuntimeError. Session expiry is never retried."""
    last_error = None
    for attempt in range(1 + retries):
        try:
            return fn(*args, **kwargs)
        except RuntimeError as e:
            if "session expired" in str(e).lower():
                raise
            last_error = e
            if attempt < retries:
                time.sleep(pause)
    raise last_error


def _scrape_platform(platform, page, items, pincode):
    """Scrape prices and fees for one platform.

    Args:
        platform: "amazon" or "blinkit".
        page: Playwright page object.
        items: List of master list items to search for.
        pincode: Delivery pincode string.

    Returns:
        (prices_dict, fees_dict, errors_list) where:
        - prices_dict maps item_id -> {"price": float, "brand": str} or None
        - fees_dict is the fee structure for the platform
        - errors_list contains error messages for any failures
    """
    scraper = scraper_amazon if platform == "amazon" else scraper_blinkit
    prices = {}
    fees = dict(DEFAULT_FEES[platform])
    errors = []
    consecutive_failures = 0

    # Set location (with retry)
    try:
        _retry(scraper.set_location, page, pincode)
        consecutive_failures = 0
    except RuntimeError as e:
        msg = str(e)
        if "session expired" in msg.lower():
            return prices, {"status": "session_expired", "platform": platform}, [msg]
        errors.append(f"{platform} location error: {msg}")
        consecutive_failures += 1

    # Dismiss modals (no-op on Amazon, dismisses banners on Blinkit)
    scraper.dismiss_modals(page)

    # Scrape each item
    for item in items:
        if consecutive_failures >= 2:
            errors.append(f"{platform}: marked unavailable after 2 consecutive failures")
            break

        query = item.get("query", item["name"])
        brand_constraint = item.get("brand")

        try:
            _retry(scraper.search_items, page, query)
            candidates = scraper.extract_results(page)
            match = find_best_match(candidates, query, brand_constraint)
            if match:
                prices[item["id"]] = {"price": match["price"], "brand": match.get("brand", "")}
            else:
                prices[item["id"]] = None
            consecutive_failures = 0
        except RuntimeError as e:
            msg = str(e)
            if "session expired" in msg.lower():
                return prices, {"status": "session_expired", "platform": platform}, [msg]
            errors.append(f"{platform} error for '{item['name']}': {msg}")
            prices[item["id"]] = None
            consecutive_failures += 1

        # Anti-bot-detection: random delay between searches
        time.sleep(random.uniform(2, 5))

    # Discover fees (with retry)
    try:
        discovered = _retry(scraper.discover_fees, page)

        if isinstance(discovered, dict) and discovered.get("status") == "session_expired":
            return prices, {"status": "session_expired", "platform": platform}, errors
        fees.update(discovered)
    except RuntimeError as e:
        errors.append(f"{platform} fee discovery error: {e}")

    return prices, fees, errors


def _log_all(selection, selected_items, platform_results, platform_fees,
             expired_platforms, optimizer_result, start_time):
    """Log run data and price history. Never raises — errors are printed to stderr."""
    try:
        duration = round(time.time() - start_time)
        timestamp = datetime.now().isoformat()

        # Build platform status for run log
        platforms_log = {}
        for platform in ("amazon", "blinkit"):
            prices = platform_results.get(platform, {})
            fees = platform_fees.get(platform, {})
            if platform in expired_platforms:
                platforms_log[platform] = {"status": "session_expired"}
            else:
                found = sum(1 for v in prices.values() if v is not None)
                not_found = sum(1 for v in prices.values() if v is None)
                platforms_log[platform] = {
                    "status": "success",
                    "items_found": found,
                    "items_not_found": not_found,
                    "fees": fees,
                    "session_valid": True,
                }

        run_data = {
            "timestamp": timestamp,
            "selected_items": [{"id": s["id"], "qty": s["qty"]} for s in selection],
            "platforms": platforms_log,
            "recommendation": optimizer_result.get("recommendation", {}) if optimizer_result else {},
            "total_cost": optimizer_result.get("combined_total", 0) if optimizer_result else 0,
            "run_duration_seconds": duration,
        }
        log_run(os.path.abspath(LOG_DIR), run_data)

        # Build price history records
        price_items = []
        for item in selected_items:
            amazon_data = platform_results.get("amazon", {}).get(item["id"])
            blinkit_data = platform_results.get("blinkit", {}).get(item["id"])

            record = {"id": item["id"], "name": item["name"],
                      "amazon": amazon_data, "blinkit": blinkit_data}

            if amazon_data is None:
                record["amazon_status"] = "session_expired" if "amazon" in expired_platforms else "unavailable"

            if blinkit_data is None:
                record["blinkit_status"] = "session_expired" if "blinkit" in expired_platforms else "unavailable"

            price_items.append(record)

        log_prices(os.path.abspath(PRICE_HISTORY_DIR), price_items)
    except Exception as e:
        # Logging must never break the pipeline
        print(f"Warning: logging failed: {e}", file=sys.stderr)


def run_comparison(selection_string):
    """Run the full comparison pipeline.

    Args:
        selection_string: e.g. "1x2,4,5,8,12"

    Returns:
        (output_text, exit_code) where output_text is the formatted result string
        and exit_code is 0 on success, 1 on total failure.
    """
    start_time = time.time()

    # Daily run limit: safety throttle to prevent excessive automated requests
    today = datetime.now().strftime("%Y%m%d")
    log_dir_abs = os.path.abspath(LOG_DIR)
    if os.path.isdir(log_dir_abs):
        today_runs = [f for f in os.listdir(log_dir_abs) if f.startswith(f"run_{today}") and f.endswith(".json")]
        if len(today_runs) >= 3:
            return "Daily limit reached (3 comparisons per day). Try again tomorrow.", 0

    # Step 1: Parse selection and load master list
    master_list = load_list(os.path.abspath(MASTER_LIST_PATH))
    valid_ids = [item["id"] for item in master_list]
    selection = parse_selection(selection_string, valid_ids)

    # Resolve items with quantities
    item_map = {item["id"]: item for item in master_list}
    selected_items = []
    for sel in selection:
        item = item_map[sel["id"]]
        selected_items.append({
            "id": item["id"],
            "name": item["name"],
            "query": item.get("query", item["name"]),
            "brand": item.get("brand"),
            "qty": sel["qty"],
        })

    # Step 2: Open browser context
    context, pw = get_browser_context(os.path.abspath(BROWSER_PROFILE_PATH))

    try:
        platform_results = {}
        platform_fees = {}
        platform_errors = {}
        session_warnings = []
        expired_platforms = set()

        # Step 3: Scrape each platform
        platforms = ("amazon", "blinkit")
        for idx, platform in enumerate(platforms):
            # Anti-bot-detection: random delay between switching platforms
            if idx > 0:
                time.sleep(random.uniform(3, 8))

            page = context.new_page()
            try:
                prices, fees, errors = _scrape_platform(platform, page, selected_items, PINCODE)
                platform_results[platform] = prices
                platform_errors[platform] = errors

                if isinstance(fees, dict) and fees.get("status") == "session_expired":
                    display = "Amazon" if platform == "amazon" else "Blinkit"
                    session_warnings.append(
                        f"\u26a0\ufe0f {display} session expired \u2014 please re-login in the browser profile."
                    )
                    expired_platforms.add(platform)
                    platform_fees[platform] = dict(DEFAULT_FEES[platform])
                    # Mark all items as unavailable for this platform
                    for item in selected_items:
                        platform_results[platform][item["id"]] = None
                else:
                    platform_fees[platform] = fees
            except Exception as e:
                platform_errors[platform] = [f"{platform} scraping failed unexpectedly: {e}"]
                platform_results[platform] = {item["id"]: None for item in selected_items}
                platform_fees[platform] = dict(DEFAULT_FEES[platform])
            finally:
                page.close()

        # Step 4: Check if any platform is available
        amazon_available = any(
            v is not None for v in platform_results.get("amazon", {}).values()
        )
        blinkit_available = any(
            v is not None for v in platform_results.get("blinkit", {}).values()
        )

        if not amazon_available and not blinkit_available:
            output_parts = ["No platforms available. Could not fetch prices from any platform."]
            if session_warnings:
                output_parts.extend([""] + session_warnings)
            for p, errs in platform_errors.items():
                for err in errs:
                    output_parts.append(err)
            _log_all(selection, selected_items, platform_results, platform_fees,
                     expired_platforms, None, start_time)
            return "\n".join(output_parts), 1

        # Step 5: Compile price data for optimizer
        optimizer_items = []
        unavailable_items = []
        for item in selected_items:
            amazon_price = platform_results.get("amazon", {}).get(item["id"])
            blinkit_price = platform_results.get("blinkit", {}).get(item["id"])

            if amazon_price is None and blinkit_price is None:
                unavailable_items.append(item)
                continue

            optimizer_items.append({
                "id": item["id"],
                "name": item["name"],
                "qty": item["qty"],
                "prices": {
                    "amazon": amazon_price,
                    "blinkit": blinkit_price,
                },
            })

        # Step 6: Optimize
        if optimizer_items:
            result = optimize_cart(optimizer_items, platform_fees)
        else:
            _log_all(selection, selected_items, platform_results, platform_fees,
                     expired_platforms, None, start_time)
            return "No items could be found on any platform.", 1

        # Step 7: Format output
        output = format_comparison(result, optimizer_items)

        if unavailable_items:
            unavail_text = format_unavailable(unavailable_items)
            if unavail_text:
                output = output + "\n\n" + unavail_text

        if session_warnings:
            output = output + "\n\n" + "\n".join(session_warnings)

        # Step 8: Logging
        _log_all(selection, selected_items, platform_results, platform_fees,
                 expired_platforms, result, start_time)

        return output, 0

    finally:
        # Step 9: Close browser
        close_context(context, pw)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 src/orchestrator.py \"1x2,4,5,8,12\"", file=sys.stderr)
        sys.exit(1)

    selection_string = sys.argv[1]

    try:
        output, exit_code = run_comparison(selection_string)
        print(output)
        sys.exit(exit_code)
    except ValueError as e:
        print(f"Input error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
