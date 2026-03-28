"""Tests for telegram_bot.py core functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def allowed_user_id():
    return 12345


@pytest.fixture
def mock_update_allowed(allowed_user_id):
    """Create a mock Update from the allowed user."""
    update = MagicMock()
    update.effective_user.id = allowed_user_id
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_update_stranger():
    """Create a mock Update from an unauthorized user."""
    update = MagicMock()
    update.effective_user.id = 99999
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    return MagicMock()


class TestIsAllowedUser:
    def test_allowed_user(self, mock_update_allowed, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import is_allowed_user
            assert is_allowed_user(mock_update_allowed) is True

    def test_stranger_rejected(self, mock_update_stranger, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import is_allowed_user
            assert is_allowed_user(mock_update_stranger) is False

    def test_no_allowed_user_configured(self, mock_update_allowed):
        with patch("src.telegram_bot.ALLOWED_USER_ID", None):
            from src.telegram_bot import is_allowed_user
            assert is_allowed_user(mock_update_allowed) is False


class TestHelpCommand:
    @pytest.mark.asyncio
    async def test_help_allowed_user(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import help_command
            await help_command(mock_update_allowed, mock_context)
            mock_update_allowed.message.reply_text.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "/compare" in text
            assert "/add" in text
            assert "/remove" in text
            assert "/help" in text

    @pytest.mark.asyncio
    async def test_help_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import help_command
            await help_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestStartCommand:
    @pytest.mark.asyncio
    async def test_start_allowed_user(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import start_command
            await start_command(mock_update_allowed, mock_context)
            mock_update_allowed.message.reply_text.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Welcome" in text

    @pytest.mark.asyncio
    async def test_start_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import start_command
            await start_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestUnknownCommand:
    @pytest.mark.asyncio
    async def test_unknown_allowed_user(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import unknown_command
            await unknown_command(mock_update_allowed, mock_context)
            mock_update_allowed.message.reply_text.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Unknown command" in text

    @pytest.mark.asyncio
    async def test_unknown_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import unknown_command
            await unknown_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestPlainMessage:
    @pytest.mark.asyncio
    async def test_plain_message_no_state(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.state", {}):
            from src.telegram_bot import plain_message
            await plain_message(mock_update_allowed, mock_context)
            mock_update_allowed.message.reply_text.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "/compare" in text

    @pytest.mark.asyncio
    async def test_plain_message_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import plain_message
            await plain_message(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestMain:
    def test_missing_token_raises(self):
        with patch("src.telegram_bot.TELEGRAM_TOKEN", None), \
             patch("src.telegram_bot.ALLOWED_USER_ID", "12345"):
            from src.telegram_bot import main
            with pytest.raises(RuntimeError, match="TELEGRAM_TOKEN"):
                main()

    def test_missing_user_id_raises(self):
        with patch("src.telegram_bot.TELEGRAM_TOKEN", "fake-token"), \
             patch("src.telegram_bot.ALLOWED_USER_ID", None):
            from src.telegram_bot import main
            with pytest.raises(RuntimeError, match="ALLOWED_USER_ID"):
                main()
