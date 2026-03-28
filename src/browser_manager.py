"""Playwright persistent browser context lifecycle management."""

from playwright.sync_api import sync_playwright


def get_browser_context(profile_path):
    """Launch a persistent Chromium context from the given profile path.

    Returns (context, playwright_instance). Caller must pass both to
    close_context() when done.
    """
    pw = sync_playwright().start()
    try:
        # Headed mode reduces bot detection risk. Requires a display (Mac/desktop only).
        context = pw.chromium.launch_persistent_context(
            profile_path,
            headless=False,
            args=["--window-size=1280,720", "--window-position=-10000,-10000"],
            viewport={"width": 1280, "height": 720},
        )
    except Exception:
        pw.stop()
        raise
    return context, pw


def close_context(context, playwright_instance):
    """Close the browser context and stop the Playwright instance."""
    try:
        context.close()
    finally:
        playwright_instance.stop()
