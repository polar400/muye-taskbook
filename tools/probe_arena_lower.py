"""One guarded arena task-condition click; stop at the lower confirmation dialog."""
import argparse
import ctypes
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from arena_daily import ArenaDaily
from arena_task import ArenaTask
from local_flows import LocalFlows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open-dialog',required=True,action='store_true')
    parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('需要唯一游戏窗口；未输入')
    w=BackgroundWindow(windows[0][0]);im=w.capture()
    if im.shape!=(1015,1920,3):raise RuntimeError('需要已校准竞技场；未调整窗口')
    folder=ROOT/'verification'/('arena-lower-direct-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir();events=[];inputs=[]
    def emit(kind,message,**extra):events.append(dict(kind=kind,message=message,**extra))
    f=LocalFlows(w,LocalOCR(),{},lambda:None,emit)
    def observe():f.image=w.capture();f.items=f.ocr.read(f.image);return f.items
    f.observe=observe
    actual_click=f.click_item
    def click(item,delay=.6):
        inputs.append(dict(box=item['box'],status='sending'))
        (folder/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
        actual_click(item,delay);inputs[-1]['status']='sent'
    f.click_item=click
    a=ArenaTask(f);runner=ArenaDaily(a,'休闲战斗');report=dict(result='failed',buttonClicks=0,realMouseInputs=0)
    try:
        board=runner.stable();report['boardBefore']=board
        card=next((c for c in board['cards'] if c['state']=='unmet' and c['progress']==0),None)
        if card is None:raise RuntimeError('没有已确认未满足任务；未点击')
        w.save(f.image,folder/'before.png')
        runner.act('核对未满足任务后打开降低难度确认一次',lambda:runner.fresh_card(board,card['index'],'unmet'))
        frames=[];start=time.monotonic()
        for index in range(5):
            time.sleep(.25);observe();w.save(f.image,folder/f'after-{index}.png')
            button=runner.lower_dialog()
            frames.append(dict(file=f'after-{index}.png',elapsed=round(time.monotonic()-start,4),confirmation=button))
            if button:
                report.update(result='lower-dialog-confirmed',confirmation=button);break
        report['frames']=frames
    finally:
        report.update(events=events,inputs=inputs,buttonClicks=len(inputs))
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
        if f.image is not None:w.save(f.image,folder/'last.png')
        print(str(folder),flush=True)
    print(json.dumps(dict(result=report['result'],buttonClicks=len(inputs),realMouseInputs=0)),flush=True)


if __name__=='__main__':main()
