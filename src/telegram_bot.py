"""Telegram bot for grocery price comparison agent."""

import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

# In-memory conversation state keyed by user_id.
# Stores current flow step and pending data. Lost on restart (acceptable per spec).
state = {}

HELP_TEXT = (
    "Available commands:\n"
    "/compare — Compare prices across Amazon and Blinkit\n"
    "/add <name> — Add an item to the master list\n"
    "/remove <id> — Remove an item from the master list\n"
    "/help — Show this help message"
)


def is_allowed_user(update: Update) -> bool:
    """Check if the message is from the allowed user."""
    if not ALLOWED_USER_ID:
        return False
    return update.effective_user.id == int(ALLOWED_USER_ID)


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


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unrecognized commands."""
    if not is_allowed_user(update):
        return
    await update.message.reply_text(f"Unknown command.\n\n{HELP_TEXT}")


async def plain_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages (for conversation state flows)."""
    if not is_allowed_user(update):
        return
    user_id = update.effective_user.id
    if user_id not in state:
        await update.message.reply_text(f"Send /compare to start a price comparison.\n\n{HELP_TEXT}")
        return
    # State-based handling will be added in B2/B3


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN not set in environment")
    if not ALLOWED_USER_ID:
        raise RuntimeError("ALLOWED_USER_ID not set in environment")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    # Catch-all for unrecognized commands
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    # Plain text messages (for state-based flows like selection, confirmation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_message))

    app.run_polling()


if __name__ == "__main__":
    main()
