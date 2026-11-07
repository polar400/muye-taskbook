"""Reproducible MaaFramework window-capture/input compatibility probe."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
ctypes.windll.shcore.SetProcessDpiAwareness(2)
sys.path.insert(0,str(ROOT/'vendor'))
from maa.controller import Win32Controller
from maa.define import MaaWin32ScreencapMethodEnum as Capture, MaaWin32InputMethodEnum as Input
from maa.toolkit import Toolkit
from PIL import Image

u=ctypes.windll.user32
u.GetForegroundWindow.restype=wintypes.HWND
u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
u.IsIconic.argtypes=[wintypes.HWND]
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
u.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
u.GetAncestor.restype=wintypes.HWND
u.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
u.PostMessageW.restype=wintypes.BOOL
u.GetWindowDpiAwarenessContext.argtypes=[wintypes.HWND]
u.GetWindowDpiAwarenessContext.restype=ctypes.c_void_p
u.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
u.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p

def observe():
    p=wintypes.POINT();u.GetCursorPos(ctypes.byref(p))
    return {'foreground':u.GetForegroundWindow(),'cursor':[p.x,p.y]}

def windows():
    roots=[w for w in Toolkit.find_desktop_windows() if w.window_name=='火影忍者ol']
    output=[]
    def info(hwnd):
        cls=ctypes.create_unicode_buffer(512);u.GetClassNameW(hwnd,cls,512)
        r=wintypes.RECT();c=wintypes.RECT();u.GetWindowRect(hwnd,ctypes.byref(r));u.GetClientRect(hwnd,ctypes.byref(c))
        output.append({'hwnd':hwnd,'class':cls.value,'rect':[r.left,r.top,r.right,r.bottom],'client':[c.right,c.bottom],'minimized':bool(u.IsIconic(hwnd))})
    for root in roots:
        info(root.hwnd)
        callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)(lambda h,p:info(h) or True)
        u.EnumChildWindows(root.hwnd,callback,0)
    return output

def main():
    p=argparse.ArgumentParser();p.add_argument('--hwnd',type=int);p.add_argument('--method',choices=['PrintWindow','FramePool'],default='PrintWindow');p.add_argument('--input',choices=['PostMessage','SendMessage'],default='PostMessage');p.add_argument('--output',default='capture');p.add_argument('--click',nargs=2,type=int);p.add_argument('--direct-target',type=int);a=p.parse_args()
    folder=ROOT/'verification';folder.mkdir(exist_ok=True)
    if a.hwnd is None:print(json.dumps(windows(),ensure_ascii=False,indent=2));return
    candidates=windows()
    if a.hwnd not in [w['hwnd'] for w in candidates]:raise RuntimeError('目标句柄不属于已识别游戏窗口')
    before=observe()
    c=Win32Controller(a.hwnd,getattr(Capture,a.method),getattr(Input,a.input),getattr(Input,a.input))
    c.set_screenshot_use_raw_size(True)
    if not c.post_connection().wait().succeeded:raise RuntimeError('Maa窗口连接失败')
    if not c.post_screencap().wait().succeeded:raise RuntimeError('截图失败')
    img=c.cached_image.copy()
    path=folder/(a.output+'-before.png');Image.fromarray(img[:,:,::-1]).save(path)
    click_ok=None
    if a.click:
        x,y=a.click
        if not 0<=x<img.shape[1] or not 0<=y<img.shape[0]:raise RuntimeError('点击坐标越界')
        if a.direct_target:
            if a.direct_target not in [w['hwnd'] for w in candidates]:raise RuntimeError('输入目标不属于游戏')
            # Coordinates supplied in the destination window's client coordinate space.
            old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(a.direct_target))
            try:
                lp=(y<<16)|(x&0xffff)
                click_ok=bool(u.PostMessageW(a.direct_target,0x200,0,lp))
                click_ok=bool(u.PostMessageW(a.direct_target,0x201,1,lp)) and click_ok
                time.sleep(.1)
                click_ok=bool(u.PostMessageW(a.direct_target,0x202,0,lp)) and click_ok
            finally:u.SetThreadDpiAwarenessContext(old)
        else:click_ok=c.post_click(x,y).wait().succeeded
        time.sleep(2)
        if not c.post_screencap().wait().succeeded:raise RuntimeError('点击后截图失败')
        Image.fromarray(c.cached_image[:,:,::-1]).save(folder/(a.output+'-after.png'))
    after=observe()
    result={'hwnd':a.hwnd,'directTarget':a.direct_target,'method':a.method,'input':a.input,'size':[img.shape[1],img.shape[0]],'imageStd':float(img.std()),'before':before,'after':after,'foregroundUnchanged':before['foreground']==after['foreground'],'cursorUnchanged':before['cursor']==after['cursor'],'clickDelivered':click_ok,'targetMinimized':bool(u.IsIconic(a.hwnd)),'capture':str(path)}
    (folder/(a.output+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
