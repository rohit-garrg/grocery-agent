import json
import pytest
from src.master_list_manager import load_list, add_item, remove_item, get_item


@pytest.fixture
def empty_list(tmp_path):
    filepath = tmp_path / "master_list.json"
    filepath.write_text("[]")
    return str(filepath)


@pytest.fixture
def populated_list(tmp_path):
    filepath = tmp_path / "master_list.json"
    items = [
        {"id": 1, "name": "Toor Dal 1kg", "query": "Toor Dal 1kg", "brand": None, "category": "pulses"},
        {"id": 2, "name": "Amul Butter 500g", "query": "Amul Butter 500g", "brand": None, "category": "dairy"},
        {"id": 3, "name": "Rice 5kg", "query": "Rice 5kg", "brand": None, "category": "grains"},
    ]
    filepath.write_text(json.dumps(items, indent=2))
    return str(filepath)


def test_load_empty_file(empty_list):
    assert load_list(empty_list) == []


def test_load_file_with_items(populated_list):
    items = load_list(populated_list)
    assert len(items) == 3
    assert items[0]["name"] == "Toor Dal 1kg"


def test_add_to_empty_list(empty_list):
    item = add_item(empty_list, "Milk 1L", category="dairy")
    assert item["id"] == 1
    assert item["name"] == "Milk 1L"
    assert item["query"] == "Milk 1L"
    assert item["brand"] is None
    assert item["category"] == "dairy"
    assert len(load_list(empty_list)) == 1


def test_add_to_nonempty_list(populated_list):
    item = add_item(populated_list, "Ghee 1L")
    assert item["id"] == 4
    assert item["category"] == "uncategorized"
    assert len(load_list(populated_list)) == 4


def test_remove_existing_item(populated_list):
    assert remove_item(populated_list, 2) is True
    items = load_list(populated_list)
    assert len(items) == 2
    assert all(item["id"] != 2 for item in items)


def test_remove_nonexistent_item(populated_list):
    with pytest.raises(ValueError, match="not found"):
        remove_item(populated_list, 99)


def test_get_existing_item(populated_list):
    item = get_item(populated_list, 2)
    assert item is not None
    assert item["name"] == "Amul Butter 500g"


def test_get_nonexistent_item(populated_list):
    assert get_item(populated_list, 99) is None


def test_id_never_reused(populated_list):
    """After deleting id 3, the next add should get id 4, not 3."""
    remove_item(populated_list, 3)
    new_item = add_item(populated_list, "Sugar 1kg")
    assert new_item["id"] == 4
