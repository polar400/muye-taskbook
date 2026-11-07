"""Own the grocery subprocess without changing the daily-task worker protocol."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from tkinter import messagebox

from grocery_plan import load_state, load_catalog, new_state, save_state, now

ROOT = Path(__file__).resolve().parents[1]
OBSERVE_TIMEOUT_SECONDS = 45


class GroceryController:
    def __init__(self, ui, view, *, root=ROOT, popen=None, window_provider=None, capability=None):
        self.ui, self.view, self.root = ui, view, Path(root)
        self.process = None
        self.running = False
        self.stopping = False
        self._closed = False
        self._events = queue.Queue()
        self._popen = subprocess.Popen if popen is None else popen
        self._window_provider = window_provider
        self._request_mode = 'purchase'
        self._observe_started = None
        self._last_error = ''
        self._timed_out = False
        if capability is None:
            try:
                from grocery_driver import capability_summary
                capability = capability_summary()
            except ImportError:
                capability = {'live_purchase_supported': False, 'reason': '交易识别模块尚未就绪'}
        self.purchase_available = capability.get('live_purchase_supported') is True
        self.supported_item_ids = capability.get('supported_item_ids')
        if hasattr(view, 'set_purchase_capability'):
            view.set_purchase_capability(self.purchase_available, capability.get('reason', ''))
        balance_path = self.root / 'grocery_balances.json'
        if balance_path.exists():
            try:
                saved = json.loads(balance_path.read_text(encoding='utf-8-sig'))
                view.show_balance(saved['balances'], saved['read_at'])
            except (OSError, ValueError, KeyError, TypeError):
                view.show_status('上次余额记录无法读取，已保留原文件，请重新读取')
        self._timer = ui.after(100, self._drain)

    def _error(self, message):
        self.view.show_status(str(message))
        return False

    def _hwnd(self):
        if self._window_provider is None:
            from app import game_windows
            windows = game_windows()
        else:
            windows = self._window_provider()
        if not windows:
            raise ValueError('未检测到360火影游戏窗口，请打开游戏并停在杂货屋，不能最小化')
        choice = self.ui.window_choice.get()
        matches = [hwnd for hwnd, title in windows if choice == f'{title}  [{hwnd}]']
        if len(matches) == 1:
            return matches[0]
        if not choice and len(windows) == 1:
            return windows[0][0]
        raise ValueError('游戏窗口已变化，请在设置中重新选择当前游戏窗口')

    def start(self, new_round=False):
        if self.running:
            return False
        if not self.purchase_available:
            return self._error('购买流程尚待实机验证；可先读取余额和保存预设，当前不会发送购买')
        if getattr(self.ui, 'running', False):
            return self._error('每日任务正在运行，请先停止后再运行杂货屋')
        if getattr(self.ui, 'backend', None) and self.ui.backend.get() != '本地后台（免API）':
            return self._error('杂货屋使用本地后台，请先在设置中选择本地后台（免API）')
        state_path = self.root / 'grocery_state.json'
        try:
            # Always validate current visible fields, including when resuming.
            quantities = self.view.validated_quantities()
            previous = load_state(state_path)
            if previous and previous['status'] == 'done' and not new_round:
                return self._error('本轮已完成；要重新按预设购买，请选择“新一轮”')
            if previous and previous['status'] == 'needs_review' and not new_round:
                return self._error('上次购买结果不确定，请先核对游戏；不能自动继续或重发购买')
            if previous and any(item['status'] == 'uncertain' for item in previous['items']) and not new_round:
                return self._error('上次存在未确认交易，已阻止自动重买，请先核对游戏')
            if new_round and previous:
                question = ('上一轮存在未确认购买。请先核对游戏库存和余额。\n'
                            '确认已核对，并放弃续跑上一轮、按当前预设开始新一轮？'
                            if any(item['status'] == 'uncertain' for item in previous['items'])
                            else '按当前预设开始新一轮购买？上一轮记录会保留。')
                if not messagebox.askyesno('杂货屋 · 新一轮', question, parent=self.ui):
                    return False
            state = previous if previous and not new_round else new_state(load_catalog(), quantities)
            if not state['items']:
                return self._error('请至少给一件商品设置大于0的购买数量')
            if self.supported_item_ids is not None:
                from grocery_live import validate_items
                validate_items(state['items'])
                if any(item['quantity']-item['completed'] > 9999 for item in state['items']):
                    raise ValueError('单项购买数量最多9999，请调整预设')
            hwnd = self._hwnd()
            folder = self.root / 'verification/grocery-runs' / state['run_id']
            folder.mkdir(parents=True, exist_ok=True)
            if previous and new_round:
                # Archive before replacing the active journal, including unknown outcomes.
                archive = self.root / 'verification/grocery-runs' / previous['run_id']
                archive.mkdir(parents=True, exist_ok=True)
                save_state(archive / 'state-archived.json', deepcopy(previous))
            save_state(state_path, state)
            request = {'schema_version': 1, 'mode': 'purchase', 'hwnd': hwnd, 'run_id': state['run_id'],
                       'created_at': now(), 'evidence_dir': str(folder), 'state_path': str(state_path)}
            request_path = folder / 'request.json'
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            options = dict(cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
            if sys.platform == 'win32':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            process = self._popen([sys.executable, '-B', str(ROOT/'src/grocery_worker.py'), str(request_path)], **options)
        except (OSError, ValueError, TypeError, KeyError) as error:
            return self._error(f'杂货屋未启动：{error}')
        self.process, self.running, self.stopping = process, True, False
        self._request_mode = 'purchase'
        self.view.set_running(True)
        self.view.set_pending_state(True)
        self.view.show_status('正在连接杂货屋；按固定预设执行，余额以游戏实时识别为准')
        threading.Thread(target=self._read, args=(process,), daemon=True).start()
        return True

    def observe(self):
        """Read live balances without constructing a purchase journal."""
        if self.running:
            return False
        if getattr(self.ui, 'running', False):
            return self._error('每日任务正在运行，请先停止后再读取杂货屋余额')
        if getattr(self.ui, 'backend', None) and self.ui.backend.get() != '本地后台（免API）':
            return self._error('读取余额使用本地后台，请在设置中选择本地后台（免API）')
        try:
            hwnd = self._hwnd()
            folder = self.root / 'verification/grocery-runs' / ('balance-'+uuid.uuid4().hex[:12])
            folder.mkdir(parents=True, exist_ok=True)
            request = {'schema_version': 1, 'mode': 'observe', 'hwnd': hwnd,
                       'created_at': now(), 'evidence_dir': str(folder),
                       'balance_path': str(self.root/'grocery_balances.json')}
            path = folder/'request.json'
            path.write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            options = dict(cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
            if sys.platform == 'win32':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            process = self._popen([sys.executable, '-B', str(ROOT/'src/grocery_worker.py'), str(path)], **options)
        except (OSError, ValueError, TypeError) as error:
            return self._error(f'余额读取未启动：{error}')
        self.process, self.running, self.stopping = process, True, False
        self._request_mode = 'observe'
        self._observe_started = time.monotonic()
        self._last_error = ''
        self._timed_out = False
        self.view.set_running(True)
        self.view.show_status('正在只读识别四种余额；请保持杂货屋已打开')
        threading.Thread(target=self._read, args=(process,), daemon=True).start()
        return True

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError('invalid event')
                except (ValueError, TypeError):
                    event = {'kind': 'log', 'message': line.strip()}
                self._events.put(event)
            code = process.wait()
        except Exception as error:
            self._events.put({'kind': 'error', 'message': str(error)})
            code = 1
        self._events.put({'kind': 'exit', 'code': code, '_process': process})

    def _drain(self):
        try:
            while True:
                event = self._events.get_nowait()
                kind = event.get('kind')
                if kind == 'balance':
                    self.view.show_balance(event.get('balances', {}), event.get('read_at', event.get('at', '')))
                elif kind == 'progress':
                    self.view.show_progress(event)
                elif kind == 'exit':
                    if event.get('_process') is not self.process:
                        continue
                    self.running = False
                    self.process = None
                    self._observe_started = None
                    self.view.set_running(False)
                    if self._request_mode == 'observe':
                        if self._timed_out:
                            self.view.show_status('余额读取超时，已停止；请重试。历史余额未覆盖')
                        elif event['code'] == 0:
                            self.view.show_status('四种余额已读取并保存；当前仍以最后确认时间为准')
                        elif self.stopping:
                            self.view.show_status('余额读取已停止')
                        else:
                            self.view.show_status('余额读取失败：'+(self._last_error or f"工作进程退出（代码{event['code']}），请重试"))
                        # Preserve the worker's specific error for a failed read.
                        continue
                    try:
                        state = load_state(self.root / 'grocery_state.json')
                        pending = bool(state and state['status'] != 'done')
                        self.view.set_pending_state(pending)
                        if state:
                            balances = state.get('balances_latest')
                            if balances:
                                self.view.show_balance(balances, state.get('balances_read_at', ''))
                            if state['status'] == 'done':
                                self.view.show_status('本轮已完成，购买和跳过详情已保存')
                            elif state['status'] == 'needs_review' or any(i['status'] == 'uncertain' for i in state['items']):
                                self.view.show_status('已停止：存在待核对交易，请核对游戏后处理，不会自动重买')
                            elif self.stopping:
                                self.view.show_status('已停止，已确认完成的项目不会在继续本轮时重买')
                            else:
                                self.view.show_status('已停止：'+str(state.get('last_error') or '请查看本轮记录'))
                    except (OSError, ValueError, TypeError, KeyError) as error:
                        self.view.show_status(f'已停止，执行记录需核对：{error}')
                elif event.get('message'):
                    if kind == 'error':
                        self._last_error = str(event['message'])
                    self.view.show_status(event['message'])
        except queue.Empty:
            pass
        if (self.running and self._request_mode == 'observe' and not self.stopping
                and self._observe_started is not None
                and time.monotonic() - self._observe_started >= OBSERVE_TIMEOUT_SECONDS):
            self._timed_out = True
            self.stop()
            self.view.show_status('余额读取超时，正在结束读取进程；历史余额未覆盖')
        if not self._closed:
            self._timer = self.ui.after(100, self._drain)

    def stop(self):
        process = self.process
        if not self.running or process is None or self.stopping:
            return
        self.stopping = True
        self.view.show_status('正在停止；若交易已发送，将保留待核对状态')
        try:
            process.stdin.write('stop\n')
            process.stdin.flush()
        except (OSError, ValueError):
            pass
        def finish():
            # Give a bounded read/checkpoint time to persist the last observation.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        threading.Thread(target=finish, daemon=True).start()

    def close(self):
        self.stop()

    def is_alive(self):
        return bool(self.running)

    def dispose(self):
        if hasattr(self.view, 'flush_pending_edits'):
            self.view.flush_pending_edits()
        self._closed = True
        if self._timer:
            try:
                self.ui.after_cancel(self._timer)
            except Exception:
                pass
        self.stop()
