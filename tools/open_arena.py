"""Standalone local stage-one entry while shared UI integration is coordinated.

Default: list available game windows, no input. --open: navigate once and stop.
"""
import argparse
import ctypes
import json
from pathlib import Path
import sys
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from arena_task import run_arena


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--hwnd',type=int)
    args=parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    print(json.dumps(windows,ensure_ascii=False),flush=True)
    if not args.open:return
    if args.hwnd is not None:windows=[w for w in windows if w[0]==args.hwnd]
    if len(windows)!=1:raise RuntimeError('无法唯一连接游戏窗口，请打开游戏并通过--hwnd指定目标；未发送输入')
    folder=ROOT/'verification'/('arena-live-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir()
    events=[]
    def emit(kind,message,**extra):
        events.append(dict(kind=kind,message=message,**extra))
        print(message,flush=True)
    class ArenaWindow:
        def __init__(self):self.actual=BackgroundWindow(windows[0][0]);self.inputs=[]
        def capture(self):return self.actual.capture()
        def save(self,image,path):self.actual.save(image,folder/'latest.png')
        def click(self,x,y):
            self.inputs.append(dict(x=x,y=y,status='sending'))
            (folder/'inputs.json').write_text(json.dumps(self.inputs,indent=2),encoding='utf-8')
            self.actual.click(x,y)
            self.inputs[-1]['status']='sent'
    window=ArenaWindow()
    flow=None
    try:
        image=window.actual.calibrate(log=lambda m:emit('log',m))
        window.save(image,None)
        flow=LocalFlows(window,LocalOCR(),{'tasks':['arena']},lambda:None,emit)
        result=run_arena(flow)
        report=dict(result=result,evidence=flow.arena_evidence)
    except Exception as error:
        report=dict(result='failed',error=str(error))
        raise
    finally:
        if flow is not None and flow.image is not None:window.save(flow.image,None)
        (folder/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'inputs.json').write_text(json.dumps(window.inputs,indent=2),encoding='utf-8')
        if 'report' in locals():(folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Evidence:',folder,flush=True)


if __name__=='__main__':main()
