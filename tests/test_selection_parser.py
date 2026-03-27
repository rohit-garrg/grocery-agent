import pytest
from src.selection_parser import parse_selection


VALID_IDS = {1, 2, 3, 4, 5, 8, 10, 12}


class TestParseSelection:
    def test_valid_with_quantities(self):
        result = parse_selection("1x2,4x3,5x1", VALID_IDS)
        assert result == [
            {"id": 1, "qty": 2},
            {"id": 4, "qty": 3},
            {"id": 5, "qty": 1},
        ]

    def test_valid_without_quantities(self):
        result = parse_selection("1,4,5", VALID_IDS)
        assert result == [
            {"id": 1, "qty": 1},
            {"id": 4, "qty": 1},
            {"id": 5, "qty": 1},
        ]

    def test_mixed_with_and_without_quantities(self):
        result = parse_selection("1x2,4,5x3,8", VALID_IDS)
        assert result == [
            {"id": 1, "qty": 2},
            {"id": 4, "qty": 1},
            {"id": 5, "qty": 3},
            {"id": 8, "qty": 1},
        ]

    def test_single_item(self):
        result = parse_selection("3", VALID_IDS)
        assert result == [{"id": 3, "qty": 1}]

    def test_single_item_with_quantity(self):
        result = parse_selection("3x5", VALID_IDS)
        assert result == [{"id": 3, "qty": 5}]

    def test_whitespace_stripping(self):
        result = parse_selection("  1x2,4  ", VALID_IDS)
        assert result == [
            {"id": 1, "qty": 2},
            {"id": 4, "qty": 1},
        ]

    def test_invalid_format_letters(self):
        with pytest.raises(ValueError, match="Invalid format"):
            parse_selection("abc", VALID_IDS)

    def test_invalid_format_spaces_between(self):
        with pytest.raises(ValueError, match="Invalid format"):
            parse_selection("1, 4", VALID_IDS)

    def test_invalid_format_trailing_comma(self):
        with pytest.raises(ValueError, match="Invalid format"):
            parse_selection("1,4,", VALID_IDS)

    def test_invalid_format_empty(self):
        with pytest.raises(ValueError, match="empty"):
            parse_selection("", VALID_IDS)

    def test_invalid_format_only_whitespace(self):
        with pytest.raises(ValueError, match="empty"):
            parse_selection("   ", VALID_IDS)

    def test_unknown_ids(self):
        with pytest.raises(ValueError, match="Unknown item id: 99"):
            parse_selection("1,99", VALID_IDS)

    def test_duplicate_ids(self):
        with pytest.raises(ValueError, match="Duplicate item id: 1"):
            parse_selection("1x2,1x3", VALID_IDS)

    def test_zero_quantity(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            parse_selection("1x0", VALID_IDS)

    def test_negative_quantity(self):
        with pytest.raises(ValueError):
            parse_selection("1x-1", VALID_IDS)

    def test_valid_ids_as_list(self):
        result = parse_selection("1,2", [1, 2, 3])
        assert result == [
            {"id": 1, "qty": 1},
            {"id": 2, "qty": 1},
        ]
