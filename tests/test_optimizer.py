import logging
from src.optimizer import optimize_cart


def _make_item(id, name, qty, amazon_price=None, blinkit_price=None,
               amazon_brand="", blinkit_brand=""):
    prices = {}
    if amazon_price is not None:
        prices["amazon"] = {"price": amazon_price, "brand": amazon_brand}
    if blinkit_price is not None:
        prices["blinkit"] = {"price": blinkit_price, "brand": blinkit_brand}
    return {"id": id, "name": name, "qty": qty, "prices": prices}


def _default_fees():
    return {
        "amazon": {
            "delivery_fee": 40.0,
            "handling_fee": 0.0,
            "free_delivery_threshold": 99.0,
            "cashback_tiers": [],
        },
        "blinkit": {
            "delivery_fee": 25.0,
            "handling_fee": 9.0,
            "free_delivery_threshold": 199.0,
            "cashback_tiers": [],
        },
    }


class TestAllItemsOnOnePlatform:
    def test_all_amazon_only(self):
        items = [
            _make_item(1, "Dal", 1, amazon_price=100),
            _make_item(2, "Rice", 1, amazon_price=200),
        ]
        result = optimize_cart(items, _default_fees())
        assert len(result["recommendation"]["amazon"]) == 2
        assert len(result["recommendation"]["blinkit"]) == 0
        assert result["amazon_subtotal"] == 300.0
        assert result["blinkit_subtotal"] == 0.0
        assert result["all_blinkit_total"] is None

    def test_all_blinkit_only(self):
        items = [
            _make_item(1, "Dal", 1, blinkit_price=100),
            _make_item(2, "Rice", 1, blinkit_price=200),
        ]
        result = optimize_cart(items, _default_fees())
        assert len(result["recommendation"]["blinkit"]) == 2
        assert len(result["recommendation"]["amazon"]) == 0
        assert result["all_amazon_total"] is None


class TestSplitAcrossPlatforms:
    def test_items_split_to_cheaper(self):
        items = [
            _make_item(1, "Dal", 1, amazon_price=100, blinkit_price=150),
            _make_item(2, "Rice", 1, amazon_price=200, blinkit_price=120),
        ]
        fees = _default_fees()
        # Both subtotals above thresholds, so free delivery on both
        fees["amazon"]["free_delivery_threshold"] = 50.0
        fees["blinkit"]["free_delivery_threshold"] = 50.0
        fees["blinkit"]["handling_fee"] = 0.0

        result = optimize_cart(items, fees)
        amazon_ids = {i["id"] for i in result["recommendation"]["amazon"]}
        blinkit_ids = {i["id"] for i in result["recommendation"]["blinkit"]}
        # Dal cheaper on Amazon (100 vs 150), Rice cheaper on Blinkit (120 vs 200)
        assert 1 in amazon_ids
        assert 2 in blinkit_ids


class TestSingleItem:
    def test_single_item_amazon_only(self):
        items = [_make_item(1, "Butter", 1, amazon_price=250)]
        result = optimize_cart(items, _default_fees())
        assert len(result["recommendation"]["amazon"]) == 1
        assert result["amazon_subtotal"] == 250.0

    def test_single_dual_item(self):
        items = [_make_item(1, "Butter", 1, amazon_price=250, blinkit_price=240)]
        fees = _default_fees()
        # Make fees equal to isolate price difference
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["handling_fee"] = 0.0
        result = optimize_cart(items, fees)
        assert len(result["recommendation"]["blinkit"]) == 1


class TestDeliveryFeeWaiver:
    def test_fee_waived_above_threshold(self):
        items = [_make_item(1, "Dal", 1, amazon_price=150)]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 99.0
        fees["amazon"]["delivery_fee"] = 40.0
        result = optimize_cart(items, fees)
        assert result["amazon_delivery_fee"] == 0.0  # 150 >= 99

    def test_fee_not_waived_below_threshold(self):
        items = [_make_item(1, "Dal", 1, amazon_price=50)]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 99.0
        fees["amazon"]["delivery_fee"] = 40.0
        result = optimize_cart(items, fees)
        assert result["amazon_delivery_fee"] == 40.0  # 50 < 99


class TestCashback:
    def test_cashback_applied(self):
        items = [_make_item(1, "Groceries", 1, amazon_price=500)]
        fees = _default_fees()
        fees["amazon"]["cashback_tiers"] = [
            {"min_order": 399, "cashback": 50},
            {"min_order": 749, "cashback": 100},
        ]
        result = optimize_cart(items, fees)
        assert result["amazon_cashback"] == 50.0  # 500 >= 399 but < 749

    def test_highest_applicable_cashback(self):
        items = [_make_item(1, "Groceries", 1, amazon_price=800)]
        fees = _default_fees()
        fees["amazon"]["cashback_tiers"] = [
            {"min_order": 399, "cashback": 50},
            {"min_order": 749, "cashback": 100},
        ]
        result = optimize_cart(items, fees)
        assert result["amazon_cashback"] == 100.0  # 800 >= 749

    def test_no_cashback_tiers(self):
        items = [_make_item(1, "Groceries", 1, amazon_price=500)]
        fees = _default_fees()
        result = optimize_cart(items, fees)
        assert result["amazon_cashback"] == 0.0


class TestGreedyFallback:
    def test_large_item_list_triggers_greedy(self, caplog):
        items = [
            _make_item(i, f"Item{i}", 1, amazon_price=100 + i, blinkit_price=100 + (21 - i))
            for i in range(1, 22)
        ]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["handling_fee"] = 0.0

        with caplog.at_level(logging.WARNING):
            result = optimize_cart(items, fees)

        assert "greedy" in caplog.text.lower()
        assert result["combined_total"] > 0


class TestFeeWarning:
    def test_fee_warning_triggered(self):
        # Item cost 30, delivery 40 + handling 9 = 49 fees > 20% of 30 = 6
        items = [_make_item(1, "Small", 1, blinkit_price=30)]
        fees = _default_fees()
        fees["blinkit"]["free_delivery_threshold"] = 199.0
        result = optimize_cart(items, fees)
        assert result["fee_warning"] is True

    def test_fee_warning_not_triggered(self):
        # Item cost 500, delivery free (>199), handling 9 => 9/500 = 1.8%
        items = [_make_item(1, "Big", 1, blinkit_price=500)]
        fees = _default_fees()
        result = optimize_cart(items, fees)
        assert result["fee_warning"] is False


class TestSavings:
    def test_savings_zero_when_single_platform_optimal(self):
        items = [_make_item(1, "Dal", 1, amazon_price=100)]
        result = optimize_cart(items, _default_fees())
        assert result["savings"] == 0.0

    def test_savings_positive_when_split_is_cheaper(self):
        items = [
            _make_item(1, "Dal", 1, amazon_price=80, blinkit_price=200),
            _make_item(2, "Rice", 1, amazon_price=200, blinkit_price=80),
        ]
        fees = _default_fees()
        fees["amazon"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["free_delivery_threshold"] = 0.0
        fees["blinkit"]["handling_fee"] = 0.0
        result = optimize_cart(items, fees)
        # Split: 80 + 80 = 160. All amazon: 280. All blinkit: 280.
        assert result["savings"] > 0


class TestAllPlatformTotals:
    def test_all_amazon_total_none_when_item_missing(self):
        items = [
            _make_item(1, "Dal", 1, amazon_price=100, blinkit_price=120),
            _make_item(2, "Rice", 1, blinkit_price=80),  # no amazon
        ]
        result = optimize_cart(items, _default_fees())
        assert result["all_amazon_total"] is None
        assert result["all_blinkit_total"] is not None


class TestHandlingFee:
    def test_handling_fee_applied_even_when_delivery_free(self):
        items = [_make_item(1, "Dal", 1, blinkit_price=300)]
        fees = _default_fees()
        fees["blinkit"]["handling_fee"] = 9.0
        fees["blinkit"]["free_delivery_threshold"] = 199.0
        result = optimize_cart(items, fees)
        assert result["blinkit_delivery_fee"] == 0.0  # 300 >= 199
        assert result["blinkit_handling_fee"] == 9.0
        assert result["blinkit_total"] == 300.0 + 9.0
