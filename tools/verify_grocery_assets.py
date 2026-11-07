"""Verify the grocery archive and icon classifier offline; never operate the game."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from grocery_recognition import ASSET_ROOT, GroceryRecognizer, SHOPS
from PIL import Image, ImageDraw, ImageFont

OUTPUT = ROOT / "verification/grocery-icons-20261026"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8-sig"))
    source = json.loads((ASSET_ROOT / "sources/groceries.json").read_text(encoding="utf-8-sig"))
    report = {"verified_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
              "scope": "grocery archive and explicitly cropped icon recognition; no game input",
              "page_url": manifest["page_url"], "errors": [], "assets": [], "sources": [], "sharedFiles": []}

    def check(condition, message):
        if not condition:
            report["errors"].append(message)

    check(not manifest["download_failures"] and not manifest["missing_icons"], "Archive contains missing images")
    shops = {shop["key"]: shop for shop in manifest["shops"]}
    check(set(shops) == set(SHOPS), "Four-shop set differs")
    urls = set()
    referenced = set()
    for key in SHOPS:
        entries = shops[key]["items"]
        check(len(entries) == len(source[key]), f"{key}: item count differs")
        for actual, original in zip(entries, source[key]):
            for field in ("name", "id", "head", "price", "stock"):
                check(actual.get(field) == original.get(field), f"{key}: metadata differs: {field}")
            head = original.get("head")
            expected_key = ("head_" + str(head)) if head else ("item_" + str(original.get("id")))
            check(actual["asset"] == expected_key, f"{key}: asset rule differs")
            check(expected_key in manifest["assets"], f"Missing asset: {expected_key}")
            referenced.add(expected_key)
    check(referenced == set(manifest["assets"]), "Unreferenced or missing asset records")
    for key, asset in manifest["assets"].items():
        path = ASSET_ROOT / asset["path"]
        with Image.open(path) as image:
            image.load()
            pixel_hash = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
            good = (image.format == "PNG" and [image.width, image.height] == [asset["width"], asset["height"]]
                    and digest(path) == asset["sha256"] and pixel_hash == asset["pixel_sha256"]
                    and path.stat().st_size == asset["size"])
        expected_url = "https://udonwiki.net/static/assets/" + (
            "ninjas/head/" + key.removeprefix("head_") if key.startswith("head_") else "items/" + key.removeprefix("item_")
        ) + ".png"
        check(asset["url"] == expected_url, f"Resource URL differs: {key}")
        check(asset["url"] not in urls, f"Duplicate resource URL: {key}")
        urls.add(asset["url"])
        check(good, f"Asset integrity failed: {key}")
        report["assets"].append({"key": key, "sha256": digest(path), "passed": good})
    for item in manifest["sources"]:
        path = ASSET_ROOT / item["path"]
        good = path.exists() and digest(path) == item.get("sha256")
        original = item.get("original_path")
        if original and Path(original).exists():
            good = good and digest(Path(original)) == digest(path)
        check(good, f"Source integrity failed: {item['path']}")
        report["sources"].append({"path": item["path"], "passed": good})
    baseline = json.loads((OUTPUT / "shared-baseline.json").read_text(encoding="utf-8-sig"))
    for item in baseline:
        path = ROOT / item["path"]
        current = digest(path)
        same = current == item["sha256"]
        report["sharedFiles"].append({**item, "currentSha256": current, "unchanged": same})
        check(same, f"Shared file changed since baseline: {item['path']}")

    recognizer = GroceryRecognizer()
    web_checks = []
    for key in SHOPS:
        for asset_key in sorted({item["asset"] for item in shops[key]["items"]}):
            with Image.open(ASSET_ROOT / manifest["assets"][asset_key]["path"]) as image:
                result = recognizer.recognize(image, shop=key)
            valid = result["status"] in ("recognized", "ambiguous") and asset_key in result["candidates"][0]["assetAliases"]
            check(valid, f"Web self-check failed: {key}/{asset_key}")
            web_checks.append({"shop": key, "expected": asset_key, "result": result})
    report["webSelfChecks"] = web_checks

    fixture = json.loads((OUTPUT / "game-cases.json").read_text(encoding="utf-8"))
    game_path = ASSET_ROOT / fixture["source"]
    check(digest(game_path) == fixture["source_sha256"], "Game fixture source checksum differs")
    with Image.open(game_path) as image:
        game = image.convert("RGB")
    overlay = game.copy()
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
    game_checks = []
    for case in fixture["cases"]:
        result = recognizer.recognize_region(game, tuple(case["box"]), shop="sun")
        passed = result["status"] == "recognized" and result["asset"] == case["asset"]
        check(passed, f"Real-game icon failed: {case['asset']}")
        game_checks.append({**case, "passed": passed, "result": result})
        x, y, w, h = case["box"]
        colour = "#00ff66" if passed else "#ff2244"
        draw.rectangle((x, y, x+w, y+h), outline=colour, width=3)
        draw.text((x, y-26), f"{case['name']} {result.get('score', 0):.3f}", fill=colour, font=font,
                  stroke_width=2, stroke_fill="black")
    overlay.save(OUTPUT / "game-recognition.png")
    report["gameChecks"] = game_checks

    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("tests_grocery_recognition")
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (OUTPUT / "tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    report["tests"] = {"run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
                       "skipped": len(tests.skipped), "successful": tests.wasSuccessful()}
    report["summary"] = {"shopItems": {key: len(shops[key]["items"]) for key in SHOPS},
                         "savedAssets": len(report["assets"]), "webSelfChecks": len(web_checks),
                         "webRecognized": sum(row["result"]["status"] == "recognized" for row in web_checks),
                         "webAmbiguous": sum(row["result"]["status"] == "ambiguous" for row in web_checks),
                         "realGameIcons": len(game_checks), "realGameCorrect": sum(row["passed"] for row in game_checks),
                         "sharedFilesUnchanged": all(row["unchanged"] for row in report["sharedFiles"])}
    report["limitations"] = ["Real-game evidence covers one user sun-shop screenshot and manually supplied icon boxes.",
                             "Other shops only have web self-checks; these are not independent real-game validation.",
                             "36 sign-shop products share one icon and must remain ambiguous.",
                             "No automatic screen localization, text OCR, current price/stock reading or purchasing is implemented."]
    report["passed"] = not report["errors"] and tests.wasSuccessful()
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "tests": report["tests"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
