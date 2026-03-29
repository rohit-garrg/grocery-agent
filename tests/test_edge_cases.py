"""Edge case tests for the grocery comparison pipeline (E2).

Tests cover:
- Single item selection (through orchestrator)
- All items unavailable on one platform (session expired)
- One platform down (persistent RuntimeErrors)
- Large selection (20+ items, greedy fallback)
- Brand-constrained items through the pipeline
- Quantity x syntax through the pipeline
- Telegram message splitting with long output (15+ items)
"""

import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator import run_comparison
from optimizer import optimize_cart
from formatter import format_comparison, split_message
from selection_parser import parse_selection
from match_utils import find_best_match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_master_list(tmp_path, items):
    path = tmp_path / "master_list.json"
    path.write_text(json.dumps(items, indent=2))
    return str(path)


def _make_master_item(id, name, query=None, brand=None, category="uncategorized"):
    return {
        "id": id,
        "name": name,
        "query": query or name.lower(),
        "brand": brand,
        "category": category,
    }


def _make_optimizer_item(id, name, qty, amazon_price=None, blinkit_price=None,
                         amazon_brand="", blinkit_brand=""):
    prices = {}
    if amazon_price is not None:
        prices["amazon"] = {"price": amazon_price, "brand": amazon_brand}
    if blinkit_price is not None:
        prices["blinkit"] = {"price": blinkit_price, "brand": blinkit_brand}
    return {"id": id, "name": name, "qty": qty, "prices": prices}


def _default_fees():
    return {
        "amazon": {
            "delivery_fee": 40.0,
            "handling_fee": 0.0,
            "free_delivery_threshold": 99.0,
            "cashback_tiers": [],
        },
        "blinkit": {
            "delivery_fee": 25.0,
            "handling_fee": 9.0,
            "free_delivery_threshold": 199.0,
            "cashback_tiers": [],
        },
    }


# Fake Playwright objects for orchestrator tests
class FakePage:
    def close(self):
        pass

class FakeContext:
    def new_page(self):
        return FakePage()
    def close(self):
        pass

class FakePlaywright:
    def stop(self):
        pass


@pytest.fixture
def orchestrator_env(tmp_path, monkeypatch):
    """Set up environment for orchestrator-level edge case tests."""
    profile_path = str(tmp_path / "browser_profile")
    os.makedirs(profile_path, exist_ok=True)

    monkeypatch.setattr("orchestrator.BROWSER_PROFILE_PATH", profile_path)
    monkeypatch.setattr("orchestrator.LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("orchestrator.PRICE_HISTORY_DIR", str(tmp_path / "price_history"))
    monkeypatch.setattr("orchestrator.PINCODE", "122001")
    monkeypatch.setattr("orchestrator.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "orchestrator.get_browser_context",
        lambda path: (FakeContext(), FakePlaywright()),
    )
    monkeypatch.setattr("orchestrator.close_context", lambda ctx, pw: None)

    return tmp_path


def _setup_master_list(orchestrator_env, monkeypatch, items):
    ml_path = _write_master_list(orchestrator_env, items)
    monkeypatch.setattr("orchestrator.MASTER_LIST_PATH", ml_path)
    return ml_path


# ---------------------------------------------------------------------------
# 1. Single item selection
# ---------------------------------------------------------------------------

class TestSingleItemSelection:
    def test_single_item_only_on_one_platform(self, orchestrator_env, monkeypatch):
        """Single item available only on Amazon produces valid output."""
        items = [_make_master_item(1, "Olive Oil 1L", "olive oil 1l")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Figaro Olive Oil 1L", "price": 449.0, "brand": "Figaro", "unit": "1L", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 40, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1")
        assert exit_code == 0
        assert "Olive Oil" in output
        assert "RECOMMENDED SPLIT" in output

    def test_single_item_cheapest_platform_selected(self, orchestrator_env, monkeypatch):
        """With a single item on both platforms, the cheaper one wins."""
        items = [_make_master_item(1, "Butter 500g", "amul butter 500g")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Amul Butter 500g", "price": 295.0, "brand": "Amul", "unit": "500g", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Amul Butter 500g", "price": 280.0, "brand": "Amul", "unit": "500g"},
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1")
        assert exit_code == 0
        assert "Butter" in output
        # Blinkit: 280 + 0 delivery (280 >= 199 threshold) + 9 handling = 289
        # Amazon: 295 + 0 = 295. Blinkit wins.
        assert "From Blinkit" in output


# ---------------------------------------------------------------------------
# 2. All items unavailable on one platform (session expired)
# ---------------------------------------------------------------------------

class TestAllItemsUnavailableOnePlatform:
    def test_session_expired_still_returns_results(self, orchestrator_env, monkeypatch):
        """When one platform session is expired, the other platform's results are returned."""
        items = [
            _make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg"),
            _make_master_item(2, "Rice 5kg", "basmati rice 5kg"),
            _make_master_item(3, "Butter 500g", "amul butter 500g"),
        ]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        # Amazon: session expired
        monkeypatch.setattr("orchestrator.scraper_amazon.set_location",
                            lambda p, pin: (_ for _ in ()).throw(RuntimeError("session expired")))
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {})

        # Blinkit: works fine
        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Toor Dal 1kg", "price": 128.0, "brand": "Tata", "unit": "1kg"},
            {"name": "Basmati Rice 5kg", "price": 450.0, "brand": "India Gate", "unit": "5kg"},
            {"name": "Amul Butter 500g", "price": 290.0, "brand": "Amul", "unit": "500g"},
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1,2,3")
        assert exit_code == 0
        assert "session expired" in output.lower()
        assert "Toor Dal" in output
        # All items should show N/A for Amazon in the comparison table
        assert "N/A" in output

    def test_all_items_na_on_working_platform_returns_failure(self, orchestrator_env, monkeypatch):
        """Both platforms alive but no items found on either returns exit code 1."""
        items = [_make_master_item(1, "Exotic Truffle Oil 250ml", "exotic truffle oil 250ml")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        for scraper in ("scraper_amazon", "scraper_blinkit"):
            monkeypatch.setattr(f"orchestrator.{scraper}.set_location", lambda p, pin: True)
            monkeypatch.setattr(f"orchestrator.{scraper}.dismiss_modals", lambda p: None)
            monkeypatch.setattr(f"orchestrator.{scraper}.search_items", lambda p, q: None)
            monkeypatch.setattr(f"orchestrator.{scraper}.extract_results", lambda p: [])
            monkeypatch.setattr(f"orchestrator.{scraper}.discover_fees", lambda p: {
                "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
            })

        output, exit_code = run_comparison("1")
        assert exit_code == 1


# ---------------------------------------------------------------------------
# 3. One platform down (persistent RuntimeErrors, not session expiry)
# ---------------------------------------------------------------------------

class TestOnePlatformDown:
    def test_amazon_down_blinkit_works(self, orchestrator_env, monkeypatch):
        """Amazon throws RuntimeErrors on every call; Blinkit still returns results."""
        items = [
            _make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg"),
            _make_master_item(2, "Butter 500g", "amul butter 500g"),
        ]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        # Amazon: all calls fail with RuntimeError (not session expiry)
        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items",
                            lambda p, q: (_ for _ in ()).throw(RuntimeError("Network timeout")))
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 40, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        # Blinkit: works fine
        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Toor Dal 1kg", "price": 128.0, "brand": "Tata", "unit": "1kg"},
            {"name": "Amul Butter 500g", "price": 290.0, "brand": "Amul", "unit": "500g"},
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1,2")
        assert exit_code == 0
        assert "Toor Dal" in output
        assert "Butter" in output

    def test_blinkit_down_amazon_works(self, orchestrator_env, monkeypatch):
        """Blinkit throws persistent errors; Amazon still returns results."""
        items = [_make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        # Amazon works
        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata", "unit": "1kg", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        # Blinkit: set_location fails permanently
        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location",
                            lambda p, pin: (_ for _ in ()).throw(RuntimeError("Page load timeout")))
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1")
        assert exit_code == 0
        assert "Toor Dal" in output


# ---------------------------------------------------------------------------
# 4. Large selection (20+ items, greedy fallback)
# ---------------------------------------------------------------------------

class TestLargeSelection:
    def test_greedy_fallback_22_dual_items(self, caplog):
        """22 dual-platform items triggers greedy and produces valid result."""
        items = [
            _make_optimizer_item(i, f"Item {i}", 1,
                                 amazon_price=100 + i, blinkit_price=100 + (22 - i),
                                 amazon_brand="Brand", blinkit_brand="Brand")
            for i in range(1, 23)
        ]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["handling_fee"] = 0.0

        with caplog.at_level(logging.WARNING):
            result = optimize_cart(items, fees)

        assert "greedy" in caplog.text.lower()
        assert result["combined_total"] > 0
        total_assigned = (len(result["recommendation"]["amazon"])
                          + len(result["recommendation"]["blinkit"]))
        assert total_assigned == 22

    def test_large_selection_through_orchestrator(self, orchestrator_env, monkeypatch):
        """22 items through the full orchestrator pipeline with mocked scrapers."""
        items = [_make_master_item(i, f"Item {i}", f"item {i}") for i in range(1, 23)]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        def make_extract(base_price):
            def extract(page):
                return [{"name": f"Item {i}", "price": base_price + i, "brand": "B", "unit": ""}
                        for i in range(1, 23)]
            return extract

        # Both platforms return results for all items
        for prefix, base in [("scraper_amazon", 100), ("scraper_blinkit", 105)]:
            monkeypatch.setattr(f"orchestrator.{prefix}.set_location", lambda p, pin: True)
            monkeypatch.setattr(f"orchestrator.{prefix}.dismiss_modals", lambda p: None)
            monkeypatch.setattr(f"orchestrator.{prefix}.search_items", lambda p, q: None)
            monkeypatch.setattr(f"orchestrator.{prefix}.extract_results", make_extract(base))
            monkeypatch.setattr(f"orchestrator.{prefix}.discover_fees", lambda p: {
                "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 0, "cashback_tiers": [],
            })

        selection = ",".join(str(i) for i in range(1, 23))
        output, exit_code = run_comparison(selection)
        assert exit_code == 0
        assert "RECOMMENDED SPLIT" in output


# ---------------------------------------------------------------------------
# 5. Brand-constrained item
# ---------------------------------------------------------------------------

class TestBrandConstraint:
    def test_brand_constraint_filters_correctly(self, orchestrator_env, monkeypatch):
        """Item with brand constraint picks the brand-matching product, not the cheapest."""
        items = [_make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg", brand="Tata")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Fortune Toor Dal 1kg", "price": 100.0, "brand": "Fortune", "unit": "1kg", "url": ""},
            {"name": "Tata Toor Dal 1kg", "price": 135.0, "brand": "Tata", "unit": "1kg", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Tata Sampann Toor Dal 1kg", "price": 128.0, "brand": "Tata Sampann", "unit": "1kg"},
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1")
        assert exit_code == 0
        assert "Toor Dal" in output
        # Amazon should show ₹135 (Tata, not Fortune at ₹100)
        assert "135" in output

    def test_brand_no_match_on_any_platform(self, orchestrator_env, monkeypatch):
        """Item with brand constraint that matches no candidate is marked unavailable."""
        items = [_make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg", brand="OrganicRare")]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        for prefix in ("scraper_amazon", "scraper_blinkit"):
            monkeypatch.setattr(f"orchestrator.{prefix}.set_location", lambda p, pin: True)
            monkeypatch.setattr(f"orchestrator.{prefix}.dismiss_modals", lambda p: None)
            monkeypatch.setattr(f"orchestrator.{prefix}.search_items", lambda p, q: None)
            monkeypatch.setattr(f"orchestrator.{prefix}.extract_results", lambda p: [
                {"name": "Toor Dal 1kg", "price": 120.0, "brand": "Fortune", "unit": "1kg"},
            ])
            monkeypatch.setattr(f"orchestrator.{prefix}.discover_fees", lambda p: {
                "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
            })

        output, exit_code = run_comparison("1")
        assert exit_code == 1  # No items found on any platform


# ---------------------------------------------------------------------------
# 6. Quantity x syntax
# ---------------------------------------------------------------------------

class TestQuantitySyntax:
    def test_quantity_syntax_parsed_and_reflected_in_output(self, orchestrator_env, monkeypatch):
        """Quantity syntax 1x3,2x2 is parsed and reflected in the formatted output."""
        items = [
            _make_master_item(1, "Milk 1L", "milk 1l"),
            _make_master_item(2, "Bread", "bread"),
        ]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Amul Taaza Milk 1L", "price": 60.0, "brand": "Amul", "unit": "1L", "url": ""},
            {"name": "Whole Wheat Bread", "price": 45.0, "brand": "Harvest", "unit": "", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Amul Taaza Milk 1L", "price": 58.0, "brand": "Amul", "unit": "1L"},
            {"name": "Whole Wheat Bread", "price": 42.0, "brand": "Harvest", "unit": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1x3,2x2")
        assert exit_code == 0
        # Table should show quantities
        assert "x3" in output
        assert "x2" in output
        # Recommendation should show per-unit price math for qty > 1
        assert "ea" in output  # table price shows "ea" for qty > 1

    def test_selection_parser_quantity_edge_cases(self):
        """Verify various quantity syntax patterns."""
        valid = {1, 2, 3, 4, 5}

        result = parse_selection("1x3,4x2", valid)
        assert result == [{"id": 1, "qty": 3}, {"id": 4, "qty": 2}]

        result = parse_selection("5x1", valid)
        assert result == [{"id": 5, "qty": 1}]

        # Large quantity
        result = parse_selection("1x99", valid)
        assert result == [{"id": 1, "qty": 99}]


# ---------------------------------------------------------------------------
# 7. Telegram message splitting with long output (15+ items)
# ---------------------------------------------------------------------------

class TestLongOutputSplitting:
    def test_15_items_output_splits_correctly(self):
        """Format 15 items and verify split_message produces valid chunks."""
        items = []
        for i in range(1, 16):
            items.append(_make_optimizer_item(
                i, f"Long Product Name Item {i}", 2,
                amazon_price=100 + i * 5, blinkit_price=110 + i * 3,
                amazon_brand=f"Brand{i}", blinkit_brand=f"Brand{i}",
            ))

        # Compute real optimizer result
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        result = optimize_cart(items, fees)

        output = format_comparison(result, items)

        # 15 items with brands should be long enough to trigger splitting
        chunks = split_message(output, max_length=4096)

        # Verify all chunks are within limit
        for chunk in chunks:
            assert len(chunk) <= 4096

        # Verify complete content is preserved
        full = "\n".join(chunks)
        assert "Price Comparison Results" in full
        assert "RECOMMENDED SPLIT" in full

    def test_20_items_table_overflow_splits_at_row_boundaries(self):
        """With 20 items, the table alone may exceed 4096. Split at row boundaries."""
        items = [
            _make_optimizer_item(
                i, f"Very Long Product Name Number {i} With Extra Description", 3,
                amazon_price=200 + i, blinkit_price=190 + i,
                amazon_brand=f"BrandName{i}", blinkit_brand=f"BrandName{i}",
            )
            for i in range(1, 21)
        ]

        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        result = optimize_cart(items, fees)
        output = format_comparison(result, items)

        # Use a smaller max to guarantee splitting
        chunks = split_message(output, max_length=2000)

        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 2000

        # No chunk should contain a partial table row (mid-row split)
        for chunk in chunks:
            lines = chunk.split("\n")
            # Each data line starts with │ and should be complete
            for line in lines:
                if line.startswith("│"):
                    assert line.endswith("│"), f"Partial row found: {line[:80]}"

    def test_single_message_for_small_output(self):
        """3 items should fit in a single message."""
        items = [
            _make_optimizer_item(i, f"Item {i}", 1,
                                 amazon_price=100 + i, blinkit_price=110 + i)
            for i in range(1, 4)
        ]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        result = optimize_cart(items, fees)
        output = format_comparison(result, items)

        chunks = split_message(output, max_length=4096)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestMixedAvailability:
    def test_some_items_on_one_platform_some_on_both(self, orchestrator_env, monkeypatch):
        """Mix of single-platform and dual-platform items."""
        items = [
            _make_master_item(1, "Toor Dal 1kg", "toor dal 1 kg"),
            _make_master_item(2, "Butter 500g", "amul butter 500g"),
            _make_master_item(3, "Olive Oil 1L", "olive oil 1l"),  # only on Amazon
        ]
        _setup_master_list(orchestrator_env, monkeypatch, items)

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_amazon.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", lambda p: [
            {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata", "unit": "1kg", "url": ""},
            {"name": "Amul Butter 500g", "price": 295.0, "brand": "Amul", "unit": "500g", "url": ""},
            {"name": "Figaro Olive Oil 1L", "price": 449.0, "brand": "Figaro", "unit": "1L", "url": ""},
        ])
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees", lambda p: {
            "delivery_fee": 0, "handling_fee": 0, "free_delivery_threshold": 99.0, "cashback_tiers": [],
        })

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", lambda p, pin: True)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", lambda p: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", lambda p, q: None)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", lambda p: [
            {"name": "Toor Dal 1kg", "price": 128.0, "brand": "Tata", "unit": "1kg"},
            {"name": "Amul Butter 500g", "price": 290.0, "brand": "Amul", "unit": "500g"},
            # No Olive Oil
        ])
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees", lambda p: {
            "delivery_fee": 25, "handling_fee": 9, "free_delivery_threshold": 199.0, "cashback_tiers": [],
        })

        output, exit_code = run_comparison("1,2,3")
        assert exit_code == 0
        assert "Olive Oil" in output
        assert "N/A" in output  # Olive Oil unavailable on Blinkit
        assert "RECOMMENDED SPLIT" in output


class TestFeeWarningEdgeCases:
    def test_fee_warning_for_small_order(self):
        """Very small order triggers the fee warning."""
        items = [_make_optimizer_item(1, "Gum", 1, blinkit_price=20)]
        fees = _default_fees()
        fees["blinkit"]["free_delivery_threshold"] = 199.0
        result = optimize_cart(items, fees)
        # delivery 25 + handling 9 = 34, item cost 20 -> 34/20 = 170% > 20%
        assert result["fee_warning"] is True

    def test_no_fee_warning_for_large_order(self):
        """Large order does not trigger fee warning."""
        items = [_make_optimizer_item(i, f"Item {i}", 1, amazon_price=200)
                 for i in range(1, 6)]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 99.0
        result = optimize_cart(items, fees)
        # subtotal 1000 > 99, delivery free, handling 0 -> 0% < 20%
        assert result["fee_warning"] is False
