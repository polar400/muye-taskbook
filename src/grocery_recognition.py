"""Read-only classification of an explicitly cropped grocery item icon.

This module never captures a window, locates a shop, or sends input. Callers must
provide the shop and a tight, square icon crop including its existing frame.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
import numpy as np
from PIL import Image

ASSET_ROOT = ROOT / "resources/local/grocery"
SHOPS = ("sun", "moon", "sign", "mystery")


def _pixels(image: Image.Image) -> np.ndarray:
    """Keep colour; omit the frame and the in-game bottom-right quantity badge."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (8, 16, 20, 255))
    background.alpha_composite(rgba)
    w, h = image.size
    inset_x, inset_y = round(w * .06), round(h * .06)
    small = background.convert("RGB").crop(
        (inset_x, inset_y, w - inset_x, h - inset_y)
    ).resize((48, 48), Image.Resampling.LANCZOS)
    pixels = np.asarray(small, dtype=np.float32) / 255
    mask = np.ones((48, 48), dtype=bool)
    mask[37:, 37:] = False
    return pixels[mask].reshape(-1)


def _similarity(query: np.ndarray, template: np.ndarray) -> tuple[float, float]:
    a, b = query - query.mean(), template - template.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    shape = float(np.dot(a, b) / denominator) if denominator else 0.0
    # Identical package silhouettes can have different coloured contents. Give
    # chroma its own comparison so shared black backgrounds do not dominate.
    qa, ta = query.reshape(-1, 3), template.reshape(-1, 3)
    qa = (qa - qa.mean(axis=1, keepdims=True)).reshape(-1)
    ta = (ta - ta.mean(axis=1, keepdims=True)).reshape(-1)
    qnorm, tnorm = float(np.linalg.norm(qa)), float(np.linalg.norm(ta))
    if qnorm < 1e-6 and tnorm < 1e-6:
        chroma = 1.0
    elif qnorm < 1e-6 or tnorm < 1e-6:
        chroma = 0.0
    else:
        chroma = float(np.dot(qa, ta) / (qnorm * tnorm))
    score = max(-1.0, min(1.0, .65 * shape + .35 * chroma))
    return score, float(np.abs(query - template).mean())


class GroceryRecognizer:
    """Classify against isolated webpage assets, rejecting unknowns and aliases.

    Scores are visual similarities, not probabilities. A result is evidence for
    an icon identity only; prices, stock, shop state and purchase controls still
    require independent recognition before any future purchase implementation.
    """

    def __init__(self, asset_root: Path = ASSET_ROOT):
        self.root = Path(asset_root).resolve()
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8-sig"))
        self.templates: dict[str, np.ndarray] = {}
        self.visual_keys: dict[str, str] = {}
        for key, asset in self.manifest["assets"].items():
            path = (self.root / asset["path"]).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError("Grocery asset path escapes its directory")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != asset["sha256"]:
                raise ValueError(f"Grocery asset checksum mismatch: {key}")
            with Image.open(path) as image:
                self.templates[key] = _pixels(image)
                self.visual_keys[key] = hashlib.sha256(
                    image.convert("RGBA").tobytes() + str(image.size).encode("ascii")
                ).hexdigest()
        self.shops = {shop["key"]: shop for shop in self.manifest["shops"]}

    def recognize(self, image: Image.Image, *, shop: str) -> dict:
        if shop not in SHOPS or shop not in self.shops:
            raise ValueError("An explicit grocery shop key is required")
        w, h = image.size
        if min(w, h) < 24 or not .9 <= w / h <= 1.1:
            return {"status": "invalid_crop", "shop": shop, "item": None}
        query = _pixels(image)
        if float(query.std()) < .035:
            return {"status": "unknown", "shop": shop, "item": None, "reason": "flat_icon"}
        items = self.shops[shop]["items"]
        visual_groups: dict[str, list[str]] = {}
        for item in items:
            key = item.get("asset")
            if key in self.templates:
                group = visual_groups.setdefault(self.visual_keys[key], [])
                if key not in group:
                    group.append(key)
        ranked = []
        for keys in visual_groups.values():
            score, error = _similarity(query, self.templates[keys[0]])
            ranked.append({"asset": keys[0], "assetAliases": keys, "score": score, "meanAbsoluteError": error})
        ranked.sort(key=lambda row: row["score"], reverse=True)
        if not ranked:
            return {"status": "unknown", "shop": shop, "item": None, "reason": "no_templates"}
        best = ranked[0]
        margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else 1.0
        result = {"status": "unknown", "shop": shop, "item": None,
                  "score": best["score"], "margin": margin, "candidates": ranked[:3]}
        if best["score"] < .92 or best["meanAbsoluteError"] > .12:
            result["reason"] = "low_similarity"
            return result
        if margin < .035:
            result.update(status="ambiguous", reason="similar_icons")
            return result
        aliases = [item for item in items if item.get("asset") in best["assetAliases"]]
        if len(aliases) != 1:
            result.update(status="ambiguous", reason="shared_icon", items=aliases)
            return result
        result.update(status="recognized", item=aliases[0], asset=best["asset"])
        return result

    def recognize_region(self, image: Image.Image, box: tuple[int, int, int, int], *, shop: str) -> dict:
        """Use explicit image pixel coordinates (x, y, width, height)."""
        if len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("Icon box must contain four integers")
        x, y, w, h = box
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > image.width or y + h > image.height:
            raise ValueError("Icon box is outside the supplied image")
        result = self.recognize(image.crop((x, y, x + w, y + h)), shop=shop)
        return dict(result, box=list(box))
