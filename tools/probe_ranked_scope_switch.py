"""Validate a reversible scope switch; does not start any battle."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_vision import read_ranked_remaining
from local_flows import normalized


def main():
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('游戏窗口不唯一')
    window=BackgroundWindow(windows[0][0])
    flow=LocalFlows(window,LocalOCR(),{},lambda:None,lambda kind,msg:print(msg))
    flow.observe()
    if not flow.ranked_panel_visible():raise RuntimeError('当前不是排位面板，未切换')
    original=flow.ranked_server_state()
    if original not in ('本服','连服'):raise RuntimeError('无法确认原范围，未切换')
    target='本服' if original=='连服' else '连服'
    count=read_ranked_remaining(flow.image,flow.items,flow.ocr,normalized)
    try:
        button=flow.ranked_server_button(target)
        print(json.dumps(dict(button=button,geometry=window.geometry),ensure_ascii=True))
        flow.click_item(button)
        flow.wait(lambda:flow.ranked_panel_visible() and flow.ranked_server_state()==target,15)
        flow.observe()
        window.save(flow.image,ROOT/'verification/ranked-scope-switched.png')
    finally:
        flow.ensure_ranked_server(original)
    after=read_ranked_remaining(flow.image,flow.items,flow.ocr,normalized)
    window.save(flow.image,ROOT/'verification/ranked-scope-restored.png')
    result=dict(original=original,target=target,beforeRemaining=count,afterRemaining=after,battleInput=False,scopeInput=True)
    (ROOT/'verification/ranked-scope-switch.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    if after!=count:raise RuntimeError('切换前后次数不一致')


if __name__=='__main__':main()
