"""Tests for logger.py."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from logger import log_run, log_prices


class TestLogRun:
    def test_creates_log_file(self, tmp_path):
        log_dir = str(tmp_path / "logs")
        run_data = {
            "timestamp": "2026-03-26T10:00:00",
            "selected_items": [{"id": 1, "qty": 2}],
            "platforms": {
                "amazon": {"status": "success", "items_found": 1, "items_not_found": 0, "fees": {}, "session_valid": True},
                "blinkit": {"status": "success", "items_found": 1, "items_not_found": 0, "fees": {}, "session_valid": True},
            },
            "recommendation": {},
            "total_cost": 500,
            "run_duration_seconds": 60,
        }
        filepath = log_run(log_dir, run_data)
        assert os.path.exists(filepath)
        assert filepath.endswith("run_20260326_100000.json")

    def test_log_file_content_matches(self, tmp_path):
        log_dir = str(tmp_path / "logs")
        run_data = {
            "timestamp": "2026-03-26T10:00:00",
            "selected_items": [{"id": 1, "qty": 2}, {"id": 4, "qty": 1}],
            "platforms": {
                "amazon": {"status": "success", "items_found": 2, "items_not_found": 0, "fees": {"delivery_fee": 0}, "session_valid": True},
            },
            "recommendation": {"amazon": [1, 4]},
            "total_cost": 1234,
            "run_duration_seconds": 120,
        }
        filepath = log_run(log_dir, run_data)
        with open(filepath) as f:
            saved = json.load(f)
        assert saved["timestamp"] == "2026-03-26T10:00:00"
        assert saved["selected_items"] == [{"id": 1, "qty": 2}, {"id": 4, "qty": 1}]
        assert saved["total_cost"] == 1234
        assert saved["run_duration_seconds"] == 120

    def test_creates_log_dir_if_missing(self, tmp_path):
        log_dir = str(tmp_path / "nested" / "logs")
        run_data = {
            "timestamp": "2026-01-01T00:00:00",
            "selected_items": [],
            "platforms": {},
            "recommendation": {},
            "total_cost": 0,
            "run_duration_seconds": 0,
        }
        filepath = log_run(log_dir, run_data)
        assert os.path.exists(filepath)

    def test_session_expired_platform(self, tmp_path):
        log_dir = str(tmp_path / "logs")
        run_data = {
            "timestamp": "2026-03-26T12:00:00",
            "selected_items": [{"id": 1, "qty": 1}],
            "platforms": {
                "amazon": {"status": "success", "items_found": 1, "items_not_found": 0, "fees": {}, "session_valid": True},
                "blinkit": {"status": "session_expired"},
            },
            "recommendation": {},
            "total_cost": 135,
            "run_duration_seconds": 90,
        }
        filepath = log_run(log_dir, run_data)
        with open(filepath) as f:
            saved = json.load(f)
        assert saved["platforms"]["blinkit"]["status"] == "session_expired"


class TestLogPrices:
    def test_appends_price_records(self, tmp_path):
        history_dir = str(tmp_path / "price_history")
        items = [
            {"id": 1, "name": "Toor Dal 1kg", "amazon": {"price": 135, "brand": "Tata"}, "blinkit": {"price": 128, "brand": "Tata"}},
            {"id": 2, "name": "Amul Butter 500g", "amazon": {"price": 295, "brand": "Amul"}, "blinkit": {"price": 290, "brand": "Amul"}},
        ]
        filepath = log_prices(history_dir, items)
        assert os.path.exists(filepath)

        with open(filepath) as f:
            lines = f.readlines()
        assert len(lines) == 2

        record1 = json.loads(lines[0])
        assert record1["item_id"] == 1
        assert record1["item_name"] == "Toor Dal 1kg"
        assert record1["amazon_price"] == 135
        assert record1["amazon_brand"] == "Tata"
        assert record1["blinkit_price"] == 128
        assert "amazon_status" not in record1
        assert "blinkit_status" not in record1

    def test_unavailable_items_have_null_and_status(self, tmp_path):
        history_dir = str(tmp_path / "price_history")
        items = [
            {"id": 3, "name": "Olive Oil 1L", "amazon": {"price": 449, "brand": "Figaro"}, "blinkit": None},
        ]
        filepath = log_prices(history_dir, items)

        with open(filepath) as f:
            record = json.loads(f.readline())
        assert record["amazon_price"] == 449
        assert record["blinkit_price"] is None
        assert record["blinkit_brand"] is None
        assert record["blinkit_status"] == "unavailable"
        assert "amazon_status" not in record

    def test_session_expired_status(self, tmp_path):
        history_dir = str(tmp_path / "price_history")
        items = [
            {"id": 1, "name": "Toor Dal 1kg", "amazon": None, "blinkit": {"price": 128, "brand": "Tata"}, "amazon_status": "session_expired"},
        ]
        filepath = log_prices(history_dir, items)

        with open(filepath) as f:
            record = json.loads(f.readline())
        assert record["amazon_price"] is None
        assert record["amazon_brand"] is None
        assert record["amazon_status"] == "session_expired"
        assert record["blinkit_price"] == 128

    def test_appends_to_existing_file(self, tmp_path):
        history_dir = str(tmp_path / "price_history")
        items1 = [{"id": 1, "name": "Item A", "amazon": {"price": 100, "brand": "X"}, "blinkit": None}]
        items2 = [{"id": 2, "name": "Item B", "amazon": None, "blinkit": {"price": 200, "brand": "Y"}}]

        log_prices(history_dir, items1)
        log_prices(history_dir, items2)

        filepath = os.path.join(history_dir, "prices.jsonl")
        with open(filepath) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["item_id"] == 1
        assert json.loads(lines[1])["item_id"] == 2

    def test_creates_history_dir_if_missing(self, tmp_path):
        history_dir = str(tmp_path / "nested" / "history")
        items = [{"id": 1, "name": "Test", "amazon": {"price": 50, "brand": "B"}, "blinkit": {"price": 60, "brand": "C"}}]
        filepath = log_prices(history_dir, items)
        assert os.path.exists(filepath)

    def test_both_platforms_unavailable(self, tmp_path):
        history_dir = str(tmp_path / "price_history")
        items = [
            {"id": 5, "name": "Ghost Item", "amazon": None, "blinkit": None, "amazon_status": "session_expired", "blinkit_status": "unavailable"},
        ]
        filepath = log_prices(history_dir, items)

        with open(filepath) as f:
            record = json.loads(f.readline())
        assert record["amazon_price"] is None
        assert record["blinkit_price"] is None
        assert record["amazon_status"] == "session_expired"
        assert record["blinkit_status"] == "unavailable"
