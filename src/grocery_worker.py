"""Isolated grocery worker. Only an explicit request file can start game work."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import traceback

from grocery_plan import load_state, run_state, save_state, _write_json, now


def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def init_dpi():
    # Separate worker only: mirror the existing backend's physical pixel space.
    # Importing this module must not alter Tkinter's process DPI context.
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)


def main(request_path):
    init_dpi()
    request = json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    if request.get('schema_version') != 1 or type(request.get('hwnd')) is not int:
        raise ValueError('杂货屋启动请求无效')
    mode = request.get('mode', 'purchase')
    if mode not in ('purchase', 'observe'):
        raise ValueError('杂货屋运行模式无效')
    if mode == 'purchase':
        from grocery_driver import capability_summary
        capability = capability_summary()
        if capability.get('live_purchase_supported') is not True:
            raise ValueError(capability['reason'])
        state_path = Path(request['state_path'])
        state = load_state(state_path)
        if state is None or state['run_id'] != request.get('run_id'):
            raise ValueError('杂货屋计划与启动请求不一致')
        if capability.get('supported_item_ids') is not None:
            from grocery_live import validate_items
            validate_items(state['items'])
    # Python 3.14: importing NumPy's extension while another thread blocks on
    # stdin can deadlock. Load the native recognition modules before that reader.
    emit({'kind': 'status', 'message': '正在加载杂货屋识别模块'})
    from grocery_driver import GroceryDriver
    if mode == 'purchase':
        import grocery_live  # Native imports must precede blocking stdin reader.
    stop = threading.Event()
    def commands():
        for line in sys.stdin:
            if line.strip() == 'stop':
                stop.set()
        stop.set()
    threading.Thread(target=commands, daemon=True).start()
    folder = Path(request['evidence_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    emit({'kind': 'status', 'message': '正在连接游戏并校准杂货屋截图'})
    driver = GroceryDriver(request['hwnd'], evidence_dir=folder, stop_event=stop, emit=emit, purchase_enabled=(mode == 'purchase'))
    if mode == 'observe':
        balances = driver.begin()
        if stop.is_set():
            emit({'kind': 'status', 'message': '余额读取已停止，未覆盖历史记录'})
            return 1
        record = {'balances': balances, 'read_at': now(), 'evidence_dir': str(folder)}
        _write_json(Path(request['balance_path']), record)
        _write_json(folder/'balances.json', record)
        emit({'kind': 'balance', 'message': '四种货币余额已确认', **record})
        return 0
    try:
        state = run_state(state, state_path, driver, emit=emit, stop_event=stop)
        if state.get('balances_latest'):
            _write_json(state_path.with_name('grocery_balances.json'),
                        {'balances': state['balances_latest'], 'read_at': state['balances_read_at'],
                         'evidence_dir': str(folder)})
    finally:
        save_state(folder / 'state-final.json', load_state(state_path) or state)
    return 0 if state['status'] in ('done', 'stopped') else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    try:
        if len(sys.argv) != 2:
            raise ValueError('请通过杂货屋工具启动，不要直接运行工作进程')
        raise SystemExit(main(sys.argv[1]))
    except Exception as error:
        emit({'kind': 'error', 'message': str(error)})
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
