"""Explicitly authorized cursor compatibility test; never clicks any button."""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import textwrap
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.background_window import BackgroundWindow,client_to_message,u
from adapters.local_ocr import LocalOCR
from app import game_windows
from local_flows import LocalFlows
from arena_daily import ArenaDaily
from arena_task import ArenaTask


def main():
    decision=json.loads((ROOT/'verification/arena-cursor-hover-proposal-20261020.json').read_text(encoding='utf-8'))
    if decision.get('decision')!='allowed_by_user':
        raise RuntimeError('用户坚持完全后台，真实鼠标兼容试验已停用；参数不构成授权')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-real-cursor',action='store_true',required=True)
    args=parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('需要唯一游戏窗口；未移动鼠标')
    namespace=dict(contextmanager=contextmanager,ctypes=ctypes,W=W,u=u,client_to_message=client_to_message)
    source=(ROOT/'verification/arena-cursor-hover-proposed-method-20261020.txt').read_text(encoding='utf-8')
    exec(compile(textwrap.dedent(source),'<cursor hover proposal>','exec'),namespace)
    class ProbeWindow(BackgroundWindow):cursor_hover=namespace['cursor_hover']
    u.GetCursorPos.argtypes=[ctypes.POINTER(W.POINT)];u.GetCursorPos.restype=W.BOOL
    u.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int];u.SetCursorPos.restype=W.BOOL
    u.GetForegroundWindow.restype=W.HWND
    w=ProbeWindow(windows[0][0]);im=w.capture()
    if im.shape!=(1015,1920,3):raise RuntimeError('需要已校准竞技场；未调整窗口')
    f=LocalFlows(w,LocalOCR(),{},lambda:None,lambda *a,**k:None)
    f.image=im;f.items=f.ocr.read(im);runner=ArenaDaily(ArenaTask(f),'休闲战斗');board=runner.board()
    if not board:raise RuntimeError('任务板无法读取；未移动鼠标')
    card=next((c for c in board['cards'] if c['state']=='unmet' and not c['hovered']),None)
    if card is None:raise RuntimeError('没有未悬停的未满足项；未移动鼠标')
    x,y,bw,bh=card['button']['box'];x+=bw//2;y+=bh//2
    folder=ROOT/'verification'/('arena-cursor-compat-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir();w.save(im,folder/'before.png');cursor=W.POINT();u.GetCursorPos(ctypes.byref(cursor))
    data=dict(root=w.root,target=int(w.target),boardBefore=board,point=[x,y],buttonClicks=0,
              cursorBefore=[cursor.x,cursor.y],foregroundBefore=int(u.GetForegroundWindow() or 0),frames=[],result='failed')
    def save():(folder/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    save();images=[]
    try:
        with w.cursor_hover(x,y) as guard:
            start=time.monotonic()
            for index,delay in enumerate((0,.3,.6,1,1.5)):
                time.sleep(max(0,delay-(time.monotonic()-start)))
                if not guard():raise RuntimeError('用户已移动鼠标，停止兼容试验')
                image=w.capture();name=f'after-{index}.png';w.save(image,folder/name)
                data['frames'].append(dict(file=name,elapsed=round(time.monotonic()-start,4)));images.append(image)
        data['result']='captured'
    finally:
        u.GetCursorPos(ctypes.byref(cursor));data['cursorAfter']=[cursor.x,cursor.y]
        data['foregroundAfter']=int(u.GetForegroundWindow() or 0);save()
    for frame,image in zip(data['frames'],images):
        strip=image[350:790,90:342].copy();frame['board']=runner.vision.read(strip,(90,350))
        frame['lower']=runner.vision.match(strip,'lower')
    data['triggeredTarget']=any(frame['board'] and frame['board']['cards'][card['index']]['hovered'] for frame in data['frames'])
    save()
    print(str(folder),flush=True)
    print(json.dumps(dict(triggeredTarget=data['triggeredTarget'],lowerCounts=[len(p['lower']) for p in data['frames']],
        cursorRestored=data['cursorBefore']==data['cursorAfter'],
        foregroundUnchanged=data['foregroundBefore']==data['foregroundAfter'],buttonClicks=0)),flush=True)


if __name__=='__main__':main()
