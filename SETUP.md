# Setup Guide

## Prerequisites

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID (use [@userinfobot](https://t.me/userinfobot) to find it)
- An Amazon Prime account (amazon.in)
- A Blinkit account

## 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

## 2. Configure environment

Copy the example files and fill in your values:

```bash
cp .env.example .env
cp master_list.example.json master_list.json
```

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `ALLOWED_USER_ID` | Your Telegram numeric user ID |
| `BROWSER_PROFILE_PATH` | Absolute path for the persistent browser profile (e.g., `/Users/you/grocery-browser-profile`) |
| `PINCODE` | Your delivery pincode (e.g., `110001`) |

## 3. Log into platforms

Run the browser setup script to open a headed Chromium window:

```bash
./setup_browser.sh
```

This opens two tabs — Amazon and Blinkit. Log into both platforms:

- **Amazon:** Sign in with your Prime account. Set your delivery address to your pincode.
- **Blinkit:** Sign in and set your delivery location to your pincode.

Once logged in, press Enter in the terminal to close the browser. Your sessions are saved to the persistent profile directory and will be reused by the bot.

## 4. Add items to the master list

The bot starts with an empty `master_list.json`. Add items via Telegram:

```
/add Toor Dal 1kg
/add Amul Butter 500g
```

Or edit `master_list.json` directly to set brand constraints or tune search queries.

## 5. Start the bot

```bash
python3 src/telegram_bot.py
```

Send `/compare` in Telegram to start a price comparison.

## Re-login

If a platform session expires, the bot will warn you. Run `./setup_browser.sh` again to re-login, then retry the comparison.
