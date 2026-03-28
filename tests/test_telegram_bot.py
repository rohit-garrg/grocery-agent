"""Tests for telegram_bot.py core functionality."""

import subprocess
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


class TestOnTextMessage:
    @pytest.mark.asyncio
    async def test_no_state_prompts_compare(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.state", {}):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            mock_update_allowed.message.reply_text.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "/compare" in text

    @pytest.mark.asyncio
    async def test_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_stranger, mock_context)
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

    def test_invalid_user_id_raises(self):
        with patch("src.telegram_bot.TELEGRAM_TOKEN", "fake-token"), \
             patch("src.telegram_bot.ALLOWED_USER_ID", "not-a-number"):
            from src.telegram_bot import main
            with pytest.raises(RuntimeError, match="numeric"):
                main()


# --- B2: /compare and selection flow ---


class TestFormatMasterList:
    def test_empty_list(self):
        from src.telegram_bot import _format_master_list
        result = _format_master_list([])
        assert "empty" in result.lower()
        assert "/add" in result

    def test_grouped_by_category(self):
        from src.telegram_bot import _format_master_list
        items = [
            {"id": 1, "name": "Toor Dal 1kg", "category": "pulses"},
            {"id": 2, "name": "Moong Dal 1kg", "category": "pulses"},
            {"id": 3, "name": "Amul Butter 500g", "category": "dairy"},
        ]
        result = _format_master_list(items)
        assert "Pulses" in result
        assert "Dairy" in result
        assert "1. Toor Dal 1kg" in result
        assert "2. Moong Dal 1kg" in result
        assert "3. Amul Butter 500g" in result

    def test_includes_instructions(self):
        from src.telegram_bot import _format_master_list
        items = [{"id": 1, "name": "Test", "category": "test"}]
        result = _format_master_list(items)
        assert "Reply with item numbers" in result
        assert "Nx format" in result
        assert "Example:" in result

    def test_uncategorized_default(self):
        from src.telegram_bot import _format_master_list
        items = [{"id": 1, "name": "Misc Item"}]
        result = _format_master_list(items)
        assert "Uncategorized" in result
        assert "1. Misc Item" in result


class TestCompareCommand:
    @pytest.mark.asyncio
    async def test_shows_formatted_list(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [
            {"id": 1, "name": "Toor Dal", "category": "pulses"},
            {"id": 2, "name": "Butter", "category": "dairy"},
        ]
        mock_state = {}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import compare_command
            await compare_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Toor Dal" in text
            assert "Butter" in text

    @pytest.mark.asyncio
    async def test_sets_awaiting_state(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_state = {}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import compare_command
            await compare_command(mock_update_allowed, mock_context)
            assert mock_state[allowed_user_id] == {"step": "awaiting_selection"}

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_update_allowed, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=[]):
            from src.telegram_bot import compare_command
            await compare_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "empty" in text.lower()

    @pytest.mark.asyncio
    async def test_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import compare_command
            await compare_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestSelectionFlow:
    @pytest.mark.asyncio
    async def test_valid_selection_acknowledged(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [
            {"id": 1, "name": "Toor Dal", "category": "pulses"},
            {"id": 2, "name": "Butter", "category": "dairy"},
        ]
        mock_update_allowed.message.text = "1x2,2"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}
        mock_result = MagicMock()
        mock_result.stdout = "Comparison output"
        mock_result.stderr = ""

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock, return_value=mock_result):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            calls = mock_update_allowed.message.reply_text.call_args_list
            ack = calls[0][0][0]
            assert "Got it" in ack
            assert "2 items" in ack

    @pytest.mark.asyncio
    async def test_agent_output_sent(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_update_allowed.message.text = "1"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}
        mock_result = MagicMock()
        mock_result.stdout = "Price comparison result here"
        mock_result.stderr = ""

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock, return_value=mock_result):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            calls = mock_update_allowed.message.reply_text.call_args_list
            output = calls[1][0][0]
            assert "Price comparison result here" in output

    @pytest.mark.asyncio
    async def test_invalid_selection_error(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_update_allowed.message.text = "abc"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Invalid selection" in text
            assert "try again" in text.lower()
            assert mock_state[allowed_user_id]["step"] == "awaiting_selection"

    @pytest.mark.asyncio
    async def test_retry_after_invalid(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}

        # First: invalid input
        mock_update_allowed.message.text = "abc"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
        assert mock_state[allowed_user_id]["step"] == "awaiting_selection"

        # Second: valid input
        mock_update_allowed.message.text = "1"
        mock_update_allowed.message.reply_text.reset_mock()
        mock_result = MagicMock()
        mock_result.stdout = "Result"
        mock_result.stderr = ""
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock, return_value=mock_result):
            await on_text_message(mock_update_allowed, mock_context)
            ack = mock_update_allowed.message.reply_text.call_args_list[0][0][0]
            assert "Got it" in ack

    @pytest.mark.asyncio
    async def test_state_cleared_after_comparison(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_update_allowed.message.text = "1"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}
        mock_result = MagicMock()
        mock_result.stdout = "Result"
        mock_result.stderr = ""

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock, return_value=mock_result):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            assert allowed_user_id not in mock_state

    @pytest.mark.asyncio
    async def test_timeout_handled(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_update_allowed.message.text = "1"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock,
                   side_effect=subprocess.TimeoutExpired("cmd", 600)):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            calls = mock_update_allowed.message.reply_text.call_args_list
            timeout_msg = calls[1][0][0]
            assert "timed out" in timeout_msg.lower()
            assert allowed_user_id not in mock_state

    @pytest.mark.asyncio
    async def test_no_output_handled(self, mock_update_allowed, mock_context, allowed_user_id):
        items = [{"id": 1, "name": "Item", "category": "test"}]
        mock_update_allowed.message.text = "1"
        mock_state = {allowed_user_id: {"step": "awaiting_selection"}}
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "agent.sh: No such file"

        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.load_list", return_value=items), \
             patch("src.telegram_bot.state", mock_state), \
             patch("src.telegram_bot._call_agent", new_callable=AsyncMock, return_value=mock_result):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            calls = mock_update_allowed.message.reply_text.call_args_list
            error_msg = calls[1][0][0]
            assert "No output" in error_msg


# --- B3: /add and /remove ---


class TestAddCommand:
    @pytest.mark.asyncio
    async def test_add_item(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/add Amul Butter 500g"
        new_item = {"id": 1, "name": "Amul Butter 500g", "query": "Amul Butter 500g",
                    "brand": None, "category": "uncategorized"}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.add_item", return_value=new_item) as mock_add:
            from src.telegram_bot import add_command
            await add_command(mock_update_allowed, mock_context)
            mock_add.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "#1" in text
            assert "Amul Butter 500g" in text
            assert "uncategorized" in text
            assert "master_list.json" in text

    @pytest.mark.asyncio
    async def test_add_no_name(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/add"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import add_command
            await add_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Usage" in text

    @pytest.mark.asyncio
    async def test_add_empty_name(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/add   "
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import add_command
            await add_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Usage" in text

    @pytest.mark.asyncio
    async def test_add_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        mock_update_stranger.message.text = "/add Test"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import add_command
            await add_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestRemoveCommand:
    @pytest.mark.asyncio
    async def test_remove_asks_confirmation(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/remove 3"
        mock_state = {}
        item = {"id": 3, "name": "Toor Dal 1kg", "category": "pulses"}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.get_item", return_value=item), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "#3" in text
            assert "Toor Dal 1kg" in text
            assert "yes" in text.lower()
            assert mock_state[allowed_user_id]["step"] == "awaiting_remove_confirm"
            assert mock_state[allowed_user_id]["item_id"] == 3

    @pytest.mark.asyncio
    async def test_remove_invalid_id_not_number(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/remove abc"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Invalid" in text

    @pytest.mark.asyncio
    async def test_remove_id_not_found(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/remove 999"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.get_item", return_value=None):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_remove_no_id(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/remove"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Usage" in text

    @pytest.mark.asyncio
    async def test_remove_stranger_ignored(self, mock_update_stranger, mock_context, allowed_user_id):
        mock_update_stranger.message.text = "/remove 1"
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_stranger, mock_context)
            mock_update_stranger.message.reply_text.assert_not_called()


class TestRemoveConfirmFlow:
    @pytest.mark.asyncio
    async def test_confirm_yes_removes(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "yes"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.remove_item", return_value=True) as mock_rm, \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            mock_rm.assert_called_once()
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Removed" in text
            assert allowed_user_id not in mock_state

    @pytest.mark.asyncio
    async def test_confirm_yes_case_insensitive(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "  YES  "
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.remove_item", return_value=True), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Removed" in text

    @pytest.mark.asyncio
    async def test_confirm_no_cancels(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "no"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "cancelled" in text.lower()
            assert allowed_user_id not in mock_state

    @pytest.mark.asyncio
    async def test_confirm_random_text_cancels(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "maybe later"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "cancelled" in text.lower()
            assert allowed_user_id not in mock_state

    @pytest.mark.asyncio
    async def test_remove_error_shown_to_user(self, mock_update_allowed, mock_context, allowed_user_id):
        """Non-ValueError exceptions (e.g. disk errors) are shown gracefully."""
        mock_update_allowed.message.text = "yes"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.remove_item", side_effect=RuntimeError("disk full")), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import on_text_message
            await on_text_message(mock_update_allowed, mock_context)
            text = mock_update_allowed.message.reply_text.call_args[0][0]
            assert "Error" in text
            assert allowed_user_id not in mock_state


# --- State cancellation when command interrupts pending remove ---


class TestCancelPendingStateOnCommand:
    @pytest.mark.asyncio
    async def test_help_cancels_pending_remove(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import help_command
            await help_command(mock_update_allowed, mock_context)
            assert allowed_user_id not in mock_state
            calls = [c[0][0] for c in mock_update_allowed.message.reply_text.call_args_list]
            assert any("cancelled" in t.lower() for t in calls)

    @pytest.mark.asyncio
    async def test_add_cancels_pending_remove(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/add Milk"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        new_item = {"id": 5, "name": "Milk", "query": "Milk", "brand": None, "category": "uncategorized"}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.add_item", return_value=new_item), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import add_command
            await add_command(mock_update_allowed, mock_context)
            assert allowed_user_id not in mock_state
            calls = [c[0][0] for c in mock_update_allowed.message.reply_text.call_args_list]
            assert any("cancelled" in t.lower() for t in calls)

    @pytest.mark.asyncio
    async def test_remove_cancels_prior_pending_remove(self, mock_update_allowed, mock_context, allowed_user_id):
        mock_update_allowed.message.text = "/remove 5"
        mock_state = {allowed_user_id: {"step": "awaiting_remove_confirm", "item_id": 3}}
        item = {"id": 5, "name": "Eggs", "category": "dairy"}
        with patch("src.telegram_bot.ALLOWED_USER_ID", str(allowed_user_id)), \
             patch("src.telegram_bot.get_item", return_value=item), \
             patch("src.telegram_bot.state", mock_state):
            from src.telegram_bot import remove_command
            await remove_command(mock_update_allowed, mock_context)
            # Old pending state was cancelled, new one was set for item 5
            assert mock_state[allowed_user_id]["item_id"] == 5
            calls = [c[0][0] for c in mock_update_allowed.message.reply_text.call_args_list]
            assert any("cancelled" in t.lower() for t in calls)
