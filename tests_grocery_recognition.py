"""Offline grocery icon checks. No window handles, capture, or input APIs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from grocery_recognition import ASSET_ROOT, GroceryRecognizer, SHOPS
import numpy as np
from PIL import Image


GAME_FIXTURE = json.loads((Path(__file__).resolve().parent / "verification/grocery-icons-20261026/game-cases.json").read_text(encoding="utf-8"))
GAME_CASES = tuple((tuple(case["box"]), case["asset"]) for case in GAME_FIXTURE["cases"])


class GroceryRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = GroceryRecognizer()
        cls.game = Image.open(ASSET_ROOT / "sources/user-game.png").convert("RGB")

    def open_asset(self, key):
        with Image.open(ASSET_ROOT / self.recognizer.manifest["assets"][key]["path"]) as image:
            return image.copy()

    def test_four_shop_catalogue_has_expected_source_counts(self):
        source = json.loads((ASSET_ROOT / "sources/groceries.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(set(self.recognizer.shops), set(SHOPS))
        self.assertEqual({key: len(self.recognizer.shops[key]["items"]) for key in SHOPS},
                         {"sun": 25, "moon": 38, "sign": 61, "mystery": 17})
        for key in SHOPS:
            with self.subTest(shop=key):
                self.assertEqual([row["name"] for row in self.recognizer.shops[key]["items"]],
                                 [row["name"] for row in source[key]])
                for row in self.recognizer.shops[key]["items"]:
                    self.assertIn(row["asset"], self.recognizer.templates)

    def test_every_web_icon_matches_its_own_visual_identity(self):
        """Ambiguity is valid; an incorrect accepted identity is never valid."""
        for shop in SHOPS:
            keys = {row["asset"] for row in self.recognizer.shops[shop]["items"]}
            for key in sorted(keys):
                with self.subTest(shop=shop, asset=key):
                    result = self.recognizer.recognize(self.open_asset(key), shop=shop)
                    self.assertIn(result["status"], ("recognized", "ambiguous"), result)
                    aliases = result["candidates"][0]["assetAliases"]
                    self.assertIn(key, aliases, result)
                    if result["status"] == "recognized":
                        self.assertIn(result["item"]["asset"], aliases)

    def test_all_twelve_user_game_icons_are_correct(self):
        for box, expected in GAME_CASES:
            with self.subTest(box=box, asset=expected):
                result = self.recognizer.recognize_region(self.game, box, shop="sun")
                self.assertEqual(result["status"], "recognized", result)
                self.assertEqual(result["asset"], expected, result)
                self.assertEqual(result["box"], list(box))

    def test_five_coloured_handbook_packages_do_not_cross_match(self):
        for key in ("item_10190514", "item_10190515", "item_10190516", "item_10190517", "item_10190518"):
            with self.subTest(asset=key):
                result = self.recognizer.recognize(self.open_asset(key), shop="sun")
                self.assertEqual(result["status"], "recognized", result)
                self.assertEqual(result["asset"], key)

    def test_shared_sign_gift_icon_cannot_select_a_product(self):
        result = self.recognizer.recognize(self.open_asset("item_10100000"), shop="sign")
        self.assertEqual(result["status"], "ambiguous", result)
        self.assertEqual(result["reason"], "shared_icon", result)
        self.assertIsNone(result["item"])
        self.assertGreater(len(result["items"]), 1)

    def test_flat_images_and_unrelated_noise_are_not_accepted(self):
        images = [Image.new("RGB", (84, 84), colour) for colour in ("black", "white", "red", "#808080")]
        images.append(Image.fromarray(np.random.default_rng(193).integers(0, 256, (84, 84, 3), dtype=np.uint8)))
        for index, image in enumerate(images):
            with self.subTest(case=index):
                result = self.recognizer.recognize(image, shop="sun")
                self.assertEqual(result["status"], "unknown", result)
                self.assertIsNone(result["item"])

    def test_real_purchase_control_and_shop_navigation_are_not_items(self):
        for box in ((533, 398, 84, 84), (1383, 174, 84, 84), (1690, 610, 84, 84)):
            with self.subTest(box=box):
                result = self.recognizer.recognize_region(self.game, box, shop="sun")
                self.assertEqual(result["status"], "unknown", result)
                self.assertIsNone(result["item"])

    def test_icon_absent_from_selected_shop_is_not_accepted(self):
        # A mystery costume icon must not become a sun-store item.
        sun_keys = {row["asset"] for row in self.recognizer.shops["sun"]["items"]}
        unique = next(row["asset"] for row in self.recognizer.shops["mystery"]["items"] if row["asset"] not in sun_keys)
        result = self.recognizer.recognize(self.open_asset(unique), shop="sun")
        self.assertEqual(result["status"], "unknown", result)
        self.assertIsNone(result["item"])

    def test_explicit_valid_shop_is_required(self):
        image = self.open_asset("item_10800050")
        with self.assertRaises(TypeError):
            self.recognizer.recognize(image)
        for shop in (None, "", "not-a-shop", "日之印商店"):
            with self.subTest(shop=shop), self.assertRaises(ValueError):
                self.recognizer.recognize(image, shop=shop)

    def test_tiny_and_nonsquare_crops_are_rejected(self):
        for size in ((23, 23), (84, 40), (40, 84), (0, 0)):
            with self.subTest(size=size):
                result = self.recognizer.recognize(Image.new("RGB", size), shop="sun")
                self.assertEqual(result["status"], "invalid_crop")
                self.assertIsNone(result["item"])

    def test_malformed_or_outside_region_is_rejected(self):
        boxes = ((-1, 0, 84, 84), (0, -1, 84, 84), (0, 0, 0, 84), (0, 0, 84, -1),
                 (self.game.width - 10, 0, 84, 84), (0, self.game.height - 10, 84, 84),
                 (0, 0, 84), (0, 0, 84, 84.0), (True, 0, 84, 84))
        for box in boxes:
            with self.subTest(box=box), self.assertRaises(ValueError):
                self.recognizer.recognize_region(self.game, box, shop="sun")

    def write_fixture(self, root, images):
        assets = {}
        items = []
        for index, image in enumerate(images):
            key = f"fixture_{index}"
            path = root / f"{key}.png"
            image.save(path)
            assets[key] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            items.append({"name": key, "asset": key})
        manifest = {"assets": assets, "shops": [{"key": "sun", "items": items}]}
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    def fixture_directory(self, prefix):
        workspace = Path(__file__).resolve().parent
        base = (workspace / "verification/grocery-icons-20261026").resolve()
        if not base.is_relative_to(workspace):
            raise ValueError("Test fixture directory escapes workspace")
        return tempfile.TemporaryDirectory(prefix=prefix, dir=base)

    def test_nearly_identical_different_candidates_are_ambiguous(self):
        image = self.open_asset("item_10800050").convert("RGBA").convert("RGB")
        changed = image.copy()
        x, y = changed.width // 2, changed.height // 2
        red, green, blue = changed.getpixel((x, y))
        changed.putpixel((x, y), (red ^ 1, green, blue))
        with self.fixture_directory("grocery-near-") as folder:
            root = Path(folder)
            self.write_fixture(root, [image, changed])
            result = GroceryRecognizer(root).recognize(image, shop="sun")
        self.assertEqual(result["status"], "ambiguous", result)
        self.assertEqual(result["reason"], "similar_icons", result)
        self.assertIsNone(result["item"])

    def test_same_pixels_in_different_files_preserve_product_ambiguity(self):
        image = self.open_asset("item_10800050")
        with self.fixture_directory("grocery-duplicate-") as folder:
            root = Path(folder)
            self.write_fixture(root, [image, image])
            result = GroceryRecognizer(root).recognize(image, shop="sun")
        self.assertEqual(result["status"], "ambiguous", result)
        self.assertEqual(result["reason"], "shared_icon", result)
        self.assertIsNone(result["item"])

    def test_corrupted_asset_checksum_stops_loading(self):
        image = self.open_asset("item_10800050")
        with self.fixture_directory("grocery-corrupt-") as folder:
            root = Path(folder)
            self.write_fixture(root, [image])
            with (root / "fixture_0.png").open("ab") as output:
                output.write(b"unexpected-content")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                GroceryRecognizer(root)

    def test_asset_reference_cannot_escape_grocery_directory(self):
        image = self.open_asset("item_10800050")
        with self.fixture_directory("grocery-path-") as folder:
            root = Path(folder)
            manifest = self.write_fixture(root, [image])
            manifest["assets"]["fixture_0"]["path"] = "../outside.png"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes its directory"):
                GroceryRecognizer(root)


if __name__ == "__main__":
    unittest.main()
