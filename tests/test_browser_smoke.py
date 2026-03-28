"""Smoke test for browser_manager — requires a live browser profile."""

import os
import pytest
from src.browser_manager import get_browser_context, close_context


# Integration test: requires browser profile with Chromium installed
@pytest.mark.integration
def test_persistent_context_opens_and_navigates():
    profile_path = os.environ.get("BROWSER_PROFILE_PATH", "browser_profile")
    context, pw = get_browser_context(profile_path)
    try:
        page = context.new_page()
        page.goto("https://example.com")
        assert "Example Domain" in page.title()
        page.close()
    finally:
        close_context(context, pw)
