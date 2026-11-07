"""Non-consuming integration check: background open/close survival panel."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from ctypes import wintypes as W
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
u=ctypes.windll.user32;u.GetForegroundWindow.restype=W.HWND
def state():
    p=W.POINT();u.GetCursorPos(ctypes.byref(p));return {'foreground':u.GetForegroundWindow(),'cursor':[p.x,p.y]}
windows=game_windows()
if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
before=state();window=BackgroundWindow(windows[0][0],sys.argv[1] if len(sys.argv)>1 else 'SendMessage');ocr=LocalOCR()
flow=LocalFlows(window,ocr,{},lambda:None,lambda k,m:print(m,flush=True))
flow.enter('生存演习');flow.wait_text(r'演习积分:(\d+)/(\d+)')
window.save(flow.image,ROOT/'verification/native-integrated-panel.png')
flow.close_panel();after=state()
result={'before':before,'after':after,'foregroundUnchanged':before['foreground']==after['foreground'],'cursorUnchanged':before['cursor']==after['cursor'],'openedAndClosed':True}
(ROOT/'verification/native-integrated-io.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
