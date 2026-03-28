"""Playwright persistent browser context lifecycle management."""

from playwright.sync_api import sync_playwright


def get_browser_context(profile_path):
    """Launch a persistent Chromium context from the given profile path.

    Returns (context, playwright_instance). Caller must pass both to
    close_context() when done.
    """
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        profile_path,
        headless=True,
    )
    return context, pw


def close_context(context, playwright_instance):
    """Close the browser context and stop the Playwright instance."""
    context.close()
    playwright_instance.stop()
