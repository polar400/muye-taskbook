"""Read-only check of a first-start prompt or active hosting banner."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows

windows = game_windows()
if len(windows) != 1:
    raise RuntimeError('游戏窗口不唯一')
window = BackgroundWindow(windows[0][0])
flow = LocalFlows(window, LocalOCR(), {}, lambda: None, lambda *args: None)
flow.observe()
button = flow.hosting_activation_dialog()
active = bool(flow.hits(r'^托管中$')) if button is None else False
if button is None and not active:
    raise RuntimeError('当前未识别到首次托管确认或托管中状态')
window.save(flow.image, ROOT/'verification/hosting-start-probe.png')
result = dict(state='first_confirmation' if button else 'active',
              confirmButton=button, gameInput=False,
              size=[flow.image.shape[1], flow.image.shape[0]])
(ROOT/'verification/hosting-start-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
