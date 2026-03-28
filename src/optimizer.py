import logging

logger = logging.getLogger(__name__)

PLATFORMS = ("amazon", "blinkit")


def _compute_platform_cost(subtotal, fees):
    """Compute delivery fee, handling fee, cashback, and total for a platform."""
    delivery_fee = fees["delivery_fee"]
    threshold = fees.get("free_delivery_threshold")
    if threshold is not None and subtotal >= threshold:
        delivery_fee = 0.0

    handling_fee = fees["handling_fee"]

    cashback = 0.0
    for tier in sorted(fees.get("cashback_tiers", []), key=lambda t: t["min_order"], reverse=True):
        if subtotal >= tier["min_order"]:
            cashback = tier["cashback"]
            break

    total = subtotal + delivery_fee + handling_fee - cashback
    return delivery_fee, handling_fee, cashback, total


def _evaluate_assignment(items, assignment, platform_fees):
    """Evaluate a specific assignment of dual-platform items.

    Args:
        items: All items (pre-assigned + dual).
        assignment: Dict mapping item id -> platform name for dual-platform items.
        platform_fees: Fee structures per platform.

    Returns:
        Dict with per-platform breakdowns and combined total.
    """
    platform_items = {"amazon": [], "blinkit": []}
    platform_subtotals = {"amazon": 0.0, "blinkit": 0.0}

    for item in items:
        prices = item["prices"]
        amazon_avail = prices.get("amazon") is not None
        blinkit_avail = prices.get("blinkit") is not None

        if amazon_avail and not blinkit_avail:
            platform = "amazon"
        elif blinkit_avail and not amazon_avail:
            platform = "blinkit"
        else:
            platform = assignment[item["id"]]

        price_info = prices[platform]
        line_cost = price_info["price"] * item["qty"]
        platform_items[platform].append(item)
        platform_subtotals[platform] += line_cost

    result = {}
    combined = 0.0
    total_fees = 0.0
    total_item_cost = sum(platform_subtotals.values())

    for p in PLATFORMS:
        sub = platform_subtotals[p]
        if sub > 0 or platform_items[p]:
            d_fee, h_fee, cb, ptotal = _compute_platform_cost(sub, platform_fees[p])
        else:
            d_fee, h_fee, cb, ptotal = 0.0, 0.0, 0.0, 0.0

        result[f"{p}_subtotal"] = sub
        result[f"{p}_delivery_fee"] = d_fee
        result[f"{p}_handling_fee"] = h_fee
        result[f"{p}_cashback"] = cb
        result[f"{p}_total"] = ptotal
        combined += ptotal
        total_fees += d_fee + h_fee

    result["recommendation"] = platform_items
    result["combined_total"] = combined
    result["fee_warning"] = total_item_cost > 0 and total_fees > 0.2 * total_item_cost

    return result


def _all_platform_total(items, platform, platform_fees):
    """Compute total if all items ordered from a single platform. Returns None if any item unavailable."""
    subtotal = 0.0
    for item in items:
        price_info = item["prices"].get(platform)
        if price_info is None:
            return None
        subtotal += price_info["price"] * item["qty"]

    _, _, _, total = _compute_platform_cost(subtotal, platform_fees[platform])
    return total


def optimize_cart(items, platform_fees):
    """Find the optimal cart split across platforms.

    Args:
        items: List of {"id", "name", "qty", "prices": {"amazon": {"price", "brand"} | None, "blinkit": ...}}.
        platform_fees: {"amazon": {"delivery_fee", "handling_fee", "free_delivery_threshold", "cashback_tiers"}, "blinkit": ...}.

    Returns:
        Dict with recommendation, per-platform breakdowns, combined total, single-platform alternatives, savings.
    """
    dual_items = []
    for item in items:
        prices = item["prices"]
        amazon_avail = prices.get("amazon") is not None
        blinkit_avail = prices.get("blinkit") is not None
        if amazon_avail and blinkit_avail:
            dual_items.append(item)

    n = len(dual_items)

    if n > 20:
        logger.warning("N=%d dual-platform items exceeds 20, using greedy heuristic", n)
        best = _greedy_assignment(items, dual_items, platform_fees)
    else:
        best = _bruteforce_assignment(items, dual_items, platform_fees)

    # Compute single-platform alternatives
    all_amazon = _all_platform_total(items, "amazon", platform_fees)
    all_blinkit = _all_platform_total(items, "blinkit", platform_fees)

    best["all_amazon_total"] = all_amazon
    best["all_blinkit_total"] = all_blinkit

    # Savings vs best single-platform option
    single_totals = [t for t in [all_amazon, all_blinkit] if t is not None]
    if single_totals:
        best_single = min(single_totals)
        best["savings"] = max(0.0, best_single - best["combined_total"])
    else:
        best["savings"] = 0.0

    return best


def _bruteforce_assignment(items, dual_items, platform_fees):
    """Try all 2^N assignments for dual-platform items."""
    n = len(dual_items)
    best_result = None
    best_total = float("inf")

    for mask in range(1 << n):
        assignment = {}
        for i, item in enumerate(dual_items):
            assignment[item["id"]] = "blinkit" if (mask >> i) & 1 else "amazon"

        result = _evaluate_assignment(items, assignment, platform_fees)
        if result["combined_total"] < best_total:
            best_total = result["combined_total"]
            best_result = result

    # Edge case: no dual items means mask=0 is the only iteration, which is correct
    return best_result


def _greedy_assignment(items, dual_items, platform_fees):
    """Assign each dual item to its cheaper platform, then check consolidation."""
    # Greedy: each item to cheapest
    greedy_assign = {}
    for item in dual_items:
        a_price = item["prices"]["amazon"]["price"]
        b_price = item["prices"]["blinkit"]["price"]
        greedy_assign[item["id"]] = "amazon" if a_price <= b_price else "blinkit"

    best_result = _evaluate_assignment(items, greedy_assign, platform_fees)
    best_total = best_result["combined_total"]

    # Check: all dual to amazon
    all_amazon_assign = {item["id"]: "amazon" for item in dual_items}
    result = _evaluate_assignment(items, all_amazon_assign, platform_fees)
    if result["combined_total"] < best_total:
        best_total = result["combined_total"]
        best_result = result

    # Check: all dual to blinkit
    all_blinkit_assign = {item["id"]: "blinkit" for item in dual_items}
    result = _evaluate_assignment(items, all_blinkit_assign, platform_fees)
    if result["combined_total"] < best_total:
        best_result = result

    return best_result
