"""Read two live end-battle button positions without sending game input."""
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
from local_flows import LocalFlows


def focus():
    point=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return dict(foreground=ctypes.windll.user32.GetForegroundWindow(),cursor=[point.x,point.y])


def main():
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
    before=focus()
    window=BackgroundWindow(windows[0][0])
    flow=LocalFlows(window,LocalOCR(),{},lambda:None,lambda kind,message:None)
    buttons=[]
    for _ in range(2):
        flow.image=window.capture()
        buttons.append(flow.ranked_end_battle_button())
    window.save(flow.image,ROOT/'verification/ranked-battle-background-probe.png')
    result=dict(buttons=buttons,before=before,after=focus(),gameInput=False)
    (ROOT/'verification/ranked-battle-background-probe.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    if any(button is None for button in buttons):raise RuntimeError('当前画面未唯一识别结束战斗按钮；未发送点击')
    if buttons[0]['box']!=buttons[1]['box']:raise RuntimeError('结束战斗按钮位置仍在变化；未发送点击')


if __name__=='__main__':main()
