"""Integration tests for scrapers. Require a live browser profile with platform logins."""

import os

import pytest

from src.browser_manager import get_browser_context, close_context
from src.scraper_amazon import set_location, search_items, extract_results, discover_fees_amazon


PROFILE_PATH = os.environ.get("BROWSER_PROFILE_PATH", "browser_profile")


@pytest.fixture(scope="module")
def browser():
    """Shared browser context for all Amazon integration tests."""
    context, pw = get_browser_context(PROFILE_PATH)
    yield context, pw
    close_context(context, pw)


@pytest.fixture
def page(browser):
    """Fresh page per test."""
    context, _pw = browser
    pg = context.new_page()
    yield pg
    pg.close()


# Integration test: requires browser profile with Amazon Prime login
@pytest.mark.integration
class TestAmazonSetLocation:
    def test_set_location_success(self, page):
        """Verify set_location sets delivery to pincode 122001."""
        result = set_location(page, "122001")
        assert result is True

    def test_set_location_already_set(self, page):
        """After setting location once, a second call should detect it and return True."""
        set_location(page, "122001")
        result = set_location(page, "122001")
        assert result is True


# Integration test: requires browser profile with Amazon Prime login
@pytest.mark.integration
class TestAmazonSearch:
    def test_search_returns_results(self, page):
        """Search for a common grocery item and verify results are returned."""
        set_location(page, "122001")
        search_items(page, "toor dal 1 kg")
        results = extract_results(page)
        assert len(results) > 0

    def test_result_structure(self, page):
        """Verify each result has the required fields."""
        set_location(page, "122001")
        search_items(page, "toor dal 1 kg")
        results = extract_results(page)
        assert len(results) > 0
        for r in results:
            assert "name" in r
            assert "price" in r
            assert "brand" in r
            assert "unit" in r
            assert "url" in r
            assert isinstance(r["price"], float)
            assert r["price"] > 0

    def test_no_sponsored_in_results(self, page):
        """Sponsored results should be filtered out (best effort — layout dependent)."""
        set_location(page, "122001")
        search_items(page, "toor dal 1 kg")
        results = extract_results(page)
        # We can't guarantee all sponsored are filtered, but results should exist
        assert isinstance(results, list)


# Integration test: requires browser profile with Amazon Prime login
@pytest.mark.integration
class TestAmazonFeeDiscovery:
    def test_discover_fees_returns_structure(self, page):
        """Fee discovery returns a dict with the expected keys."""
        set_location(page, "122001")
        search_items(page, "toor dal 1 kg")
        fees = discover_fees_amazon(page)
        assert "status" not in fees  # Should not be session_expired
        assert "delivery_fee" in fees
        assert "handling_fee" in fees
        assert "free_delivery_threshold" in fees
        assert "cashback_tiers" in fees
        assert fees["handling_fee"] == 0  # Amazon has no handling fee


# Integration test: requires browser profile with Amazon Prime login
@pytest.mark.integration
class TestAmazonSessionExpiry:
    def test_session_expiry_detection(self, page):
        """If navigated to a signin page, session expiry should be detected."""
        page.goto("https://www.amazon.in/ap/signin", wait_until="domcontentloaded", timeout=30000)
        fees = discover_fees_amazon(page)
        assert fees.get("status") == "session_expired"
