"""Comparison pipeline coordinator.

Run as: python3 src/orchestrator.py "1x2,4,5,8,12"
Exits 0 on success, 1 on total failure (no platforms available).
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from selection_parser import parse_selection
from master_list_manager import load_list
from browser_manager import get_browser_context, close_context
from match_utils import find_best_match
from optimizer import optimize_cart
from formatter import format_comparison, format_unavailable, split_message

import scraper_amazon
import scraper_blinkit

MASTER_LIST_PATH = os.path.join(os.path.dirname(__file__), "..", "master_list.json")
BROWSER_PROFILE_PATH = os.environ.get("BROWSER_PROFILE_PATH", "browser_profile")
PINCODE = os.environ.get("PINCODE", "122001")

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

    # Set location
    try:
        scraper.set_location(page, pincode)
        consecutive_failures = 0
    except RuntimeError as e:
        msg = str(e)
        if "session expired" in msg.lower():
            return prices, {"status": "session_expired", "platform": platform}, [msg]
        errors.append(f"{platform} location error: {msg}")
        consecutive_failures += 1

    # Dismiss modals (Blinkit)
    if platform == "blinkit":
        scraper_blinkit.dismiss_modals(page)

    # Scrape each item
    for item in items:
        if consecutive_failures >= 2:
            errors.append(f"{platform}: marked unavailable after 2 consecutive failures")
            break

        query = item.get("query", item["name"])
        brand_constraint = item.get("brand")

        try:
            scraper.search_items(page, query)
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

    # Discover fees
    try:
        if platform == "amazon":
            discovered = scraper_amazon.discover_fees_amazon(page)
        else:
            discovered = scraper_blinkit.discover_fees_blinkit(page)

        if isinstance(discovered, dict) and discovered.get("status") == "session_expired":
            return prices, {"status": "session_expired", "platform": platform}, errors
        fees = discovered
    except Exception as e:
        errors.append(f"{platform} fee discovery error: {e}")

    return prices, fees, errors


def run_comparison(selection_string):
    """Run the full comparison pipeline.

    Args:
        selection_string: e.g. "1x2,4,5,8,12"

    Returns:
        (output_text, exit_code) where output_text is the formatted result string
        and exit_code is 0 on success, 1 on total failure.
    """
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
        start_time = time.time()
        platform_results = {}
        platform_fees = {}
        platform_errors = {}
        session_warnings = []

        # Step 3: Scrape each platform
        for platform in ("amazon", "blinkit"):
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
                    platform_fees[platform] = dict(DEFAULT_FEES[platform])
                    # Mark all items as unavailable for this platform
                    for item in selected_items:
                        platform_results[platform][item["id"]] = None
                else:
                    platform_fees[platform] = fees
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
            return "No items could be found on any platform.", 1

        # Step 7: Format output
        # item_details for formatter includes all items (optimizer items)
        item_details = optimizer_items
        output = format_comparison(result, item_details)

        if unavailable_items:
            unavail_text = format_unavailable(unavailable_items)
            if unavail_text:
                output = output + "\n\n" + unavail_text

        if session_warnings:
            output = output + "\n\n" + "\n".join(session_warnings)

        # Step 8: Split for Telegram and output
        messages = split_message(output)

        duration = time.time() - start_time

        # Step 9: Logging (wired in D5 when logger.py is created)
        # log_run() and log_prices() will be called here

        return "\n---\n".join(messages), 0

    finally:
        # Step 10: Close browser
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
