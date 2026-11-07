"""Preset/journal tests use injected drivers only; no window or input APIs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import grocery_plan as gp


class Driver:
    def __init__(self, path=None):
        self.balances = {shop: 10000 for shop in gp.SHOPS}
        self.stock = {}
        self.prices = {}
        self.calls = []
        self.begin_calls = 0
        self.path = path
        self.after_purchase = None

    def begin(self):
        self.begin_calls += 1
        return dict(self.balances)

    def inspect(self, item):
        return {"verified": True, "unit_price": self.prices.get(item["key"], 10),
                "stock": self.stock.get(item["key"], 100), "balances": dict(self.balances)}

    def purchase(self, item, quantity, inspection):
        if self.path:
            saved = gp.load_state(self.path)
            current = next(row for row in saved["items"] if row["key"] == item["key"])
            if current["status"] != "uncertain":
                raise AssertionError("Consuming input preceded durable uncertain boundary")
        self.calls.append((item["key"], quantity))
        self.balances[item["shop"]] -= quantity * inspection["unit_price"]
        self.stock[item["key"]] = inspection["stock"] - quantity
        result = {"verified": True, "quantity": quantity, "stock": self.stock[item["key"]],
                  "balances": dict(self.balances)}
        if self.after_purchase:
            self.after_purchase()
        return result


class GroceryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = gp.load_catalog()
        cls.by_shop = {shop: [item for item in cls.catalog if item["shop"] == shop] for shop in gp.SHOPS}
        cls.temp_root = gp.ROOT / "verification/grocery-tool-tests"
        cls.temp_root.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="plan-", dir=self.temp_root)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.path = self.root / "state.json"
        self.plan = self.root / "plan.json"

    def selected(self, *entries):
        quantities = {entry["key"]: count for entry, count in entries}
        return gp.new_state(self.catalog, quantities)

    def test_catalog_order_and_shared_icon_product_keys_are_distinct(self):
        self.assertEqual(len(self.catalog), 141)
        self.assertEqual(len({item["key"] for item in self.catalog}), 141)
        self.assertEqual([len(self.by_shop[shop]) for shop in gp.SHOPS], [25, 38, 61, 17])
        aliases = [item for item in self.by_shop["sign"] if item["asset"] == "item_10100000"]
        self.assertEqual(len(aliases), 36)
        self.assertEqual(len({item["key"] for item in aliases}), 36)
        self.assertEqual([item["currency"] for item in [self.by_shop[shop][0] for shop in gp.SHOPS]],
                         ["日之币", "月之币", "签到令", "奇怪的石头"])

    def test_quantity_accepts_only_nonnegative_integers(self):
        for raw, expected in [(0, 0), (52, 52), ("0", 0), (" 003 ", 3), ("90000", 90000)]:
            self.assertEqual(gp.parse_quantity(raw), expected)
        for raw in [True, False, -1, 1.0, "1.0", "-1", "+1", "1e3", "", " ", None, "二", "１"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                gp.parse_quantity(raw)

    def test_preset_default_roundtrip_and_invalid_edit_preserve_file(self):
        blank = gp.load_plan(self.plan, self.catalog)
        self.assertEqual(set(blank.values()), {0})
        key = self.catalog[0]["key"]
        gp.save_plan(self.plan, {key: "5"}, self.catalog)
        before = self.plan.read_bytes()
        self.assertEqual(gp.load_plan(self.plan, self.catalog)[key], 5)
        with self.assertRaises(ValueError):
            gp.save_plan(self.plan, {key: "5.5"}, self.catalog)
        self.assertEqual(before, self.plan.read_bytes())
        with self.assertRaises(ValueError):
            gp.save_plan(self.plan, {"not-a-current-item": 2}, self.catalog)
        self.assertEqual(before, self.plan.read_bytes())

    def test_missing_and_corrupt_journal_are_distinguished(self):
        self.assertIsNone(gp.load_state(self.path))
        self.path.write_text('{"unexpected":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            gp.load_state(self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"unexpected":true}')

    def test_new_round_is_a_snapshot_and_does_not_select_zero_items(self):
        original = deepcopy(self.catalog)
        key = original[0]["key"]
        quantities = {key: 3, original[1]["key"]: 0}
        state = gp.new_state(original, quantities)
        quantities[key] = 8
        original[0]["name"] = "changed"
        self.assertEqual(len(state["items"]), 1)
        self.assertEqual(state["items"][0]["quantity"], 3)
        self.assertEqual(state["items"][0]["name"], self.catalog[0]["name"])

    def test_four_shop_run_obeys_catalog_order_and_records_balances(self):
        entries = [self.by_shop[shop][0] for shop in gp.SHOPS]
        state = gp.new_state(self.catalog, {item["key"]: 2 for item in reversed(entries)})
        driver = Driver(self.path)
        events = []
        gp.run_state(state, self.path, driver, events.append)
        self.assertEqual(state["status"], "done")
        self.assertEqual(driver.calls, [(item["key"], 2) for item in entries])
        self.assertEqual(state["balances_start"], {shop: 10000 for shop in gp.SHOPS})
        self.assertEqual(state["balances_end"], {shop: 9980 for shop in gp.SHOPS})
        self.assertTrue(state["balances_read_at"])
        self.assertTrue(any(event["kind"] == "balance" for event in events))
        self.assertEqual(gp.load_state(self.path)["status"], "done")

    def test_insufficient_full_stock_or_currency_skips_without_partial_purchase(self):
        entries = self.by_shop["sun"][:3]
        state = self.selected(*[(item, 5) for item in entries])
        driver = Driver(self.path)
        driver.stock[entries[0]["key"]] = 4
        driver.prices[entries[1]["key"]] = 3000
        gp.run_state(state, self.path, driver)
        self.assertEqual(state["status"], "done")
        self.assertEqual([item["status"] for item in state["items"]], ["skipped", "skipped", "done"])
        self.assertEqual(driver.calls, [(entries[2]["key"], 5)])

    def test_purchase_timeout_leaves_durable_uncertainty_and_cannot_replay(self):
        state = self.selected((self.catalog[0], 2), (self.catalog[1], 2))
        driver = Driver(self.path)
        def uncertain(*args):
            driver.calls.append((args[0]["key"], args[1]))
            raise TimeoutError("input outcome unknown")
        driver.purchase = uncertain
        gp.run_state(state, self.path, driver)
        self.assertEqual(state["status"], "needs_review")
        self.assertEqual(state["items"][0]["completed"], 0)
        loaded = gp.load_state(self.path)
        second = Driver(self.path)
        gp.run_state(loaded, self.path, second)
        self.assertEqual(loaded["status"], "needs_review")
        self.assertEqual(second.begin_calls, 0)
        self.assertEqual(second.calls, [])
        self.assertEqual(len(driver.calls), 1)

    def test_deduction_mismatch_cannot_confirm_purchase(self):
        state = self.selected((self.catalog[0], 2))
        driver = Driver(self.path)
        purchase = driver.purchase
        def mismatching(*args):
            result = purchase(*args)
            result["balances"]["sun"] += 1
            return result
        driver.purchase = mismatching
        gp.run_state(state, self.path, driver)
        self.assertEqual(state["status"], "needs_review")
        self.assertEqual(state["items"][0]["completed"], 0)
        self.assertEqual(len(driver.calls), 1)

    def test_stock_mismatch_or_unverified_result_cannot_confirm_purchase(self):
        for change in (lambda result: result.update(stock=100), lambda result: result.update(verified=False)):
            with self.subTest(change=change):
                state = self.selected((self.catalog[0], 2))
                driver = Driver(self.path)
                purchase = driver.purchase
                def mismatching(*args):
                    result = purchase(*args)
                    change(result)
                    return result
                driver.purchase = mismatching
                gp.run_state(state, self.path, driver)
                self.assertEqual(state["status"], "needs_review")
                self.assertEqual(state["items"][0]["completed"], 0)

    def test_unverified_inspection_stops_before_consuming_input(self):
        state = self.selected((self.catalog[0], 2))
        driver = Driver(self.path)
        driver.inspect = lambda item: {"verified": False}
        gp.run_state(state, self.path, driver)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(driver.calls, [])
        self.assertEqual(state["items"][0]["status"], "pending")

    def test_incomplete_balance_stops_before_any_purchase(self):
        state = self.selected((self.catalog[0], 2))
        driver = Driver(self.path)
        driver.begin = lambda: {"sun": 10000}
        gp.run_state(state, self.path, driver)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(driver.calls, [])

    def test_journal_save_failure_blocks_consuming_input(self):
        state = self.selected((self.catalog[0], 2))
        driver = Driver(self.path)
        original = gp._write_json
        def cannot_write_uncertain(path, data):
            if any(item["status"] == "uncertain" for item in data["items"]):
                raise OSError("disk unavailable")
            return original(path, data)
        with patch.object(gp, "_write_json", side_effect=cannot_write_uncertain):
            gp.run_state(state, self.path, driver)
        self.assertEqual(driver.calls, [])
        self.assertEqual(gp.load_state(self.path)["items"][0]["status"], "pending")
        self.assertIn("disk unavailable", state["last_error"])

    def test_stop_then_resume_never_rebuys_confirmed_item(self):
        entries = self.catalog[:2]
        state = self.selected((entries[0], 2), (entries[1], 3))
        stop = threading.Event()
        driver = Driver(self.path)
        driver.after_purchase = stop.set
        gp.run_state(state, self.path, driver, stop_event=stop)
        self.assertEqual(state["status"], "stopped")
        self.assertEqual([item["completed"] for item in state["items"]], [2, 0])
        driver.after_purchase = None
        stop.clear()
        gp.run_state(gp.load_state(self.path), self.path, driver, stop_event=stop)
        self.assertEqual(driver.calls, [(entries[0]["key"], 2), (entries[1]["key"], 3)])
        self.assertEqual(gp.load_state(self.path)["status"], "done")

    def test_stop_after_inspection_does_not_send_current_purchase(self):
        state = self.selected((self.catalog[0], 2))
        stop = threading.Event()
        driver = Driver(self.path)
        inspect = driver.inspect
        def stop_inspect(item):
            result = inspect(item)
            stop.set()
            return result
        driver.inspect = stop_inspect
        gp.run_state(state, self.path, driver, stop_event=stop)
        self.assertEqual(driver.calls, [])
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["items"][0]["status"], "pending")

    def test_partial_confirmed_quantity_only_buys_remaining(self):
        state = self.selected((self.catalog[0], 5))
        state["items"][0]["completed"] = 2
        driver = Driver(self.path)
        gp.run_state(state, self.path, driver)
        self.assertEqual(driver.calls, [(self.catalog[0]["key"], 3)])
        self.assertEqual(state["items"][0]["completed"], 5)

    def test_done_round_does_not_restart_without_explicit_new_state(self):
        state = self.selected((self.catalog[0], 2))
        driver = Driver(self.path)
        gp.run_state(state, self.path, driver)
        gp.run_state(gp.load_state(self.path), self.path, driver)
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(driver.begin_calls, 1)
        fresh = self.selected((self.catalog[0], 2))
        self.assertNotEqual(fresh["run_id"], state["run_id"])
        gp.run_state(fresh, self.path, driver)
        self.assertEqual(len(driver.calls), 2)


if __name__ == "__main__":
    unittest.main()
