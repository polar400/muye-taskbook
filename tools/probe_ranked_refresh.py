"""Validate one free opponent refresh; never challenge or confirm purchases."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows


def main():
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
    window=BackgroundWindow(windows[0][0])
    flow=LocalFlows(window,LocalOCR(),{},lambda:None,lambda kind,msg:print(msg))
    before=flow.wait_ranked_ready()
    scope=flow.ranked_server_state()
    state,button=flow.ranked_refresh_state()
    if state!='ready':raise RuntimeError('当前刷新不可用，未发送点击')
    window.save(flow.image,ROOT/'verification/ranked-refresh-before.png')
    flow.refresh_ranked_after_defeat()
    flow.observe()
    window.save(flow.image,ROOT/'resources/local/ranked-refresh-cooldown-live.png')
    after=flow.wait_ranked_ready()
    state,_=flow.ranked_refresh_state()
    result=dict(server=scope,beforeRemaining=before[0],afterRemaining=after[0],refreshState=state,
                beforePowers=[o['power'] for o in before[2]],afterPowers=[o['power'] for o in after[2]],
                battleInput=False,refreshInput=True)
    (ROOT/'verification/ranked-refresh-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    if before[0]!=after[0]:raise RuntimeError('刷新改变了挑战次数')


if __name__=='__main__':main()
