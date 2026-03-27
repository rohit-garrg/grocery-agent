import re


def parse_selection(input_string, valid_ids):
    """Parse selection string like '1x2,4,5x3' into list of {id, qty} dicts.

    Args:
        input_string: Comma-separated items, optional NxQ quantity syntax.
        valid_ids: Collection of valid integer ids.

    Returns:
        List of {"id": int, "qty": int} dicts.

    Raises:
        ValueError: On any invalid input.
    """
    text = input_string.strip()
    if not text:
        raise ValueError("Selection is empty")

    if not re.match(r"^\d+(x\d+)?(,\d+(x\d+)?)*$", text):
        raise ValueError(
            "Invalid format. Use comma-separated item numbers, "
            "with optional quantity (e.g., 1x2,4,5x3)"
        )

    valid_id_set = set(int(v) for v in valid_ids)
    seen_ids = set()
    result = []

    for token in text.split(","):
        if "x" in token:
            parts = token.split("x")
            item_id = int(parts[0])
            qty = int(parts[1])
        else:
            item_id = int(token)
            qty = 1

        if qty <= 0:
            raise ValueError(f"Quantity must be positive, got {qty} for item {item_id}")

        if item_id not in valid_id_set:
            raise ValueError(f"Unknown item id: {item_id}")

        if item_id in seen_ids:
            raise ValueError(f"Duplicate item id: {item_id}")

        seen_ids.add(item_id)
        result.append({"id": item_id, "qty": qty})

    return result
