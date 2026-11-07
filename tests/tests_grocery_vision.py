"""Read-only image fixtures and injected transaction observers; no game input."""
from pathlib import Path
import json
import threading
import tempfile
import unittest

from grocery_driver import GroceryDriver, capability_summary
from grocery_recognition import ASSET_ROOT
from grocery_vision import GroceryRecognitionError, GroceryVision, to_rgb
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ScriptedOCR:
    def __init__(self, results):
        self.results = iter(results)

    def read(self, image, only_rec=False):
        value = next(self.results)
        return value if isinstance(value, list) else [{"text": value, "score": .99}]


class FakeObserver:
    supports_verified_purchase = True

    def __init__(self):
        self.balances = {"sun": 500, "moon": 200, "sign": 20, "mystery": 10}
        self.stock = 50
        self.submits = 0
        self.bad_ready = False
        self.bad_result = False

    def begin(self):
        return dict(self.balances)

    def inspect(self, item):
        return {"verified": True, "shop": item["shop"], "asset": item["asset"], "name": item["name"],
                "unit_price": 50, "stock": self.stock, "quantity": 1, "balances": dict(self.balances)}

    def prepare_quantity(self, item, quantity, inspection):
        self.quantity = quantity

    def confirm_ready(self, item, quantity, inspection):
        data = self.inspect(item)
        data["quantity"] = quantity + int(self.bad_ready)
        return data

    def submit_once(self, item, quantity, before):
        self.submits += 1
        self.balances[item["shop"]] -= before["unit_price"] * quantity
        self.stock -= quantity

    def verify_result(self, item, quantity, before):
        data = {"verified": not self.bad_result, "quantity": quantity, "balances": dict(self.balances), "stock": self.stock}
        return data


class GroceryVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with Image.open(ASSET_ROOT / "sources/user-game.png") as image:
            cls.game = image.convert("RGB").crop((45, 131, 1965, 1146))
        cls.vision = GroceryVision()

    def test_real_page_anchors_and_sun_activation(self):
        self.assertEqual(self.vision.selected_shop(self.game), "sun")

    def test_other_image_cannot_supply_page_anchors(self):
        with self.assertRaises(GroceryRecognitionError):
            self.vision.require_page(Image.new("RGB", (1920, 1015), "black"))

    def test_independent_live_village_frame_cannot_be_read_as_grocery_balances(self):
        with Image.open(ROOT / 'verification/grocery-tool-20261026/live-initial.png') as home:
            with self.assertRaises(GroceryRecognitionError):
                self.vision.read_balances(home)

    def test_dimmed_modal_background_is_not_a_confirmed_page(self):
        dark = Image.fromarray((np.asarray(self.game, dtype=np.float32)*.5).astype(np.uint8))
        with self.assertRaises(GroceryRecognitionError):
            self.vision.require_page(dark)

    def test_bgr_conversion_and_calibration_size(self):
        array = np.asarray(self.game)[:, :, ::-1].copy()
        self.assertEqual(to_rgb(array).getpixel((900, 300)), self.game.getpixel((900, 300)))
        with self.assertRaises(GroceryRecognitionError):
            to_rgb(Image.new("RGB", (2010, 1191)))

    def test_live_november_page_rounding_and_low_contrast_five_digit_sign(self):
        image=Image.open(ROOT/'verification/grocery-ui-10potions-live-20261106/game-read-failed.png')
        vision=GroceryVision()
        self.assertEqual(vision.read_balances(image),{'sun':13609,'moon':403945,'sign':10000,'mystery':321})
        self.assertTrue(all(abs(row['offset'][1])<=2 for row in vision.last_evidence['page']))
        self.assertEqual(vision.last_evidence['balances']['sign']['threshold'],[100,140])

    def test_currency_reads_require_complete_pure_numbers(self):
        vision = GroceryVision(ocr=ScriptedOCR(["13609", "13609", "320565", "320565", "8300", "8300", "321", "321"]))
        self.assertEqual(vision.read_balances(self.game), {"sun": 13609, "moon": 320565, "sign": 8300, "mystery": 321})

    def test_real_current_balances_do_not_turn_six_into_zero(self):
        vision = GroceryVision()
        with Image.open(ROOT/'verification/grocery-read-fix-20261031/0001-balances.png') as image:
            self.assertEqual(vision.read_balances(image),
                             {'sun': 13609, 'moon': 360680, 'sign': 9600, 'mystery': 321})

    def test_independent_prior_balance_frame_uses_same_number_processing(self):
        vision = GroceryVision()
        with Image.open(ROOT/'verification/grocery-key-live-20261031/key-preflight-1.png') as image:
            self.assertEqual(vision.read_balances(image),
                             {'sun': 13609, 'moon': 361080, 'sign': 9600, 'mystery': 321})

    def test_ocr_conflict_is_not_voted_away(self):
        vision = GroceryVision(ocr=ScriptedOCR(["13609", "13608"]))
        with self.assertRaisesRegex(GroceryRecognitionError, "冲突"):
            vision.read_balances(self.game)

    def test_ocr_letter_substitution_is_rejected(self):
        vision = GroceryVision(ocr=ScriptedOCR(["13G09", "13609"]))
        with self.assertRaises(GroceryRecognitionError):
            vision.read_balances(self.game)

    def test_low_confidence_and_multiple_numeric_results_are_rejected(self):
        for results in ([{"text": "13609", "score": .84}],
                        [{"text": "13609", "score": .99}, {"text": "1", "score": .99}]):
            with self.subTest(results=results), self.assertRaises(GroceryRecognitionError):
                GroceryVision(ocr=ScriptedOCR([results])).read_balances(self.game)

    def test_real_local_ocr_currency_sample(self):
        from adapters.local_ocr import LocalOCR
        vision = GroceryVision(ocr=LocalOCR())
        self.assertEqual(vision.read_balances(self.game), {"sun": 13609, "moon": 320565, "sign": 8300, "mystery": 321})

    def test_real_card_live_fields_and_name_anchor(self):
        from adapters.local_ocr import LocalOCR
        expected = ((50, 50), (25, 50), (50, 50), (150, 50), (500, 100), (200, 200),
                    (400, 10), (400, 10), (400, 10), (400, 10), (400, 10), (100, 100))
        vision = GroceryVision(ocr=LocalOCR())
        for original, (price, stock) in zip(self.vision.recognizer.shops["sun"]["items"][:12], expected):
            item = dict(original, shop="sun", key=original["asset"])
            with self.subTest(name=item["name"]):
                result = vision.inspect_visible_item(self.game, item)
                self.assertTrue(result["verified"])
                self.assertEqual((result["unit_price"], result["stock"], result["quantity"]), (price, stock, 1))

    def test_requested_name_cannot_be_replaced_while_reusing_an_icon_id(self):
        item = dict(self.vision.recognizer.shops["sun"]["items"][0], shop="sun", key="renamed", name="其他商品")
        with self.assertRaisesRegex(GroceryRecognitionError, "目录身份"):
            self.vision.inspect_visible_item(self.game, item)


class GroceryDriverTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "verification/grocery-driver-test-temp"
        base.mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.folder.cleanup)
        self.observer = FakeObserver()
        self.item = {"key": "seal", "shop": "sun", "asset": "item_10800050", "name": "封印碎片"}
        self.driver = GroceryDriver(0, evidence_dir=self.folder.name, observer=self.observer)
        self.driver.begin()

    def test_production_capability_is_limited_to_evidenced_moon_items(self):
        result = capability_summary()
        self.assertTrue(result["supported_read"])
        self.assertTrue(result["live_purchase_supported"])
        self.assertEqual(set(result["supported_item_ids"]), {"10800057", "10840089"})

    def test_verified_purchase_confirms_currency_and_stock(self):
        inspection = self.driver.inspect(self.item)
        result = self.driver.purchase(self.item, 3, inspection)
        self.assertEqual(result["balances"]["sun"], 350)
        self.assertEqual(result["stock"], 47)
        self.assertEqual(result["quantity"], 3)
        self.assertEqual(self.observer.submits, 1)

    def test_consumed_token_cannot_repeat_purchase(self):
        inspection = self.driver.inspect(self.item)
        self.driver.purchase(self.item, 1, inspection)
        with self.assertRaisesRegex(RuntimeError, "凭据"):
            self.driver.purchase(self.item, 1, inspection)
        self.assertEqual(self.observer.submits, 1)

    def test_changed_observation_cannot_be_sent(self):
        inspection = self.driver.inspect(self.item)
        inspection["unit_price"] = 1
        with self.assertRaisesRegex(RuntimeError, "凭据"):
            self.driver.purchase(self.item, 1, inspection)
        self.assertEqual(self.observer.submits, 0)

    def test_quantity_ready_mismatch_never_submits(self):
        self.observer.bad_ready = True
        with self.assertRaises(GroceryRecognitionError):
            self.driver.purchase(self.item, 1, self.driver.inspect(self.item))
        self.assertEqual(self.observer.submits, 0)

    def test_uncertain_result_submits_only_once_and_cannot_retry(self):
        self.observer.bad_result = True
        inspection = self.driver.inspect(self.item)
        with self.assertRaises(GroceryRecognitionError):
            self.driver.purchase(self.item, 1, inspection)
        with self.assertRaises(RuntimeError):
            self.driver.purchase(self.item, 1, inspection)
        self.assertEqual(self.observer.submits, 1)

    def test_insufficient_balance_and_stock_do_not_submit(self):
        for quantity in (11, 51):
            with self.subTest(quantity=quantity), self.assertRaises(RuntimeError):
                self.driver.purchase(self.item, quantity, self.driver.inspect(self.item))
        self.assertEqual(self.observer.submits, 0)

    def test_stop_before_purchase_never_submits(self):
        inspection = self.driver.inspect(self.item)
        self.driver.stop_event.set()
        with self.assertRaises(InterruptedError):
            self.driver.purchase(self.item, 1, inspection)
        self.assertEqual(self.observer.submits, 0)

    def test_plan_engine_and_driver_complete_a_durable_transaction(self):
        from grocery_plan import new_state, run_state
        path = Path(self.folder.name) / "state.json"
        state = new_state([self.item], {self.item["key"]: 3})
        original_submit = self.observer.submit_once

        def submit(item, quantity, before):
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["status"], "uncertain")
            original_submit(item, quantity, before)

        self.observer.submit_once = submit
        run_state(state, path, self.driver)
        self.assertEqual(state["status"], "done", state.get("last_error"))
        self.assertEqual(state["items"][0]["completed"], 3)
        self.assertEqual(state["balances_end"]["sun"], 350)
        self.assertEqual(self.observer.submits, 1)

    def test_plan_engine_keeps_uncertain_driver_result_without_replay(self):
        from grocery_plan import new_state, run_state
        path = Path(self.folder.name) / "state.json"
        state = new_state([self.item], {self.item["key"]: 1})
        self.observer.bad_result = True
        run_state(state, path, self.driver)
        self.assertEqual(state["status"], "needs_review")
        self.assertEqual(state["items"][0]["status"], "uncertain")
        run_state(state, path, self.driver)
        self.assertEqual(self.observer.submits, 1)


if __name__ == "__main__":
    unittest.main()
