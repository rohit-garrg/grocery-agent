# Grocery Price Comparison Agent

A Telegram bot that compares grocery prices between **Amazon** (Prime) and **Blinkit**, then recommends the cheapest way to split your cart across both platforms — factoring in delivery fees, free delivery thresholds, and cashback.

Built with Python, Playwright (for browser-based price scraping), and Claude Code (as the orchestration layer).

## How it works

1. You maintain a **master list** of grocery items (via Telegram commands or JSON)
2. Send `/compare` in Telegram and select which items to compare
3. The bot scrapes live prices from Amazon and Blinkit using a persistent browser session
4. An optimizer calculates the best cart split across platforms
5. You get a formatted comparison table + recommendation in Telegram

## Quick start

### Prerequisites

- Python 3.11+
- An Amazon Prime account (amazon.in) and a Blinkit account
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) on a Max plan

### Setup

```bash
# 1. Clone and install
git clone https://github.com/<your-username>/grocery-agent.git
cd grocery-agent
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment
cp .env.example .env
# Edit .env with your Telegram token, user ID, browser profile path, and delivery pincode

cp master_list.example.json master_list.json

# 3. Log into Amazon and Blinkit in the persistent browser
./setup_browser.sh
# Sign into both platforms, set your delivery address, then press Enter to close

# 4. Start the bot
python3 src/telegram_bot.py
```

See [SETUP.md](SETUP.md) for detailed step-by-step instructions.

### Telegram commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List available commands |
| `/list` | Show your master list |
| `/add <item>` | Add an item (e.g., `/add Amul Butter 500g`) |
| `/remove <id>` | Remove an item by ID |
| `/compare` | Start a price comparison |

## Architecture

```
Telegram bot (async, long-running)
  -> agent.sh (shell bridge)
    -> claude -p (orchestrator)
      -> python3 src/orchestrator.py (pipeline)
           |- scraper_amazon.py    (Playwright, sync)
           |- scraper_blinkit.py   (Playwright, sync)
           |- match_utils.py       (product matching)
           |- optimizer.py         (cart split optimization)
           '- formatter.py         (Telegram output)
```

Browser automation uses **Python Playwright (sync API)** — not Playwright MCP. Scrapers drive a persistent Chromium profile with your logged-in sessions.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_TOKEN` | Yes | Bot token from @BotFather |
| `ALLOWED_USER_ID` | Yes | Your Telegram user ID (integer) |
| `BROWSER_PROFILE_PATH` | Yes | Absolute path for the persistent browser profile |
| `PINCODE` | Yes | Your delivery pincode |

## Project structure

```
src/                  # All source code
  telegram_bot.py     # Telegram polling + command routing
  orchestrator.py     # Pipeline coordinator
  scraper_amazon.py   # Amazon price scraper
  scraper_blinkit.py  # Blinkit price scraper
  match_utils.py      # Product matching heuristic
  optimizer.py        # Cart split optimizer
  formatter.py        # Telegram message formatting
  ...
tests/                # Pytest test suite
master_list.json      # Your item list (starts empty)
```

## Running tests

```bash
# Unit tests (no browser needed)
python3 -m pytest tests/ -v -m "not integration"

# Integration tests (requires browser profile + live sessions)
python3 -m pytest tests/ -v -m integration
```

## Limitations

- Works with **Amazon.in** and **Blinkit** only (Indian grocery platforms)
- Requires active logged-in sessions — the bot does not handle login
- Platform page layouts change without warning; selectors may need updates
- Scraping is slow (~30-60s per comparison depending on item count)

## License

MIT
