"""Grocery-only read-only recognition on a calibrated 1920 x 1015 image.

The initial live evidence covers the sun store's first visible twelve cards.
Other page layouts and transaction dialogs are deliberately not inferred from
web metadata. Numeric OCR accepts complete, agreeing reads, never substitutions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from grocery_recognition import ASSET_ROOT, GroceryRecognizer
import numpy as np
from PIL import Image, ImageOps

BALANCE_BOXES = {
    "sun": (375, 55, 68, 32), "moon": (595, 55, 77, 32),
    "sign": (819, 55, 65, 32), "mystery": (1036, 55, 56, 32),
}
CANONICAL_SIZE = (1920, 1015)


class GroceryRecognitionError(RuntimeError):
    pass


class GroceryTextInsufficient(GroceryRecognitionError):
    pass


def to_rgb(image):
    """Pillow input is RGB; NumPy input follows BackgroundWindow's BGR API."""
    if isinstance(image, Image.Image):
        result = image.convert("RGB")
    elif isinstance(image, np.ndarray) and image.ndim == 3 and image.shape[2] == 3:
        result = Image.fromarray(image[:, :, ::-1].copy()).convert("RGB")
    else:
        raise GroceryRecognitionError("杂货屋截图类型无效")
    if result.size != CANONICAL_SIZE:
        raise GroceryRecognitionError("杂货屋识别要求1920×1015游戏区域")
    return result


def crop(image, box):
    x, y, w, h = box
    return image.crop((x, y, x + w, y + h))


def patch_similarity(image, template):
    image = image.convert("RGB").resize(template.size, Image.Resampling.LANCZOS)
    a, b = np.asarray(image, dtype=np.float32) / 255, np.asarray(template, dtype=np.float32) / 255
    aa, bb = a.reshape(-1) - a.mean(), b.reshape(-1) - b.mean()
    denominator = float(np.linalg.norm(aa) * np.linalg.norm(bb))
    score = float(np.dot(aa, bb) / denominator) if denominator else 0.
    return score, float(np.abs(a - b).mean())


def patch_near(image, box, template, radius=2):
    """Keep strict appearance thresholds while allowing subpixel-layout rounding."""
    x,y,w,h=box
    best=None
    for dy in range(-radius,radius+1):
        for dx in range(-radius,radius+1):
            score,error=patch_similarity(crop(image,(x+dx,y+dy,w,h)),template)
            row=(score,-error,dx,dy)
            if best is None or row>best: best=row
    return best[0],-best[1],(best[2],best[3])


class GroceryVision:
    def __init__(self, ocr=None, asset_root=ASSET_ROOT, recognizer=None):
        self.root = Path(asset_root)
        self.recognizer = recognizer or GroceryRecognizer(self.root)
        self.ocr = ocr
        metadata = json.loads((self.root / "runtime-sources.json").read_text(encoding="utf-8"))
        self.references = {}
        for entry in metadata["assets"]:
            path = self.root / entry["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise GroceryRecognitionError("杂货屋页面参考图校验失败")
            with Image.open(path) as image:
                self.references[entry["key"]] = (entry, image.convert("RGB"))
        self.last_evidence = {}

    def _ocr(self):
        if self.ocr is None:
            from adapters.local_ocr import LocalOCR
            self.ocr = LocalOCR()
        return self.ocr

    def _matches_reference(self, image, key, box=None):
        entry, template = self.references[key]
        score, error, offset = patch_near(image, box or entry["box"], template)
        return score >= .94 and error <= .065, {"key": key, "score": score, "error": error, "offset": list(offset)}

    def require_page(self, image):
        image = to_rgb(image)
        evidence = []
        for key in ("page_close", "currency_sun", "currency_moon", "currency_sign", "currency_mystery"):
            matched, detail = self._matches_reference(image, key)
            evidence.append(detail)
            if not matched:
                raise GroceryRecognitionError("未确认杂货屋页面，停止读取／购买")
        self.last_evidence["page"] = evidence
        return image

    def selected_shop(self, image):
        image = self.require_page(image)
        matched, detail = self._matches_reference(image, "tab_sun_selected")
        self.last_evidence["shop"] = detail
        if matched:
            return "sun"
        raise GroceryRecognitionError("当前店铺尚无经过验证的激活状态样本")

    def read_text(self, image, box, pattern, *, only_rec=True, minimum=.85, white_foreground=False,
                  foreground_threshold=220):
        image = to_rgb(image)
        patch = crop(image, box)
        if white_foreground:
            # Remove the textured currency bar, preserving the white digit ink.
            patch = ImageOps.expand(patch.convert('L').point(lambda value: 255 if value >= foreground_threshold else 0),
                                    border=4, fill=0).convert('RGB')
        reads = []
        for scale in (2, 3):
            enlarged = patch.resize((patch.width * scale, patch.height * scale), Image.Resampling.LANCZOS)
            array = np.asarray(enlarged)[:, :, ::-1].copy()
            results = self._ocr().read(array, only_rec=only_rec)
            candidates = [row for row in results if row.get("score", 0) >= minimum
                          and re.fullmatch(pattern, row.get("text", "").strip())]
            if len(candidates) != 1:
                raise GroceryTextInsufficient("杂货屋局部文字未获得唯一完整高分读数")
            reads.append({"text": candidates[0]["text"].strip(), "score": candidates[0]["score"], "scale": scale})
        if reads[0]["text"] != reads[1]["text"]:
            raise GroceryRecognitionError("杂货屋局部双视图读数冲突")
        return reads[0]["text"], reads

    def read_balances(self, image):
        image = self.require_page(image)
        balances, evidence = {}, {}
        offsets = [row['offset'] for row in self.last_evidence['page']]
        dx,dy = (int(np.median([row[k] for row in offsets])) for k in (0,1))
        for shop, box in BALANCE_BOXES.items():
            foreground = shop in ('moon', 'sign')
            if foreground:
                box = (597, 60, 73, 22) if shop == 'moon' else (825, 60, 65, 22)
            x,y,w,h=box
            box=(x+dx,y+dy,w,h) if foreground else box
            thresholds=195 if shop=='moon' else 220
            try:
                text, reads = self.read_text(image, box, r"(?:0|[1-9][0-9]{0,8})",
                                             white_foreground=foreground, minimum=.9 if shop == 'sign' else .85,
                                             foreground_threshold=thresholds)
            except GroceryTextInsufficient:
                if shop != 'sign': raise
                # Low-contrast sign digits may disappear at 220. Accept two
                # independently thresholded views only when all four reads agree.
                a,ar=self.read_text(image,box,r"(?:0|[1-9][0-9]{0,8})",white_foreground=True,foreground_threshold=100,minimum=.9)
                b,br=self.read_text(image,box,r"(?:0|[1-9][0-9]{0,8})",white_foreground=True,foreground_threshold=140,minimum=.9)
                if a != b: raise GroceryRecognitionError('签到令不同前景阈值读数冲突')
                text,reads,thresholds=a,ar+br,[100,140]
            balances[shop] = int(text)
            evidence[shop] = {"box": list(box), "reads": reads, "white_foreground": foreground}
            if foreground: evidence[shop]['threshold']=thresholds
        self.last_evidence["balances"] = evidence
        return balances

    def inspect_visible_item(self, image, item):
        """Locate a known visible icon; read its live price, stock and quantity.

        Existing name references are genuine game crops, not rendered labels.
        Unavailable name evidence (including sign-shop alias products) is refused.
        """
        image = self.require_page(image)
        shop = self.selected_shop(image)
        if item["shop"] != shop:
            raise GroceryRecognitionError("需要切换店铺；当前切换后页面尚未获得验证")
        hits = []
        for row in range(3):
            for column in range(4):
                x, y = 367 + column * 300, 169 + row * 264
                result = self.recognizer.recognize_region(image, (x, y, 88, 88), shop=shop)
                if result["status"] == "recognized" and result["asset"] == item["asset"]:
                    hits.append((x, y, result))
        if len(hits) != 1:
            raise GroceryRecognitionError("当前可见商品不能唯一匹配；尚不猜测滚动或搜索结果")
        x, y, icon = hits[0]
        if icon["item"]["name"] != item["name"]:
            raise GroceryRecognitionError("预设商品名称与图标目录身份不一致")
        name_key = "name_" + str(item.get("id") or "")
        if name_key not in self.references:
            raise GroceryRecognitionError("此商品缺少经过验证的游戏名称证据")
        original, _ = self.references[name_key]
        width = original["box"][2]
        name_box = (round(x + 101 - width / 2), y + 186, width, 30)
        name_ok, name_detail = self._matches_reference(image, name_key, name_box)
        if not name_ok:
            raise GroceryRecognitionError("商品名称与图标证据不一致")
        try:
            price_text, price_reads = self.read_text(image, (x+145, y+15, 63, 32), r"[1-9][0-9]{0,7}")
        except GroceryRecognitionError as error:
            if "冲突" in str(error):
                raise
            # Detection can ignore the plank decoration that some narrow values
            # (notably 25) turn into a trailing underscore in only-rec mode.
            price_text, price_reads = self.read_text(image, (x+138, y+9, 72, 41), r"[1-9][0-9]{0,7}", only_rec=False)
        stock_text, stock_reads = self.read_text(image, (x+95, y+51, 112, 32), r"库存(?:0|[1-9][0-9]{0,7})")
        quantity_text, quantity_reads = self.read_text(image, (x+10, y+109, 30, 37), r"[1-9][0-9]{0,3}")
        balances = self.read_balances(image)
        return {"verified": True, "key": item.get("key"), "shop": shop, "name": item["name"],
                "asset": item["asset"], "unit_price": int(price_text), "stock": int(stock_text[2:]),
                "quantity": int(quantity_text), "balances": balances, "icon_box": [x, y, 88, 88],
                "buy_box": [x+97, y+107, 132, 51], "quantity_box": [x+10, y+109, 30, 37],
                "evidence": {"icon": icon, "name": name_detail, "price": price_reads,
                             "stock": stock_reads, "quantity": quantity_reads}}
