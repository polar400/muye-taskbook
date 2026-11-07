"""Grocery presets and a resumable purchase journal, with no game IO.

The injected driver owns recognition/input. This module owns the fixed plan,
funding/stock policy and the durable boundary before every consuming action.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
import uuid

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "grocery_plan.json"
STATE_PATH = ROOT / "grocery_state.json"
SHOPS = ("sun", "moon", "sign", "mystery")
SHOP_NAMES = {"sun": "日商店", "moon": "月商店", "sign": "签到商店", "mystery": "神秘商店"}
CURRENCIES = {"sun": "日之币", "moon": "月之币", "sign": "签到令", "mystery": "奇怪的石头"}
STATE_STATUSES = {"new", "running", "stopped", "done", "needs_review", "failed"}
ITEM_STATUSES = {"pending", "done", "skipped", "uncertain"}


def now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def item_key(shop: str, item: dict) -> str:
    identity = [shop, item.get("name", ""), str(item.get("id") or ""), str(item.get("head") or "")]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return shop + ":" + hashlib.sha256(encoded).hexdigest()[:24]


def load_catalog(root: Path = ROOT) -> list[dict]:
    manifest_path = Path(root) / "resources/local/grocery/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    shops = {shop["key"]: shop for shop in manifest["shops"]}
    result = []
    seen = set()
    for shop in SHOPS:
        for original in shops[shop]["items"]:
            entry = deepcopy(original)
            key = item_key(shop, entry)
            if key in seen:
                raise ValueError(f"杂货屋商品身份重复：{entry['name']}")
            seen.add(key)
            asset = manifest["assets"][entry["asset"]]
            entry.update(key=key, shop=shop, shop_name=SHOP_NAMES[shop], currency=CURRENCIES[shop],
                         image_path=str(manifest_path.parent / asset["path"]))
            result.append(entry)
    return result


def parse_quantity(value) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value.strip())
    raise ValueError("购买数量必须是非负整数，0表示不买")


def _quantities(quantities: dict, catalog: list[dict]) -> dict[str, int]:
    if not isinstance(quantities, dict):
        raise ValueError("杂货屋预设必须包含商品数量")
    keys = {item["key"] for item in catalog}
    unknown = set(quantities) - keys
    if unknown:
        raise ValueError("预设包含当前目录中不存在的商品，请先核对原预设")
    return {item["key"]: parse_quantity(quantities.get(item["key"], 0)) for item in catalog}


def _write_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_plan(path: Path = PLAN_PATH, catalog: list[dict] | None = None) -> dict[str, int]:
    catalog = load_catalog() if catalog is None else catalog
    path = Path(path)
    if not path.exists():
        return _quantities({}, catalog)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("杂货屋预设格式不受支持，请保留原文件并核对")
    return _quantities(data.get("quantities"), catalog)


def save_plan(path: Path, quantities: dict, catalog: list[dict] | None = None) -> dict[str, int]:
    catalog = load_catalog() if catalog is None else catalog
    valid = _quantities(quantities, catalog)
    _write_json(Path(path), {"schema_version": 1, "saved_at": now(), "quantities": valid})
    return valid


def new_state(catalog: list[dict], quantities: dict) -> dict:
    valid = _quantities(quantities, catalog)
    created = now()
    items = []
    for original in catalog:
        quantity = valid[original["key"]]
        if quantity:
            item = deepcopy(original)
            item.update(quantity=quantity, completed=0, status="pending", purchases=[])
            items.append(item)
    return {"schema_version": 1, "run_id": created.replace(":", "-") + "-" + uuid.uuid4().hex[:10],
            "created_at": created, "updated_at": created, "status": "new", "items": items,
            "balances_start": {}, "balances_end": {}, "balances_latest": {},
            "balances_read_at": None, "events": [], "last_error": None}


def _validate_state(state: dict) -> None:
    if (not isinstance(state, dict) or state.get("schema_version") != 1
            or state.get("status") not in STATE_STATUSES or not isinstance(state.get("run_id"), str)
            or not state["run_id"] or not isinstance(state.get("items"), list)
            or not isinstance(state.get("events"), list)):
        raise ValueError("杂货屋执行记录损坏，请保留原文件并核对")
    seen = set()
    for item in state["items"]:
        key = item.get("key")
        quantity, completed = item.get("quantity"), item.get("completed")
        if (not isinstance(key, str) or not key or key in seen or item.get("shop") not in SHOPS
                or item.get("status") not in ITEM_STATUSES or type(quantity) is not int or quantity <= 0
                or type(completed) is not int or not 0 <= completed <= quantity
                or (item["status"] == "done" and completed != quantity)):
            raise ValueError("杂货屋商品执行记录损坏，请勿重新发送购买")
        seen.add(key)
    if state["status"] == "done" and any(item["status"] not in {"done", "skipped"} for item in state["items"]):
        raise ValueError("杂货屋完成状态与商品记录冲突")


def load_state(path: Path = STATE_PATH) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8-sig"))
    _validate_state(state)
    return state


def save_state(path: Path, state: dict) -> None:
    _validate_state(state)
    state["updated_at"] = now()
    _write_json(Path(path), state)


def _balances(value) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(SHOPS):
        raise ValueError("四种货币余额未完整确认")
    if any(type(value[shop]) is not int or value[shop] < 0 for shop in SHOPS):
        raise ValueError("货币余额不是可靠的非负整数")
    return {shop: value[shop] for shop in SHOPS}


def run_state(state: dict, path: Path, driver, emit: Callable[[dict], None] | None = None,
              stop_event=None) -> dict:
    """Execute a fixed journal with an injected recognizer/input driver.

    driver.begin() returns four balances keyed by SHOPS. inspect(item) returns
    verified=True, unit_price, stock and balances. purchase(item, quantity,
    inspection) returns verified=True, quantity, stock and balances. A purchase
    return is accepted only if the engine independently verifies exact currency
    deduction and stock decrease. Driver exceptions after the durable uncertain
    boundary never cause another purchase attempt.
    """
    _validate_state(state)
    path = Path(path)
    emit = (lambda event: None) if emit is None else emit

    def stopped():
        return stop_event is not None and stop_event.is_set()

    def event(kind, message, **fields):
        record = {"kind": kind, "message": message, "at": now(), **fields}
        state["events"].append(record)
        save_state(path, state)
        emit(deepcopy(record))

    def record_balances(balances):
        checked = _balances(balances)
        read_at = now()
        if not state["balances_start"]:
            state["balances_start"] = dict(checked)
        state["balances_latest"] = dict(checked)
        state["balances_end"] = dict(checked)
        state["balances_read_at"] = read_at
        event("balance", "四种货币余额已确认", balances=checked, read_at=read_at)

    try:
        if any(item["status"] == "uncertain" for item in state["items"]):
            state["status"] = "needs_review"
            state["last_error"] = "上一次购买结果不确定，请核对后再继续；未自动重买"
            event("status", state["last_error"], status=state["status"])
            return state
        if state["status"] == "done":
            emit({"kind": "status", "message": "本轮已完成，请使用新一轮重新购买", "status": "done"})
            return state
        if stopped():
            state["status"] = "stopped"
            event("status", "本轮已停止，尚未发送新的购买", status="stopped")
            return state
        state["status"] = "running"
        state["last_error"] = None
        event("status", "杂货屋本轮开始", status="running", run_id=state["run_id"])
        record_balances(driver.begin())
        for item in state["items"]:
            if item["status"] in {"done", "skipped"}:
                continue
            if stopped():
                state["status"] = "stopped"
                event("status", "购买已停止，可继续本轮剩余商品", status="stopped")
                return state
            remaining = item["quantity"] - item["completed"]
            if remaining == 0:
                item["status"] = "done"
                event("progress", f"{item['name']}已完成", item=deepcopy(item), remaining=0)
                continue
            inspection = driver.inspect(deepcopy(item))
            if not isinstance(inspection, dict) or inspection.get("verified") is not True:
                raise ValueError(f"{item['name']}的商品、价格或库存尚未可靠确认")
            unit_price, stock = inspection.get("unit_price"), inspection.get("stock")
            if type(unit_price) is not int or unit_price < 0 or type(stock) is not int or stock < 0:
                raise ValueError(f"{item['name']}价格或库存读数无效")
            balances = _balances(inspection.get("balances"))
            record_balances(balances)
            item["last_inspection"] = {"unit_price": unit_price, "stock": stock, "balances": balances,
                                        "read_at": state["balances_read_at"]}
            cost = unit_price * remaining
            if stock < remaining or balances[item["shop"]] < cost:
                item["status"] = "skipped"
                item["skip_reason"] = "库存不足整项预设数量" if stock < remaining else "货币不足整项预设数量"
                event("progress", f"跳过{item['name']}：{item['skip_reason']}", item=deepcopy(item), remaining=remaining)
                continue
            if stopped():
                state["status"] = "stopped"
                event("status", "购买已停止，尚未发送当前商品购买", status="stopped")
                return state
            # This write must succeed before the driver may send consuming input.
            item["status"] = "uncertain"
            item["purchase_started_at"] = now()
            event("progress", f"正在购买{item['name']} × {remaining}", item=deepcopy(item), remaining=remaining)
            result = driver.purchase(deepcopy(item), remaining, inspection)
            if (not isinstance(result, dict) or result.get("verified") is not True
                    or type(result.get("quantity")) is not int or result["quantity"] != remaining
                    or type(result.get("stock")) is not int or result["stock"] != stock - remaining):
                raise ValueError(f"{item['name']}购买后的数量或库存变化无法确认")
            after = _balances(result.get("balances"))
            expected = dict(balances)
            expected[item["shop"]] -= cost
            if after != expected:
                raise ValueError(f"{item['name']}购买后的货币变化不符，已停止且不重买")
            item["completed"] += remaining
            item["status"] = "done"
            item.setdefault("purchases", []).append({"quantity": remaining, "unit_price": unit_price,
                "stock_before": stock, "stock_after": result["stock"], "balances_before": balances,
                "balances_after": after, "confirmed_at": now()})
            record_balances(after)
            event("progress", f"已购买{item['name']} × {remaining}", item=deepcopy(item), remaining=0)
        state["status"] = "done"
        event("status", "杂货屋本轮完成", status="done")
    except Exception as error:
        state["status"] = "needs_review" if any(item["status"] == "uncertain" for item in state["items"]) else "failed"
        state["last_error"] = str(error)
        # If persistence itself failed, retain the last durable record rather
        # than masking it with another exception or sending further input.
        try:
            event("status", "杂货屋已停止：" + str(error), status=state["status"])
        except Exception:
            try:
                emit({"kind": "status", "message": "执行记录保存失败，已停止购买：" + str(error),
                      "status": state["status"]})
            except Exception:
                pass
    return state
