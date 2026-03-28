import pytest
from src.formatter import format_comparison, split_message, format_unavailable


# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------

def _make_item(id, name, qty, amazon_price=None, amazon_brand="", blinkit_price=None, blinkit_brand=""):
    """Build an item dict matching the optimizer/formatter contract."""
    prices = {}
    if amazon_price is not None:
        prices["amazon"] = {"price": amazon_price, "brand": amazon_brand}
    else:
        prices["amazon"] = None
    if blinkit_price is not None:
        prices["blinkit"] = {"price": blinkit_price, "brand": blinkit_brand}
    else:
        prices["blinkit"] = None
    return {"id": id, "name": name, "qty": qty, "prices": prices}


def _make_optimizer_result(
    amazon_items=None, blinkit_items=None,
    amazon_subtotal=0, blinkit_subtotal=0,
    amazon_delivery_fee=0, blinkit_delivery_fee=0,
    amazon_handling_fee=0, blinkit_handling_fee=0,
    amazon_cashback=0, blinkit_cashback=0,
    amazon_total=0, blinkit_total=0,
    combined_total=0, all_amazon_total=None, all_blinkit_total=None,
    savings=0, fee_warning=False,
):
    return {
        "recommendation": {
            "amazon": amazon_items or [],
            "blinkit": blinkit_items or [],
        },
        "amazon_subtotal": amazon_subtotal,
        "blinkit_subtotal": blinkit_subtotal,
        "amazon_delivery_fee": amazon_delivery_fee,
        "blinkit_delivery_fee": blinkit_delivery_fee,
        "amazon_handling_fee": amazon_handling_fee,
        "blinkit_handling_fee": blinkit_handling_fee,
        "amazon_cashback": amazon_cashback,
        "blinkit_cashback": blinkit_cashback,
        "amazon_total": amazon_total,
        "blinkit_total": blinkit_total,
        "combined_total": combined_total,
        "all_amazon_total": all_amazon_total,
        "all_blinkit_total": all_blinkit_total,
        "savings": savings,
        "fee_warning": fee_warning,
    }


# ---------------------------------------------------------------------------
# format_comparison tests
# ---------------------------------------------------------------------------

class TestFormatComparison:
    def test_basic_output_structure(self):
        """Output has header, table, recommended split, and totals."""
        items = [_make_item(1, "Dal 1kg", 1, 100, "Tata", 95, "Tata")]
        result = _make_optimizer_result(
            blinkit_items=items,
            blinkit_subtotal=95, blinkit_delivery_fee=0, blinkit_total=95,
            combined_total=95, all_amazon_total=100, all_blinkit_total=95,
            savings=5,
        )
        output = format_comparison(result, items)

        assert "📊 Price Comparison Results" in output
        assert "ITEM COMPARISON:" in output
        assert "✅ RECOMMENDED SPLIT:" in output
        assert "💰 COMBINED TOTAL:" in output
        assert "Dal 1kg" in output

    def test_quantity_display(self):
        """Items with qty > 1 show 'ea' in table and qty in recommendation."""
        items = [_make_item(1, "Milk 1L", 2, 60, "", 55, "")]
        result = _make_optimizer_result(
            blinkit_items=items,
            blinkit_subtotal=110, blinkit_delivery_fee=0, blinkit_total=110,
            combined_total=110, all_amazon_total=120, all_blinkit_total=110,
            savings=10,
        )
        output = format_comparison(result, items)

        # Table should show "ea" for qty > 1
        assert "₹60 ea" in output
        assert "₹55 ea" in output
        # Recommendation should show quantity math
        assert "x2" in output
        assert "₹55 x2 = ₹110" in output

    def test_na_items_in_table(self):
        """Items unavailable on a platform show N/A in the table."""
        items = [_make_item(1, "Olive Oil 1L", 1, 449, "Figaro", None, None)]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=449, amazon_delivery_fee=0, amazon_total=449,
            combined_total=449, all_amazon_total=449, all_blinkit_total=None,
            savings=0,
        )
        output = format_comparison(result, items)

        assert "N/A" in output
        assert "vs all from Blinkit: N/A" in output

    def test_single_platform_result(self):
        """When all items go to one platform, only that platform section appears."""
        items = [_make_item(1, "Butter 500g", 1, 295, "", 290, "")]
        result = _make_optimizer_result(
            blinkit_items=items,
            blinkit_subtotal=290, blinkit_delivery_fee=25, blinkit_handling_fee=9,
            blinkit_total=324,
            combined_total=324, all_amazon_total=295, all_blinkit_total=324,
            savings=0,
        )
        output = format_comparison(result, items)

        assert "From Blinkit" in output
        assert "From Amazon" not in output

    def test_fee_warning_display(self):
        """Fee warning is shown when fee_warning is True."""
        items = [_make_item(1, "Gum", 1, 10, "", 12, "")]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=10, amazon_delivery_fee=40, amazon_handling_fee=0,
            amazon_total=50,
            combined_total=50, all_amazon_total=50, all_blinkit_total=46,
            savings=0, fee_warning=True,
        )
        output = format_comparison(result, items)

        assert "⚠️ High fee ratio" in output

    def test_no_fee_warning_when_false(self):
        """No fee warning when fee_warning is False."""
        items = [_make_item(1, "Rice 5kg", 1, 400, "", 420, "")]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=400, amazon_delivery_fee=0, amazon_total=400,
            combined_total=400, all_amazon_total=400, all_blinkit_total=420,
            savings=20, fee_warning=False,
        )
        output = format_comparison(result, items)

        assert "⚠️" not in output

    def test_cashback_display(self):
        """Cashback is displayed in the platform section."""
        items = [_make_item(1, "Rice 5kg", 1, 500, "", 520, "")]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=500, amazon_delivery_fee=0, amazon_cashback=50,
            amazon_total=450,
            combined_total=450, all_amazon_total=450, all_blinkit_total=520,
            savings=70,
        )
        output = format_comparison(result, items)

        assert "Cashback: ₹50" in output

    def test_handling_fee_displayed_when_nonzero(self):
        """Handling fee line is shown for non-zero values."""
        items = [_make_item(1, "Eggs 12pc", 1, 80, "", 75, "")]
        result = _make_optimizer_result(
            blinkit_items=items,
            blinkit_subtotal=75, blinkit_delivery_fee=25, blinkit_handling_fee=9,
            blinkit_total=109,
            combined_total=109, all_amazon_total=80, all_blinkit_total=109,
            savings=0,
        )
        output = format_comparison(result, items)

        assert "Handling: ₹9" in output

    def test_handling_fee_hidden_when_zero(self):
        """Handling fee line is NOT shown when it is 0 (e.g., Amazon)."""
        items = [_make_item(1, "Bread", 1, 45, "", 50, "")]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=45, amazon_delivery_fee=0, amazon_handling_fee=0,
            amazon_total=45,
            combined_total=45, all_amazon_total=45, all_blinkit_total=50,
            savings=5,
        )
        output = format_comparison(result, items)

        assert "Handling" not in output

    def test_brand_in_table_and_recommendation(self):
        """Brand appears in parentheses in table and after dash in recommendation."""
        items = [_make_item(1, "Olive Oil 1L", 1, 449, "Figaro", None, None)]
        result = _make_optimizer_result(
            amazon_items=items,
            amazon_subtotal=449, amazon_delivery_fee=0, amazon_total=449,
            combined_total=449, all_amazon_total=449, all_blinkit_total=None,
        )
        output = format_comparison(result, items)

        assert "(Figaro)" in output  # table brand row
        assert "— Figaro —" in output  # recommendation line


# ---------------------------------------------------------------------------
# split_message tests
# ---------------------------------------------------------------------------

class TestSplitMessage:
    def test_fits_in_single_message(self):
        """Short text returns as single-element list."""
        text = "Hello world"
        assert split_message(text) == ["Hello world"]

    def test_split_at_section_boundary(self):
        """Splits at the ✅ RECOMMENDED SPLIT marker."""
        table = "A" * 3000
        rec = "✅ RECOMMENDED SPLIT:\n" + "B" * 3000
        text = table + "\n" + rec

        parts = split_message(text, max_length=4096)
        assert len(parts) == 2
        assert parts[0].endswith("A" * 100)  # table part
        assert "✅ RECOMMENDED SPLIT:" in parts[1]

    def test_split_at_row_boundaries_when_table_exceeds_limit(self):
        """When the table section alone exceeds max_length, split at ├ lines."""
        # Build a long table with ├ row separators
        header = "ITEM COMPARISON:\n┌────┬────┐\n│ H1 │ H2 │\n├────┼────┤"
        rows = []
        for i in range(50):
            rows.append(f"│ Item {i:>3} │ ₹{i*10:>4} │")
            rows.append("├────┼────┤")
        table = header + "\n" + "\n".join(rows) + "\n└────┴────┘"

        rec = "\n✅ RECOMMENDED SPLIT:\nShort recommendation."
        text = table + rec

        parts = split_message(text, max_length=500)

        assert len(parts) >= 2
        for part in parts:
            assert len(part) <= 500

    def test_hard_split_fallback(self):
        """When no markers exist, hard-split at newlines."""
        lines = ["Line " + str(i) for i in range(200)]
        text = "\n".join(lines)

        parts = split_message(text, max_length=200)
        assert len(parts) >= 2
        for part in parts:
            assert len(part) <= 200

    def test_no_chunk_exceeds_max_length(self):
        """Regardless of input, no chunk exceeds max_length."""
        items = [_make_item(i, f"Very Long Item Name Number {i}", 2, 100 + i, "Brand", 110 + i, "Brand") for i in range(30)]
        result = _make_optimizer_result(
            amazon_items=items[:15], blinkit_items=items[15:],
            amazon_subtotal=2000, blinkit_subtotal=2500,
            amazon_delivery_fee=0, blinkit_delivery_fee=25, blinkit_handling_fee=9,
            amazon_total=2000, blinkit_total=2534,
            combined_total=4534, all_amazon_total=5000, all_blinkit_total=5500,
            savings=466,
        )
        output = format_comparison(result, items)
        parts = split_message(output, max_length=500)
        for part in parts:
            assert len(part) <= 500


# ---------------------------------------------------------------------------
# format_unavailable tests
# ---------------------------------------------------------------------------

class TestFormatUnavailable:
    def test_empty_list(self):
        assert format_unavailable([]) == ""

    def test_single_item(self):
        out = format_unavailable([{"name": "Exotic Cheese"}])
        assert "⚠️ Not found on any platform:" in out
        assert "Exotic Cheese" in out

    def test_multiple_items(self):
        items = [{"name": "Item A"}, {"name": "Item B"}]
        out = format_unavailable(items)
        assert "Item A" in out
        assert "Item B" in out
