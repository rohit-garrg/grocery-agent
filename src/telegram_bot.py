"""Telegram bot for grocery price comparison agent."""

import asyncio
import os
import subprocess
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from src.master_list_manager import load_list
    from src.selection_parser import parse_selection
    from src.formatter import split_message
except ImportError:
    from master_list_manager import load_list
    from selection_parser import parse_selection
    from formatter import split_message

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
MASTER_LIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "master_list.json"
)
AGENT_SH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.sh")

# In-memory conversation state keyed by user_id.
# Stores current flow step and pending data. Lost on restart (acceptable per spec).
state = {}

HELP_TEXT = (
    "Available commands:\n"
    "/compare \u2014 Compare grocery prices\n"
    "/help \u2014 Show this help message"
)


def is_allowed_user(update: Update) -> bool:
    """Check if the message is from the allowed user."""
    if not ALLOWED_USER_ID or not update.effective_user:
        return False
    return update.effective_user.id == int(ALLOWED_USER_ID)


def _format_master_list(items):
    """Format master list items grouped by category for Telegram display."""
    if not items:
        return "Your grocery list is empty. Use /add <name> to add items."

    grouped = defaultdict(list)
    for item in items:
        grouped[item.get("category", "uncategorized")].append(item)

    lines = ["\U0001f9fa Your grocery list:\n"]
    for category, cat_items in grouped.items():
        lines.append(category.title())
        for item in cat_items:
            lines.append(f"{item['id']}. {item['name']}")
        lines.append("")

    lines.append("Reply with item numbers separated by commas.")
    lines.append("For multiple units, use Nx format (e.g., 1x2 = two units of item 1).")
    lines.append("Example: 1x2,4,5,8,12")

    return "\n".join(lines)


async def _call_agent(selection_string):
    """Call agent.sh via subprocess. Returns CompletedProcess."""
    return await asyncio.to_thread(
        subprocess.run,
        ["bash", AGENT_SH_PATH, selection_string],
        capture_output=True, text=True, timeout=600,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_allowed_user(update):
        return
    await update.message.reply_text(HELP_TEXT)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_allowed_user(update):
        return
    await update.message.reply_text(f"Welcome to the Grocery Price Agent!\n\n{HELP_TEXT}")


async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /compare -- show master list and await selection."""
    if not is_allowed_user(update):
        return

    items = load_list(MASTER_LIST_PATH)
    if not items:
        await update.message.reply_text(
            "Your grocery list is empty. Use /add <name> to add items first."
        )
        return

    for chunk in split_message(_format_master_list(items)):
        await update.message.reply_text(chunk)
    state[update.effective_user.id] = {"step": "awaiting_selection"}


async def _handle_selection(update: Update, user_id: int) -> None:
    """Process user's item selection and invoke agent."""
    items = load_list(MASTER_LIST_PATH)
    valid_ids = {item["id"] for item in items}

    try:
        parsed = parse_selection(update.message.text, valid_ids)
    except ValueError as e:
        await update.message.reply_text(f"Invalid selection: {e}\n\nPlease try again.")
        return

    n = len(parsed)
    state[user_id] = {"step": "comparing", "selection": parsed}

    selection_string = ",".join(
        f"{p['id']}x{p['qty']}" if p["qty"] > 1 else str(p["id"])
        for p in parsed
    )

    await update.message.reply_text(
        f"Got it. Fetching prices for {n} items... (this takes 2-5 minutes)"
    )

    try:
        result = await _call_agent(selection_string)
        output = result.stdout.strip()
        if output:
            for chunk in split_message(output):
                await update.message.reply_text(chunk)
        else:
            stderr = result.stderr.strip() if result.stderr else ""
            await update.message.reply_text(
                f"No output from comparison.{' Error: ' + stderr if stderr else ''}"
            )
    except subprocess.TimeoutExpired:
        await update.message.reply_text(
            "Comparison timed out after 10 minutes. Please try again."
        )
    except Exception as e:
        await update.message.reply_text(f"Error running comparison: {e}")
    finally:
        state.pop(user_id, None)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unrecognized commands."""
    if not is_allowed_user(update):
        return
    await update.message.reply_text(f"Unknown command.\n\n{HELP_TEXT}")


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages (for conversation state flows)."""
    if not is_allowed_user(update):
        return
    user_id = update.effective_user.id
    user_state = state.get(user_id)

    if not user_state:
        await update.message.reply_text(
            f"Send /compare to start a price comparison.\n\n{HELP_TEXT}"
        )
        return

    if user_state.get("step") == "awaiting_selection":
        await _handle_selection(update, user_id)
        return

    # Other state steps will be added in B3 (awaiting_remove_confirm, etc.)
    await update.message.reply_text(
        f"Send /compare to start a price comparison.\n\n{HELP_TEXT}"
    )


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN not set in environment")
    if not ALLOWED_USER_ID:
        raise RuntimeError("ALLOWED_USER_ID not set in environment")
    try:
        int(ALLOWED_USER_ID)
    except ValueError:
        raise RuntimeError(
            f"ALLOWED_USER_ID must be a numeric user ID, got: {ALLOWED_USER_ID!r}"
        )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("compare", compare_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))

    app.run_polling()


if __name__ == "__main__":
    main()
