"""Tests for orchestrator.py with mocked scrapers."""

import json
import os
import sys
import types

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator import run_comparison, _scrape_platform, DEFAULT_FEES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_master_list(tmp_path, items):
    """Write a master_list.json in tmp_path and return its path."""
    path = tmp_path / "master_list.json"
    path.write_text(json.dumps(items, indent=2))
    return str(path)


def _make_items():
    """Return a small master list for testing."""
    return [
        {"id": 1, "name": "Toor Dal 1kg", "query": "toor dal 1 kg", "brand": None, "category": "pulses"},
        {"id": 2, "name": "Amul Butter 500g", "query": "amul butter 500g", "brand": "Amul", "category": "dairy"},
        {"id": 3, "name": "Olive Oil 1L", "query": "olive oil 1l", "brand": None, "category": "oils"},
    ]


def _mock_amazon_search(page, query):
    """Mock Amazon search_items — does nothing."""
    pass


def _mock_amazon_extract(page):
    """Mock Amazon extract_results — returns canned data."""
    return [
        {"name": "Toor Dal 1kg Premium", "price": 135.0, "brand": "Tata", "unit": "1kg", "url": ""},
        {"name": "Amul Butter 500g", "price": 295.0, "brand": "Amul", "unit": "500g", "url": ""},
        {"name": "Figaro Olive Oil 1L", "price": 449.0, "brand": "Figaro", "unit": "1L", "url": ""},
    ]


def _mock_blinkit_search(page, query):
    """Mock Blinkit search_items — does nothing."""
    pass


def _mock_blinkit_extract(page):
    """Mock Blinkit extract_results — returns canned data."""
    return [
        {"name": "Toor Dal 1kg", "price": 128.0, "brand": "Tata", "unit": "1kg"},
        {"name": "Amul Butter 500g", "price": 290.0, "brand": "Amul", "unit": "500g"},
    ]


def _mock_set_location(page, pincode):
    """Mock set_location — always succeeds."""
    return True


def _mock_dismiss_modals(page):
    """Mock dismiss_modals — does nothing."""
    pass


def _mock_discover_fees_amazon(page):
    return {
        "delivery_fee": 40,
        "handling_fee": 0,
        "free_delivery_threshold": 99.0,
        "cashback_tiers": [],
    }


def _mock_discover_fees_blinkit(page):
    return {
        "delivery_fee": 25,
        "handling_fee": 9,
        "free_delivery_threshold": 199.0,
        "cashback_tiers": [],
    }


class FakePage:
    """Minimal fake page that acts as a no-op for scraper calls."""
    def close(self):
        pass


class FakeContext:
    """Minimal fake browser context."""
    def new_page(self):
        return FakePage()

    def close(self):
        pass


class FakePlaywright:
    """Minimal fake playwright instance."""
    def stop(self):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Set up environment and master list for orchestrator tests."""
    items = _make_items()
    ml_path = _write_master_list(tmp_path, items)
    profile_path = str(tmp_path / "browser_profile")
    os.makedirs(profile_path, exist_ok=True)

    # Patch orchestrator module-level paths
    monkeypatch.setattr("orchestrator.MASTER_LIST_PATH", ml_path)
    monkeypatch.setattr("orchestrator.BROWSER_PROFILE_PATH", profile_path)
    monkeypatch.setattr("orchestrator.PINCODE", "122001")

    # Patch browser manager
    monkeypatch.setattr(
        "orchestrator.get_browser_context",
        lambda path: (FakeContext(), FakePlaywright()),
    )
    monkeypatch.setattr(
        "orchestrator.close_context",
        lambda ctx, pw: None,
    )

    return ml_path


@pytest.fixture
def mock_scrapers_success(monkeypatch):
    """Mock all scraper functions for a successful run."""
    # Amazon
    monkeypatch.setattr("orchestrator.scraper_amazon.set_location", _mock_set_location)
    monkeypatch.setattr("orchestrator.scraper_amazon.search_items", _mock_amazon_search)
    monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
    monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

    # Blinkit
    monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", _mock_set_location)
    monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
    monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", _mock_blinkit_search)
    monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
    monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSuccessfulPipeline:
    def test_full_flow_returns_output(self, setup_env, mock_scrapers_success):
        output, exit_code = run_comparison("1x2,2,3")
        assert exit_code == 0
        assert "Price Comparison Results" in output
        assert "RECOMMENDED SPLIT" in output

    def test_output_contains_item_names(self, setup_env, mock_scrapers_success):
        output, exit_code = run_comparison("1,2")
        assert exit_code == 0
        assert "Toor Dal" in output
        assert "Butter" in output

    def test_single_item(self, setup_env, mock_scrapers_success):
        output, exit_code = run_comparison("1")
        assert exit_code == 0
        assert "Toor Dal" in output

    def test_item_only_on_amazon(self, setup_env, mock_scrapers_success):
        """Olive Oil (id=3) is only in the Amazon mock data."""
        output, exit_code = run_comparison("3")
        assert exit_code == 0
        assert "Olive Oil" in output


class TestSinglePlatformFailure:
    def test_amazon_session_expired(self, setup_env, monkeypatch):
        """When Amazon session is expired, should still get results from Blinkit."""
        def amazon_set_location_expired(page, pincode):
            raise RuntimeError("Amazon session expired — please re-login in the browser profile.")

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", amazon_set_location_expired)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", _mock_amazon_search)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", _mock_blinkit_search)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)

        output, exit_code = run_comparison("1,2")
        assert exit_code == 0
        assert "session expired" in output.lower()
        # Blinkit items should still appear
        assert "Toor Dal" in output

    def test_blinkit_session_expired(self, setup_env, monkeypatch):
        """When Blinkit session is expired, should still get results from Amazon."""
        def blinkit_set_location_expired(page, pincode):
            raise RuntimeError("Blinkit session expired — please re-login in the browser profile.")

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", _mock_amazon_search)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", blinkit_set_location_expired)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", _mock_blinkit_search)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)

        output, exit_code = run_comparison("1,2,3")
        assert exit_code == 0
        assert "session expired" in output.lower()
        # Amazon items should appear
        assert "Toor Dal" in output


class TestBothPlatformsFailed:
    def test_both_expired_returns_failure(self, setup_env, monkeypatch):
        """When both platforms have expired sessions, exit code should be 1."""
        def amazon_expired(page, pincode):
            raise RuntimeError("Amazon session expired — please re-login in the browser profile.")

        def blinkit_expired(page, pincode):
            raise RuntimeError("Blinkit session expired — please re-login in the browser profile.")

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", amazon_expired)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", _mock_amazon_search)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", blinkit_expired)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", _mock_blinkit_search)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)

        output, exit_code = run_comparison("1,2")
        assert exit_code == 1
        assert "no platforms available" in output.lower() or "session expired" in output.lower()

    def test_both_runtime_errors(self, setup_env, monkeypatch):
        """When both platforms throw RuntimeErrors (not session), exit code 1."""
        call_count = {"amazon": 0, "blinkit": 0}

        def amazon_fail(page, query):
            call_count["amazon"] += 1
            raise RuntimeError("Amazon page layout changed")

        def blinkit_fail(page, query):
            call_count["blinkit"] += 1
            raise RuntimeError("Blinkit page layout changed")

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", amazon_fail)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", blinkit_fail)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)

        output, exit_code = run_comparison("1,2,3")
        assert exit_code == 1


class TestConsecutiveFailures:
    def test_two_consecutive_failures_marks_unavailable(self, setup_env, monkeypatch):
        """After 2 consecutive failures, platform is marked unavailable for remaining items."""
        search_calls = []

        def amazon_always_fail(page, query):
            search_calls.append(("amazon", query))
            raise RuntimeError("Amazon page layout changed")

        monkeypatch.setattr("orchestrator.scraper_amazon.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_amazon.search_items", amazon_always_fail)
        monkeypatch.setattr("orchestrator.scraper_amazon.extract_results", _mock_amazon_extract)
        monkeypatch.setattr("orchestrator.scraper_amazon.discover_fees_amazon", _mock_discover_fees_amazon)

        monkeypatch.setattr("orchestrator.scraper_blinkit.set_location", _mock_set_location)
        monkeypatch.setattr("orchestrator.scraper_blinkit.dismiss_modals", _mock_dismiss_modals)
        monkeypatch.setattr("orchestrator.scraper_blinkit.search_items", _mock_blinkit_search)
        monkeypatch.setattr("orchestrator.scraper_blinkit.extract_results", _mock_blinkit_extract)
        monkeypatch.setattr("orchestrator.scraper_blinkit.discover_fees_blinkit", _mock_discover_fees_blinkit)

        # 3 items selected — Amazon should fail on 2 and stop trying
        output, exit_code = run_comparison("1,2,3")
        # Amazon search should be called only twice (stops after 2 consecutive failures)
        assert len(search_calls) == 2
        # Blinkit should still work, so we get results
        assert exit_code == 0
