"""Read-only live strong-panel check; no resize, activation, or game input."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from ctypes import wintypes
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
import json

def focus():
    point=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return dict(foreground=ctypes.windll.user32.GetForegroundWindow(),cursor=[point.x,point.y])

windows=game_windows()
if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
before=focus()
window=BackgroundWindow(windows[0][0])
ocr=LocalOCR()
flow=LocalFlows(window,ocr,{},lambda:None,lambda kind,message:print(message))
count,buttons=flow.wait_strong_ready()
start=flow.strong_start_button()
if start is None:raise RuntimeError('进入战斗按钮未识别')
window.save(flow.image,ROOT/'verification/strong-background-probe.png')
result=dict(ordinaryRewards=count,difficultyButtons=buttons,startButton=start,size=[flow.image.shape[1],flow.image.shape[0]],before=before,after=focus(),gameInput=False)
(ROOT/'verification/strong-background-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
