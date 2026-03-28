"""Run logging and price history."""

import json
import os
from datetime import datetime


def log_run(log_dir, run_data):
    """Write a run log file to log_dir.

    Args:
        log_dir: Directory to write logs to (created if missing).
        run_data: Dict with keys: timestamp, selected_items, platforms,
                  recommendation, total_cost, run_duration_seconds.

    Returns:
        Path to the created log file.
    """
    os.makedirs(log_dir, exist_ok=True)
    ts = run_data.get("timestamp", datetime.now().isoformat())
    # Parse timestamp to build filename
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        dt = datetime.now()
    filename = f"run_{dt.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(log_dir, filename)
    with open(filepath, "w") as f:
        json.dump(run_data, f, indent=2)
    return filepath


def log_prices(history_dir, items_with_prices):
    """Append price records to prices.jsonl.

    Args:
        history_dir: Directory containing prices.jsonl (created if missing).
        items_with_prices: List of dicts, each with:
            - id, name: item identifiers
            - amazon: {"price": float, "brand": str} or None
            - blinkit: {"price": float, "brand": str} or None
            - amazon_status: optional, e.g. "unavailable" or "session_expired"
            - blinkit_status: optional, e.g. "unavailable" or "session_expired"

    Returns:
        Path to the prices.jsonl file.
    """
    os.makedirs(history_dir, exist_ok=True)
    filepath = os.path.join(history_dir, "prices.jsonl")
    today = datetime.now().strftime("%Y-%m-%d")

    with open(filepath, "a") as f:
        for item in items_with_prices:
            amazon = item.get("amazon")
            blinkit = item.get("blinkit")

            record = {
                "date": today,
                "item_id": item["id"],
                "item_name": item["name"],
                "amazon_price": amazon["price"] if amazon else None,
                "amazon_brand": amazon["brand"] if amazon else None,
                "blinkit_price": blinkit["price"] if blinkit else None,
                "blinkit_brand": blinkit["brand"] if blinkit else None,
            }

            # Add status fields for unavailable items
            if amazon is None:
                record["amazon_status"] = item.get("amazon_status", "unavailable")
            if blinkit is None:
                record["blinkit_status"] = item.get("blinkit_status", "unavailable")

            f.write(json.dumps(record) + "\n")

    return filepath
