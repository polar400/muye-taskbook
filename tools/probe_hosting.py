"""Read-only hosting entrance check; never activate, resize, or click."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from ctypes import wintypes
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows


def desktop_state():
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return dict(foreground=ctypes.windll.user32.GetForegroundWindow(), cursor=[point.x, point.y])


windows = game_windows()
if len(windows) != 1:
    raise RuntimeError('游戏窗口不唯一')
before = desktop_state()
window = BackgroundWindow(windows[0][0])
flow = LocalFlows(window, LocalOCR(), {}, lambda: None, lambda *args: None)
flow.home()
button = flow.hosting_computer_button()
if button is None:
    raise RuntimeError('托管小电脑图标未识别')
window.save(flow.image, ROOT/'verification/hosting-background-probe.png')
result = dict(button=button, size=[flow.image.shape[1], flow.image.shape[0]],
              before=before, after=desktop_state(), gameInput=False)
(ROOT/'verification/hosting-background-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
