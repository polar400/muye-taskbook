"""Pending authorization: one arena lower + confirm, no matching or real cursor."""
import argparse
import ctypes
from ctypes import wintypes as W
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]


def read_authorization():
    path=ROOT/'verification/arena-lower-virtual-authorization-20261020.json'
    auth=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if (auth.get('decision')!='allowed_by_user' or auth.get('remaining')!=1
            or auth.get('scopeCode')!='arena-lower-confirm-once'):
        raise RuntimeError('尚未获准虚拟指针降级确认验收；旧悬停授权已用完，参数不构成授权')
    return path,auth


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lower-and-confirm-once',action='store_true',required=True)
    parser.parse_args()
    authorization,auth=read_authorization()  # Gate before desktop/process APIs.
    from app import game_windows
    from adapters.background_window import BackgroundWindow,u
    from adapters.local_ocr import LocalOCR
    from arena_daily import ArenaDaily
    from arena_task import ArenaTask
    from arena_lower_probe import LowerOnceProbe
    from arena_virtual_pointer import ArenaVirtualPointer
    from local_flows import LocalFlows

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('需要唯一游戏窗口；未修改进程')
    window=BackgroundWindow(windows[0][0]);image=window.capture()
    if image.shape!=(1015,1920,3):raise RuntimeError('需要已校准竞技场；不调整窗口')
    flow=LocalFlows(window,LocalOCR(),{},lambda:None,lambda *a,**k:None)
    flow.image=image;flow.items=flow.ocr.read(image)
    runner=ArenaDaily(ArenaTask(flow),'休闲战斗')
    if not runner.board():raise RuntimeError('当前不是可识别竞技场任务板；未修改进程')
    pointers=[ArenaVirtualPointer(window,purpose='lower-once') for _ in range(2)]
    folder=ROOT/'verification'/('arena-lower-virtual-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir();count=0
    u.GetCursorPos.argtypes=[ctypes.POINTER(W.POINT)];u.GetCursorPos.restype=W.BOOL
    u.GetForegroundWindow.restype=W.HWND
    def state():
        point=W.POINT()
        if not u.GetCursorPos(ctypes.byref(point)):raise RuntimeError('无法读取真实鼠标位置')
        return dict(cursor=[point.x,point.y],foreground=int(u.GetForegroundWindow() or 0))
    initial=state()
    def save(label,report):
        nonlocal count
        name=f'{count:02}-{label}.png';count+=1
        if flow.image is not None:window.save(flow.image,folder/name)
        report.update(root=window.root,target=int(window.target),stateBefore=initial,lastImage=name)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    probe=LowerOnceProbe(runner,pointers,save)
    # Consume before the first prepare/OpenProcess, including failures. No retry.
    auth.update(decision='consumed',remaining=0,evidence=folder.relative_to(ROOT).as_posix())
    authorization.write_text(json.dumps(auth,ensure_ascii=False,indent=2),encoding='utf-8')
    try:probe.run()
    finally:
        for pointer in pointers:pointer.close()
        final=state();probe.report.update(stateAfter=final,cursorUnchanged=initial['cursor']==final['cursor'],
            foregroundUnchanged=initial['foreground']==final['foreground'],
            inputAttempts=sum(e['status'] in ('sending','sent') for e in probe.report['inputs']))
        save('final',probe.report);print(str(folder),flush=True)
    print(json.dumps(dict(result=probe.report['result'],inputAttempts=probe.report['inputAttempts']),ensure_ascii=True))


if __name__=='__main__':main()
