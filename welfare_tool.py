"""Independent welfare UI/worker. No shared task list or configuration writes."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import threading
import json
import uuid

ROOT = Path(__file__).resolve().parent


def worker(hwnd):
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    from adapters.background_window import BackgroundWindow
    from adapters.local_ocr import LocalOCR
    from welfare_task import WelfareTask
    stop = threading.Event()
    def commands():
        for line in sys.stdin:
            if line.strip() == 'stop':
                stop.set()
        stop.set()
    threading.Thread(target=commands, daemon=True).start()
    def checkpoint():
        if stop.is_set():
            raise RuntimeError('用户停止福利大厅任务')
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    folder = ROOT / 'verification' / ('welfare-'+stamp+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    print('证据目录：'+str(folder), flush=True)
    try:
        window = BackgroundWindow(hwnd)
        window.calibrate(checkpoint, lambda message: print(message, flush=True))
        task = WelfareTask(window, LocalOCR(), folder, checkpoint, lambda message: print(message, flush=True))
        task.run()
        return 0
    except Exception as error:
        if not (folder / 'report.json').exists():
            (folder / 'report.json').write_text(json.dumps({'status': 'stopped', 'error': str(error),
                'gameInputs': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
        print('已停止：'+str(error), flush=True)
        return 1


def ui():
    import queue
    import subprocess
    import tkinter as tk
    from tkinter import ttk
    from app import game_windows
    root = tk.Tk()
    root.title('福利大厅 · 每日领取')
    root.geometry('720x440')
    root.minsize(650, 400)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='每日福利 → 月卡／大月卡／勋章 → 上忍／中忍／下忍 → 在线礼包 → 关闭').pack(anchor='w')
    ttk.Label(frame, text='先停止其他助手任务。游戏可遮挡，不可最小化；仅领取现有奖励。').pack(anchor='w', pady=(6, 12))
    choices = ttk.Combobox(frame, state='readonly')
    choices.pack(fill='x')
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=10)
    output = tk.Text(frame, wrap='word', state='disabled')
    output.pack(fill='both', expand=True)
    state = {'process': None, 'windows': [], 'closing': False}
    messages = queue.Queue()
    def log(text):
        output.configure(state='normal')
        output.insert('end', text+'\n')
        output.see('end')
        output.configure(state='disabled')
    def refresh():
        state['windows'] = game_windows()
        choices['values'] = [f'{title} [{hwnd}]' for hwnd, title in state['windows']]
        if state['windows']:
            choices.current(0)
        else:
            choices.set('')
            log('未检测到360火影忍者游戏窗口，请打开游戏后刷新。')
    def start():
        if state['process'] is not None:
            return
        index = choices.current()
        if index < 0 or index >= len(state['windows']):
            log('请选择游戏窗口。')
            return
        hwnd = state['windows'][index][0]
        import os
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        proc = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--hwnd', str(hwnd)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', env=env, cwd=ROOT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        state['process'] = proc
        start_button.configure(state='disabled')
        refresh_button.configure(state='disabled')
        choices.configure(state='disabled')
        def read():
            for line in proc.stdout:
                messages.put(line.rstrip())
            proc.wait()
            messages.put(None)
        threading.Thread(target=read, daemon=True).start()
    def stop():
        proc = state['process']
        if proc and proc.poll() is None:
            try:
                proc.stdin.write('stop\n')
                proc.stdin.flush()
                log('已请求停止，等待当前后台调用结束。')
            except (OSError, ValueError):
                pass
    def poll():
        while not messages.empty():
            message = messages.get()
            if message is None:
                proc = state['process']
                log('进程结束，退出码 '+str(proc.returncode))
                proc.stdin.close()
                proc.stdout.close()
                state['process'] = None
                start_button.configure(state='normal')
                refresh_button.configure(state='normal')
                choices.configure(state='readonly')
            else:
                log(message)
        if state['closing'] and state['process'] is None:
            root.destroy()
            return
        root.after(100, poll)
    def close():
        state['closing'] = True
        stop()
    refresh_button = ttk.Button(row, text='刷新窗口', command=refresh)
    refresh_button.pack(side='left')
    start_button = ttk.Button(row, text='打开并领取每日奖励', command=start)
    start_button.pack(side='left', padx=8)
    ttk.Button(row, text='停止', command=stop).pack(side='left')
    refresh()
    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='福利大厅独立工具；不传参数打开交互窗口')
    parser.add_argument('--hwnd', type=int)
    args = parser.parse_args()
    if args.hwnd is None:
        ui()
    else:
        raise SystemExit(worker(args.hwnd))
