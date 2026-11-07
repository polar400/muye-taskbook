"""Grocery-only live observation and a strictly verified transaction protocol.

The production observer supports the two evidence-backed moon-store items.
Read-only mode never creates an input-capable observer. Injected observers can
exercise the protocol offline.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

from grocery_vision import GroceryRecognitionError, GroceryVision, to_rgb


def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def capability_summary():
    from grocery_live import NOTICE, SUPPORTED
    return {"supported_read": True, "live_purchase_supported": True,
            "reason": NOTICE, "supported_item_ids": list(SUPPORTED)}


def item_identity(item):
    # The engine durably changes status/completed/inspection fields between
    # inspect and purchase. Bind only the fixed product and planned quantity.
    return tuple(item.get(key) for key in ("key", "shop", "name", "asset", "id", "head", "quantity"))


class GroceryDriver:
    def __init__(self, hwnd, *, evidence_dir, stop_event=None, emit=lambda event: None,
                 window=None, vision=None, observer=None, purchase_enabled=False):
        self.hwnd = hwnd
        self.folder = Path(evidence_dir)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.stop_event = stop_event or threading.Event()
        self.emit = emit
        self.window = window
        self.vision = vision if vision is not None else (None if observer else GroceryVision())
        self.observer = observer
        self.purchase_enabled = purchase_enabled
        self._tokens = {}
        self._started = False
        self._sequence = 0
        self.supports_verified_purchase = bool(observer and getattr(observer, "supports_verified_purchase", False))

    def _check(self):
        if self.stop_event.is_set():
            raise InterruptedError("杂货屋已停止")

    def _save_image(self, image, label):
        self._sequence += 1
        path = self.folder / f"{self._sequence:04d}-{label}.png"
        image.save(path)
        return path.name

    def _capture(self):
        self._check()
        return to_rgb(self.window.capture())

    def _stable_balances(self):
        first = self._capture()
        a = self.vision.read_balances(first)
        if self.stop_event.wait(.15):
            self._check()
        second = self._capture()
        b = self.vision.read_balances(second)
        if a != b:
            raise GroceryRecognitionError("两帧货币读数不稳定，停止购买")
        self._save_image(second, "balances")
        self.emit({"kind": "balance", "balances": b, "read_at": timestamp()})
        return b

    def begin(self):
        self._check()
        if self.observer:
            balances = self.observer.begin()
            self._started = True
            return balances
        if self.window is None:
            from adapters.background_window import BackgroundWindow
            self.window = BackgroundWindow(self.hwnd)
        self.window.calibrate(checkpoint=self._check, log=lambda text: self.emit({"kind": "log", "message": text}))
        if self.purchase_enabled:
            from grocery_live import GroceryLiveObserver
            self.observer = GroceryLiveObserver(self.window, self.vision, self.folder, self.stop_event, self.emit)
            self.supports_verified_purchase = True
            balances = self.observer.begin()
        else:
            balances = self._stable_balances()
        self._started = True
        return balances

    def inspect(self, item):
        self._check()
        if not self._started:
            raise RuntimeError("请先读取杂货屋初始状态")
        if self.observer:
            data = dict(self.observer.inspect(item))
        else:
            first = self._capture()
            a = self.vision.inspect_visible_item(first, item)
            if self.stop_event.wait(.15):
                self._check()
            second = self._capture()
            data = self.vision.inspect_visible_item(second, item)
            signature = lambda row: (row.get("key"), row["shop"], row["asset"], row["unit_price"], row["stock"], row["quantity"], row["balances"])
            if signature(a) != signature(data):
                raise GroceryRecognitionError("两帧商品或货币状态发生变化")
            data["frame"] = self._save_image(second, "inspect")
        if data.get("verified") is not True:
            raise GroceryRecognitionError("商品观察结果未验证")
        token = hashlib.sha256(f"{time.monotonic_ns()}:{item.get('key')}".encode()).hexdigest()
        data["token"] = token
        self._tokens[token] = {"identity": item_identity(item), "inspection": deepcopy(data), "used": False}
        return data

    def purchase(self, item, quantity, inspection):
        self._check()
        if not self.supports_verified_purchase:
            raise RuntimeError(capability_summary()["reason"])
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("购买份数必须为正整数")
        token = inspection.get("token")
        record = self._tokens.get(token)
        if record is None or record["used"] or record["identity"] != item_identity(item) or record["inspection"] != inspection:
            raise RuntimeError("购买前观察凭据无效或已使用")
        shop = item["shop"]
        if inspection["stock"] < quantity or inspection["balances"][shop] < inspection["unit_price"] * quantity:
            raise RuntimeError("购买前余额或库存不足")
        # Consume the one-use token before invoking any input-capable operation.
        record["used"] = True
        self.observer.prepare_quantity(item, quantity, inspection)
        self._check()
        before = self.observer.confirm_ready(item, quantity, inspection)
        required = (before.get("verified") is True and before.get("quantity") == quantity
                    and before.get("unit_price") == inspection["unit_price"]
                    and before.get("stock") == inspection["stock"]
                    and before.get("balances") == inspection["balances"]
                    and before.get("asset") == item["asset"] and before.get("name") == item["name"])
        if not required:
            raise GroceryRecognitionError("购买发送前商品、数量、价格、库存或货币复核失败")
        self._check()
        self.observer.submit_once(item, quantity, before)
        # Even if stop arrives after submit, collect the bounded read-only result
        # so confirmed consumption is not accidentally offered for replay.
        after = self.observer.verify_result(item, quantity, before)
        expected = dict(before["balances"])
        expected[shop] -= quantity * before["unit_price"]
        if not (after.get("verified") is True and after.get("quantity") == quantity
                and after.get("balances") == expected and after.get("stock") == before["stock"] - quantity):
            raise GroceryRecognitionError("购买结果不确定；停止且禁止自动再次购买")
        self.emit({"kind": "balance", "balances": after["balances"], "read_at": timestamp()})
        return dict(after)

    def close(self):
        if self.observer and hasattr(self.observer, "close"):
            self.observer.close()
        self._tokens.clear()
