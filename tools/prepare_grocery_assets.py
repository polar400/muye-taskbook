"""Archive four grocery shops. Offline rebuild by default; --download uses HTTPS.

Downloaded PNGs retain their original bytes. A preview is an inspection artifact,
not a recognition template. No game connection, input, or purchasing is included.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
from PIL import Image, ImageDraw, ImageFont

DEST = ROOT / "resources/local/grocery"
SHOPS = ("sun", "moon", "sign", "mystery")
ORIGIN = "https://udonwiki.net"
USER_SOURCES = {
    "user-web": "C:/Users/lenovo/AppData/Local/Temp/codex-clipboard-83ba9dbf-5ea2-4114-a14e-7d713e22f06f.png",
    "user-entry": "C:/Users/lenovo/AppData/Local/Temp/codex-clipboard-c3b31620-492a-4760-a045-f90688c481de.png",
    "user-game": "C:/Users/lenovo/AppData/Local/Temp/codex-clipboard-674d6e56-bb21-4e47-b266-353d43819999.png",
}


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def now():
    # Current Asia/Shanghai is UTC+08:00. Do not require optional tzdata on Windows.
    return datetime.now(timezone(timedelta(hours=8), "Asia/Shanghai")).isoformat(timespec="seconds")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def image_info(blob):
    with Image.open(io.BytesIO(blob)) as image:
        image.load()
        pixels = image.convert("RGBA")
        return dict(size=len(blob), width=image.width, height=image.height,
                    format=image.format, mode=image.mode,
                    pixel_sha256=sha256(pixels.tobytes()))


def asset_identity(item):
    # This order follows general.html grIcon(it), including ninja-head priority.
    head = str(item.get("head") or "").strip()
    identifier = head or str(item.get("id") or "").strip()
    if not identifier:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
        raise ValueError(f"Unsafe asset identifier: {identifier!r}")
    kind = "head" if head else "item"
    key = kind + "_" + identifier
    url = ORIGIN + ("/static/assets/ninjas/head/" if head else "/static/assets/items/") + identifier + ".png"
    return key, url


def fetch_asset(key, url):
    path = DEST / "image" / (key + ".png")
    if path.exists():
        blob = path.read_bytes()
        return key, dict(path=path.relative_to(DEST).as_posix(), url=url,
                         sha256=sha256(blob), **image_info(blob), reused=True), None
    attempts = []
    # Use the environment's HTTPS configuration (including its configured proxy).
    opener = urllib.request.build_opener()
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": ORIGIN + "/general"})
            with opener.open(request, timeout=25) as response:
                blob = response.read()
                status = response.status
            info = image_info(blob)
            if info["format"] != "PNG":
                raise ValueError(f"Expected PNG, received {info['format']!r}")
            path.write_bytes(blob)
            return key, dict(path=path.relative_to(DEST).as_posix(), url=url,
                             sha256=sha256(blob), **info, downloaded_at=now(),
                             http_status=status, download_attempts=attempt), None
        except Exception as error:
            attempts.append(dict(attempt=attempt, error=type(error).__name__, message=str(error)))
            if isinstance(error, urllib.error.HTTPError) and error.code in (400, 403, 404, 410):
                break
            if attempt < 3:
                time.sleep(attempt)
    return key, None, dict(asset=key, url=url, attempts=attempts)


def contact_sheet(assets):
    width, height, columns = 140, 152, 9
    rows = (len(assets) + columns - 1) // columns
    sheet = Image.new("RGB", (width * columns, max(1, rows) * height), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 13) if font_path.exists() else ImageFont.load_default()
    for index, (key, asset) in enumerate(sorted(assets.items())):
        x, y = (index % columns) * width, (index // columns) * height
        with Image.open(DEST / asset["path"]) as image:
            image = image.convert("RGBA")
            image.thumbnail((110, 110))
            sheet.paste(image, (x + (width - image.width) // 2, y + 5), image)
        draw.text((x + 4, y + 118), key, fill="black", font=font)
        draw.text((x + 4, y + 135), f"{asset['width']} x {asset['height']}", fill="black", font=font)
    sheet.save(DEST / "contact-sheet.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download missing public PNGs; never contacts the game")
    args = parser.parse_args()
    (DEST / "sources").mkdir(parents=True, exist_ok=True)
    (DEST / "image").mkdir(exist_ok=True)
    previous_path = DEST / "manifest.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    source_records = []
    for name, url in (("general.html", ORIGIN + "/general"), ("groceries.json", ORIGIN + "/static/data/groceries.json")):
        path = DEST / "sources" / name
        blob = path.read_bytes()
        source_records.append(dict(path=path.relative_to(DEST).as_posix(), url=url,
                                   sha256=sha256(blob), size=len(blob), role="public-website-source"))
    for name, original in USER_SOURCES.items():
        path = DEST / "sources" / (name + ".png")
        original_path = Path(original)
        if not path.exists() and original_path.is_file():
            shutil.copyfile(original_path, path)
        if path.exists():
            blob = path.read_bytes()
            source_records.append(dict(path=path.relative_to(DEST).as_posix(), original_path=original,
                                       sha256=sha256(blob), **image_info(blob), role="user-attachment"))
        else:
            source_records.append(dict(path=path.relative_to(DEST).as_posix(), original_path=original,
                                       error="User attachment unavailable"))
    data = json.loads((DEST / "sources/groceries.json").read_text(encoding="utf-8"))
    tabs = {item["key"]: item["name"] for item in data["_tabs"]}
    shops, wanted, missing_icons = [], {}, []
    for key in SHOPS:
        items = []
        for index, raw in enumerate(data[key]):
            item = {name: raw.get(name) for name in ("name", "id", "head", "price", "stock")}
            identity = asset_identity(raw)
            item["asset"] = identity[0] if identity else None
            if identity:
                wanted[identity[0]] = identity[1]
            else:
                missing_icons.append(dict(shop=key, index=index, name=item["name"], id=item["id"], head=item["head"]))
            items.append(item)
        shops.append(dict(key=key, name=tabs[key], currency=data.get("_cur", {}).get(key), items=items))
    assets, download_failures = {}, []
    if args.download:
        with ThreadPoolExecutor(max_workers=6) as executor:
            jobs = [executor.submit(fetch_asset, key, url) for key, url in sorted(wanted.items())]
            for future in as_completed(jobs):
                key, asset, failure = future.result()
                if failure:
                    download_failures.append(failure)
                    print("FAILED", key, flush=True)
                else:
                    # Preserve original download provenance during a later rebuild.
                    asset = {**previous.get("assets", {}).get(key, {}), **asset}
                    assets[key] = asset
                    print("OK", key, asset["width"], asset["height"], flush=True)
    else:
        for key, url in sorted(wanted.items()):
            path = DEST / "image" / (key + ".png")
            if not path.exists():
                download_failures.append(dict(asset=key, url=url, error="File missing; rerun with --download"))
                continue
            blob = path.read_bytes()
            assets[key] = {**previous.get("assets", {}).get(key, {}),
                           **dict(path=path.relative_to(DEST).as_posix(), url=url, sha256=sha256(blob), **image_info(blob))}
    aliases = []
    for shop in shops:
        by_asset = {}
        for item in shop["items"]:
            if item["asset"]:
                by_asset.setdefault(item["asset"], []).append(item)
        for key, items in by_asset.items():
            if len(items) > 1:
                aliases.append(dict(shop=shop["key"], asset=key, items=items))
    manifest = dict(schema_version=1, collected_at=previous.get("collected_at", now()), rebuilt_at=now(),
                    timezone="Asia/Shanghai", page_url=ORIGIN + "/general",
                    purpose="Four-shop icon archive and offline ROI recognition; no game IO or purchasing",
                    asset_rule="grIcon(it): nonempty head first, otherwise item id; original PNG bytes retained",
                    pixel_sha256_encoding="PIL convert RGBA, row-major raw pixel bytes",
                    sources=source_records, shops=shops, assets=dict(sorted(assets.items())),
                    missing_icons=missing_icons, download_failures=sorted(download_failures, key=lambda item: item["asset"]),
                    same_shop_asset_aliases=aliases,
                    summary=dict(shops=len(shops), shop_items=sum(len(shop["items"]) for shop in shops),
                                 unique_asset_paths=len(wanted), saved_assets=len(assets),
                                 missing_icons=len(missing_icons), download_failures=len(download_failures),
                                 same_shop_asset_alias_groups=len(aliases)),
                    limitations=["Website metadata is a reference snapshot, not live game price or stock.",
                                 "Same asset can represent multiple products; icon-only selection must reject ambiguity.",
                                 "Only the user's sun-shop screenshot is a real-game product sample."])
    write_json(previous_path, manifest)
    contact_sheet(assets)
    print(json.dumps(manifest["summary"], ensure_ascii=False), flush=True)
    return 1 if download_failures or missing_icons or any("error" in source for source in source_records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
