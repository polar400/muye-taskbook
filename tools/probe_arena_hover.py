"""Bounded arena hover diagnostics. Never press buttons or move the real cursor."""
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
from local_flows import LocalFlows
from arena_task import ArenaTask
from arena_daily import ArenaDaily


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial',required=True,choices=('activate-render','activate-wrapper','wrapper-move','setcursor-render',
        'focus-render','enter-render','maa-hover'))
    args=parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('需要唯一游戏窗口；未发送输入')
    w=BackgroundWindow(windows[0][0]);im=w.capture()
    if im.shape!=(1015,1920,3):raise RuntimeError('需要已校准竞技场；未调整窗口')
    f=LocalFlows(w,LocalOCR(),{},lambda:None,lambda *a,**k:None)
    f.image=im;f.items=f.ocr.read(im);runner=ArenaDaily(ArenaTask(f),'休闲战斗')
    board=runner.board()
    if not board:raise RuntimeError('任务板无法可靠读取；未发送输入')
    card=next((c for c in board['cards'] if c['state']=='unmet' and not c['hovered']),None)
    if card is None:raise RuntimeError('没有可诊断的未悬停未满足项；未发送输入')
    x,y,bw,bh=card['button']['box'];x+=bw//2;y+=bh//2
    folder=ROOT/'verification'/('arena-hover-probe-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir();w.save(im,folder/'before.png')
    u.GetForegroundWindow.restype=W.HWND
    u.GetParent.argtypes=[W.HWND];u.GetParent.restype=W.HWND
    foreground=int(u.GetForegroundWindow() or 0)
    data=dict(trial=args.trial,root=w.root,target=int(w.target),geometry=list(w.geometry),
              boardBefore=board,point=[x,y],foregroundBefore=foreground,messages=[],buttonClicks=0,realMouseInputs=0)
    def save():
        (folder/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    def send(h,msg,wp,lp):
        w.check()
        physical_context=u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            if w.geometry!=w.measure():raise RuntimeError('窗口几何变化，停止诊断')
        finally:u.SetThreadDpiAwarenessContext(physical_context)
        entry=dict(hwnd=int(h),message=msg,wParam=int(wp),lParam=int(lp),status='sending')
        data['messages'].append(entry);save();result=ctypes.c_size_t()
        if not u.SendMessageTimeoutW(h,msg,wp,lp,2,1000,ctypes.byref(result)):raise RuntimeError('消息结果未知，停止')
        entry['status']='sent';save()
    try:
        if args.trial=='activate-render':send(w.target,0x6,1,0)
        elif args.trial in ('activate-wrapper','wrapper-move'):
            parent=u.GetParent(w.target);name=ctypes.create_unicode_buffer(256);u.GetClassNameW(parent,name,256)
            if name.value!='WrapperNativeWindowClass':raise RuntimeError('包装窗口与实测类型不符')
            if args.trial=='activate-wrapper':send(parent,0x6,1,0);send(w.target,0x6,1,0)
            else:
                old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(parent))
                try:
                    rect=W.RECT();u.GetClientRect(parent,ctypes.byref(rect))
                    # The wrapper must cover exactly the same physical game region.
                    if (rect.right,rect.bottom)!=(1280,677):raise RuntimeError('包装客户区与本次对照基线不符')
                    mx=int(x*rect.right/1920);my=int(y*rect.bottom/1015)
                    send(parent,0x200,0,(my<<16)|mx)
                finally:u.SetThreadDpiAwarenessContext(old)
        elif args.trial=='setcursor-render':send(w.target,0x20,w.target,(0x200<<16)|1)
        elif args.trial=='focus-render':send(w.target,0x6,1,0);send(w.target,0x7,0,0)
        elif args.trial=='enter-render':
            old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(w.target))
            try:
                point=W.POINT(x,y);rect=W.RECT();u.GetClientRect(w.target,ctypes.byref(rect))
                point.x=int(x*rect.right/1920);point.y=int(y*rect.bottom/1015)
                u.ClientToScreen(w.target,ctypes.byref(point))
                send(w.target,0x84,0,(point.y<<16)|(point.x&0xffff))
                send(w.target,0x20,w.target,(0x200<<16)|1)
            finally:u.SetThreadDpiAwarenessContext(old)
        elif args.trial=='maa-hover':
            from maa.controller import Win32Controller
            from maa.define import MaaWin32ScreencapMethodEnum as Capture,MaaWin32InputMethodEnum as Input
            controller=Win32Controller(w.target,Capture.GDI,Input.SendMessage,Input.Null)
            controller.set_screenshot_use_raw_size(True)
            if not controller.post_connection().wait().succeeded:raise RuntimeError('Maa后台输入连接失败')
            if not controller.post_screencap().wait().succeeded:raise RuntimeError('Maa渲染窗口截图失败')
            image=controller.cached_image
            if image is None or image.shape!=(1015,1920,3):raise RuntimeError('Maa坐标原图尺寸不符')
            data['messages'].append(dict(via='Maa SendMessage TouchMove, no down/up',x=x,y=y,status='sending'));save()
            if not controller.post_touch_move(x,y,contact=0,pressure=0).wait().succeeded:raise RuntimeError('Maa后台移动失败')
            data['messages'][-1]['status']='sent'
        if args.trial not in ('wrapper-move','maa-hover'):
            # Use the existing geometry and DPI implementation unchanged.
            w.hover(x,y)
            data['messages'].append(dict(hwnd=int(w.target),message=0x200,status='sent',via='existing hover'))
        frames=[];images=[];start=time.monotonic()
        for index,delay in enumerate((0,.3,.7,1.5,3)):
            time.sleep(max(0,delay-(time.monotonic()-start)))
            image=w.capture();name=f'after-{index}.png';w.save(image,folder/name)
            frames.append(dict(file=name,elapsed=round(time.monotonic()-start,4)));images.append(image)
        for frame,image in zip(frames,images):
            strip=image[350:790,90:342].copy();frame['board']=runner.vision.read(strip,(90,350))
            frame['lower']=runner.vision.match(strip,'lower')
        data['frames']=frames;data['foregroundAfter']=int(u.GetForegroundWindow() or 0)
        data['triggeredTarget']=any(frame['board'] and frame['board']['cards'][card['index']]['hovered'] for frame in frames)
    finally:save();print(str(folder),flush=True)
    print(json.dumps(dict(trial=args.trial,triggeredTarget=data['triggeredTarget'],
        lowerCounts=[len(frame['lower']) for frame in data['frames']],
        foregroundUnchanged=data['foregroundBefore']==data['foregroundAfter'],buttonClicks=0)),flush=True)


if __name__=='__main__':main()
