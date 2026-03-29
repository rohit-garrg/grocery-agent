#!/bin/bash
# setup_browser.sh — Open a headed browser for manual login to Amazon and Blinkit.
# The persistent profile is reused by the agent for headless scraping runs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load BROWSER_PROFILE_PATH from .env if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
  BROWSER_PROFILE_PATH=$(grep -E '^BROWSER_PROFILE_PATH=' "$SCRIPT_DIR/.env" | cut -d'=' -f2- | xargs)
fi

if [ -z "${BROWSER_PROFILE_PATH:-}" ]; then
  echo "Error: BROWSER_PROFILE_PATH not set."
  echo "Set it in .env or export it before running this script."
  exit 1
fi

echo "Browser profile: $BROWSER_PROFILE_PATH"
echo ""
echo "A Chromium window will open with two tabs:"
echo "  1. amazon.in"
echo "  2. blinkit.com"
echo ""
echo "Log into both platforms, then come back here and press Enter to close."
echo ""

# Export so Python reads it via os.environ — avoids shell injection from string interpolation.
export BROWSER_PROFILE_PATH

python3 -c "
import os
from playwright.sync_api import sync_playwright

profile_path = os.environ['BROWSER_PROFILE_PATH']

pw = sync_playwright().start()
try:
    context = pw.chromium.launch_persistent_context(
        profile_path,
        headless=False,
        viewport={'width': 1280, 'height': 720},
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://www.amazon.in', wait_until='domcontentloaded')

    blinkit_page = context.new_page()
    blinkit_page.goto('https://www.blinkit.com', wait_until='domcontentloaded')

    print('Browser is open. Log into both platforms.')
    try:
        input('Press Enter to close the browser...')
    except EOFError:
        pass

    context.close()
finally:
    pw.stop()
"

echo "Browser closed. Sessions are saved to: $BROWSER_PROFILE_PATH"
echo "You can now run the bot with: python3 src/telegram_bot.py"
