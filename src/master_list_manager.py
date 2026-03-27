import json


def _read_file(filepath):
    """Read raw JSON from file. Handles both list format (legacy) and object format."""
    with open(filepath, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        # Legacy format: bare list. Compute next_id from max existing.
        next_id = max((item["id"] for item in data), default=0) + 1
        return {"items": data, "_next_id": next_id}
    return data


def _write_file(filepath, store):
    with open(filepath, "w") as f:
        json.dump(store, f, indent=2)


def load_list(filepath):
    """Load master list from JSON file. Returns list of items."""
    return _read_file(filepath)["items"]


def add_item(filepath, name, category="uncategorized"):
    """Add item with auto-incremented id. Returns the new item dict."""
    store = _read_file(filepath)
    new_id = store["_next_id"]
    new_item = {
        "id": new_id,
        "name": name,
        "query": name,
        "brand": None,
        "category": category,
    }
    store["items"].append(new_item)
    store["_next_id"] = new_id + 1
    _write_file(filepath, store)
    return new_item


def remove_item(filepath, item_id):
    """Remove item by id. Returns True if removed, raises ValueError if not found."""
    store = _read_file(filepath)
    items = store["items"]
    for i, item in enumerate(items):
        if item["id"] == item_id:
            items.pop(i)
            _write_file(filepath, store)
            return True
    raise ValueError(f"Item with id {item_id} not found")


def get_item(filepath, item_id):
    """Return single item dict or None if not found."""
    items = load_list(filepath)
    for item in items:
        if item["id"] == item_id:
            return item
    return None
