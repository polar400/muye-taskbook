"""Inspect the current ranked panel without activation, resizing or clicks."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from ctypes import wintypes
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows,select_opponent

def focus():
    point=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return dict(foreground=ctypes.windll.user32.GetForegroundWindow(),cursor=[point.x,point.y])

windows=game_windows()
if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
before=focus()
window=BackgroundWindow(windows[0][0])
cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
flow=LocalFlows(window,LocalOCR(),cfg,lambda:None,lambda kind,message:None)
states=[]
for _ in range(2):
    flow.image=window.capture();flow.items=flow.ocr.read(flow.image)
    states.append(flow.ranked_state())
def signature(state):
    count,own,opponents=state
    return count,own,tuple(sorted(item['power'] for item in opponents))
# Compare game values, as wait_ranked_ready does. OCR confidence or a
# one-pixel text-box variation does not mean the challenge count changed.
if signature(states[0])!=signature(states[1]):raise RuntimeError('排位战面板仍在变化，未发送点击')
count,own,opponents=states[-1]
picked=select_opponent(own,opponents,cfg.get('tolerance',20)) if count else None
window.save(flow.image,ROOT/'verification/ranked-background-probe.png')
result=dict(remaining=count,ownPower=own,opponents=opponents,selected=picked,
            before=before,after=focus(),gameInput=False)
(ROOT/'verification/ranked-background-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
