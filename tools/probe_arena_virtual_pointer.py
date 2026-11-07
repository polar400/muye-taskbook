"""Explicitly authorized Flash virtual-pointer trial. One move, zero clicks."""
import argparse
import ctypes
from ctypes import wintypes as W
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow,u
from adapters.local_ocr import LocalOCR
from arena_daily import ArenaDaily
from arena_task import ArenaTask
from local_flows import LocalFlows
from arena_virtual_pointer import ArenaVirtualPointer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-render-process-shim',action='store_true',required=True)
    parser.parse_args()
    authorization=ROOT/'verification/arena-virtual-pointer-authorization-20261020.json'
    auth=json.loads(authorization.read_text(encoding='utf-8')) if authorization.exists() else {}
    if auth.get('decision')!='allowed_by_user' or auth.get('remaining')!=1:
        raise RuntimeError('未获准游戏进程虚拟指针试验；参数不构成授权')
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('需要唯一游戏窗口；未修改进程')
    w=BackgroundWindow(windows[0][0]);im=w.capture()
    if im.shape!=(1015,1920,3):raise RuntimeError('需要已校准竞技场；未调整窗口')
    f=LocalFlows(w,LocalOCR(),{},lambda:None,lambda *a,**k:None)
    f.image=im;f.items=f.ocr.read(im);runner=ArenaDaily(ArenaTask(f),'休闲战斗');board=runner.board()
    if not board:raise RuntimeError('任务板无法可靠读取；未修改进程')
    card=next((c for c in board['cards'] if c['state']=='unmet' and not c['hovered']),None)
    if card is None:raise RuntimeError('没有未满足未悬停任务；未修改进程')
    x,y,bw,bh=card['button']['box'];x+=bw//2;y+=bh//2
    folder=ROOT/'verification'/('arena-virtual-pointer-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir();w.save(im,folder/'before.png')
    u.GetCursorPos.argtypes=[ctypes.POINTER(W.POINT)];u.GetCursorPos.restype=W.BOOL
    u.GetForegroundWindow.restype=W.HWND
    cursor=W.POINT();u.GetCursorPos(ctypes.byref(cursor))
    data=dict(result='preparing',root=w.root,target=int(w.target),boardBefore=board,point=[x,y],
              buttonClicks=0,realMouseInputs=0,cursorBefore=[cursor.x,cursor.y],
              foregroundBefore=int(u.GetForegroundWindow() or 0),importPointersRestored=False)
    def save():(folder/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    save();pointer=ArenaVirtualPointer(w);frames=[];images=[]
    auth.update(decision='consumed',remaining=0,evidence=folder.relative_to(ROOT).as_posix())
    authorization.write_text(json.dumps(auth,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        pointer.prepare(x,y);data['shim']=pointer.evidence;save()
        with pointer.transaction:
            data['result']='active';save();w.hover(x,y);data['moveMessages']=1
            start=time.monotonic()
            for index,delay in enumerate((0,.3,.6,1,1.5)):
                time.sleep(max(0,delay-(time.monotonic()-start)))
                image=w.capture();name=f'after-{index}.png';w.save(image,folder/name)
                frames.append(dict(file=name,elapsed=round(time.monotonic()-start,4)));images.append(image)
        data['importPointersRestored']=all(pointer.memory.read(e['address'],4).hex()==e['original'] for e in pointer.evidence['entries'])
        if not data['importPointersRestored']:raise RuntimeError('虚拟指针入口恢复未确认')
        data['result']='captured'
    except BaseException as error:data['error']=str(error);raise
    finally:
        pointer.close();u.GetCursorPos(ctypes.byref(cursor));data['cursorAfter']=[cursor.x,cursor.y]
        data['foregroundAfter']=int(u.GetForegroundWindow() or 0);data['frames']=frames;save()
        print(str(folder),flush=True)
    for frame,image in zip(frames,images):
        strip=image[350:790,90:342].copy();frame['board']=runner.vision.read(strip,(90,350));frame['lower']=runner.vision.match(strip,'lower')
    data['triggeredTarget']=any(frame['board'] and frame['board']['cards'][card['index']]['hovered'] for frame in frames)
    save()
    print(json.dumps(dict(triggeredTarget=data['triggeredTarget'],lowerCounts=[len(p['lower']) for p in frames],
        importPointersRestored=data['importPointersRestored'],cursorUnchanged=data['cursorBefore']==data['cursorAfter'],
        foregroundUnchanged=data['foregroundBefore']==data['foregroundAfter'],buttonClicks=0)),flush=True)


if __name__=='__main__':main()
