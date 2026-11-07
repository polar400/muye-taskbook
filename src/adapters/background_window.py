"""Capture one game window and deliver messages to its render child only."""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'vendor'))
from maa.controller import Win32Controller
from maa.define import MaaWin32ScreencapMethodEnum as Capture, MaaWin32InputMethodEnum as Input
from PIL import Image

u=ctypes.windll.user32
class WindowPlacement(ctypes.Structure):
    _fields_=[('length',W.UINT),('flags',W.UINT),('showCmd',W.UINT),
              ('ptMinPosition',W.POINT),('ptMaxPosition',W.POINT),('rcNormalPosition',W.RECT)]

class MonitorInfo(ctypes.Structure):
    _fields_=[('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('dwFlags',W.DWORD)]

u.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];u.MonitorFromWindow.restype=W.HANDLE
u.GetMonitorInfoW.argtypes=[W.HANDLE,ctypes.POINTER(MonitorInfo)];u.GetMonitorInfoW.restype=W.BOOL

def centered_window_position(bounds,size):
    left,top,right,bottom=bounds;width,height=size
    if right<=left or bottom<=top or min(width,height)<=0:raise RuntimeError('校准显示器区域无效')
    # Preserve the OCR canvas even on a smaller monitor; never change display mode.
    return left+(right-left-width)//2,top+(bottom-top-height)//2

u.IsZoomed.argtypes=[W.HWND];u.IsZoomed.restype=W.BOOL
u.GetWindowPlacement.argtypes=[W.HWND,ctypes.POINTER(WindowPlacement)];u.GetWindowPlacement.restype=W.BOOL
u.SetWindowPlacement.argtypes=[W.HWND,ctypes.POINTER(WindowPlacement)];u.SetWindowPlacement.restype=W.BOOL
u.SetWindowPos.argtypes=[W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT]
u.SetWindowPos.restype=W.BOOL
for name,args,result in [
 ('IsWindow',[W.HWND],W.BOOL),('IsIconic',[W.HWND],W.BOOL),
 ('GetAncestor',[W.HWND,W.UINT],W.HWND),
 ('GetWindowRect',[W.HWND,ctypes.POINTER(W.RECT)],W.BOOL),
 ('GetClientRect',[W.HWND,ctypes.POINTER(W.RECT)],W.BOOL),
 ('ClientToScreen',[W.HWND,ctypes.POINTER(W.POINT)],W.BOOL),
 ('GetClassNameW',[W.HWND,W.LPWSTR,ctypes.c_int],ctypes.c_int),
 ('GetWindowDpiAwarenessContext',[W.HWND],ctypes.c_void_p),
 ('SetThreadDpiAwarenessContext',[ctypes.c_void_p],ctypes.c_void_p),
 ('PostMessageW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM],W.BOOL)]:
    f=getattr(u,name);f.argtypes=args;f.restype=result
u.SendMessageTimeoutW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,ctypes.POINTER(ctypes.c_size_t)]
u.SendMessageTimeoutW.restype=W.LPARAM

def client_to_message(x,y,physical_size,message_size):
    pw,ph=physical_size;mw,mh=message_size
    if min(pw,ph,mw,mh)<=0 or not (0<=x<pw and 0<=y<ph):raise RuntimeError('点击坐标超出游戏客户区')
    return min(mw-1,int(x*mw/pw)),min(mh-1,int(y*mh/ph))

class BackgroundWindow:
    def __init__(self,hwnd,input_method='SendMessage'):
        if input_method not in ('PostMessage','SendMessage'):raise RuntimeError('后台输入方式无效')
        self.input_method=input_method
        self.root=int(hwnd);self.check()
        from app import game_windows
        if self.root not in [h for h,_ in game_windows()]:raise RuntimeError('窗口不属于360火影忍者游戏')
        children=[]
        def visit(h,_):
            text=ctypes.create_unicode_buffer(256);u.GetClassNameW(h,text,256)
            if text.value=='NativeWindowClass':children.append(h)
            return True
        cb=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)(visit)
        u.EnumChildWindows(self.root,cb,0)
        if len(children)!=1:raise RuntimeError('无法唯一定位游戏渲染窗口，请只保留一个游戏标签')
        self.target=children[0]
        self.controller=Win32Controller(self.root,Capture.FramePool,Input.PostMessage,Input.PostMessage)
        self.controller.set_screenshot_use_raw_size(True)
        if not self.controller.post_connection().wait().succeeded:raise RuntimeError('后台截图连接失败')
        self.geometry=None

    def check(self):
        if not u.IsWindow(self.root):raise RuntimeError('游戏窗口已关闭')
        if u.IsIconic(self.root):raise RuntimeError('游戏已最小化：请恢复窗口后重新开始；允许被其他窗口遮挡')
        if hasattr(self,'target') and (not u.IsWindow(self.target) or u.GetAncestor(self.target,2)!=self.root):
            raise RuntimeError('游戏渲染窗口已变化，请重新连接')

    def measure(self):
        root=W.RECT();r=W.RECT();p=W.POINT()
        u.GetWindowRect(self.root,ctypes.byref(root));u.GetClientRect(self.target,ctypes.byref(r))
        u.ClientToScreen(self.target,ctypes.byref(p))
        return (p.x-root.left,p.y-root.top,r.right,r.bottom,root.right-root.left,root.bottom-root.top)

    def calibration_bounds(self):
        monitor=u.MonitorFromWindow(self.root,2)  # nearest monitor, including negative origins
        info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
        if not monitor or not u.GetMonitorInfoW(monitor,ctypes.byref(info)):
            raise RuntimeError('无法读取游戏所在显示器，停止校准')
        rect=info.rcWork
        return rect.left,rect.top,rect.right,rect.bottom

    def calibrate(self,checkpoint=lambda:None,log=lambda message:None):
        """Normalize only the game window without activating it or moving the mouse."""
        target=(1920,1015)
        self.check();checkpoint()
        if u.IsZoomed(self.root):
            placement=WindowPlacement();placement.length=ctypes.sizeof(placement)
            if not u.GetWindowPlacement(self.root,ctypes.byref(placement)):raise RuntimeError('无法读取游戏窗口位置')
            placement.showCmd=4
            if not u.SetWindowPlacement(self.root,ctypes.byref(placement)):raise RuntimeError('无法恢复游戏窗口以校准尺寸')
            time.sleep(.2);self.check()
        samples=[];previous_axis=None;layout_reset=None
        for attempt in range(13):
            checkpoint();geometry=self.measure()
            if geometry[2:4]==target:
                time.sleep(.2);checkpoint()
                if self.measure()!=geometry:continue
                image=self.capture()
                if image.shape[:2]!=(target[1],target[0]):raise RuntimeError('启动校准截图尺寸不一致')
                log('启动校准通过：游戏区域1920×1015，保持后台操作')
                return image
            if attempt==12:break
            if attempt==1 and geometry[2]==target[0] and geometry[3]>target[1]:
                # 360's scrollbar layout is history-dependent: the same outer
                # size can leave an extra scrollbar-height in the render child.
                # Resize the ROOT wider, then restore its measured physical size
                # on the next step. Never resize/crop the render child itself.
                layout_reset=geometry[4:6]
                width=geometry[4]+geometry[3]-target[1];height=geometry[5]
                log('启动校准：重置滚动条布局，先扩宽根窗口再还原')
                samples=[];previous_axis=None
            elif attempt==2 and layout_reset is not None:
                width,height=layout_reset
                samples=[];previous_axis=None
            elif attempt<2 or (attempt==3 and layout_reset is not None):
                # Real 360 browser profiles: scrollbar-bearing layout (live
                # 2026-11-05) and the older borderless layout. Verify, never crop.
                width,height=(1920,1147) if attempt==0 else (1920,1122)
                samples=[];previous_axis=None
            else:
                # Height first: a short browser viewport creates a vertical scrollbar
                # and makes width look too small. Never compensate both axes at once.
                axis=1 if geometry[3]!=target[1] else 0
                if axis!=previous_axis:samples=[]
                previous_axis=axis
                outer=geometry[4+axis];client=geometry[2+axis];wanted=target[axis]
                samples.append((outer,client))
                lower=[v for v,c in samples if c<wanted];upper=[v for v,c in samples if c>wanted]
                if lower and upper and max(lower)<min(upper):
                    low,high=max(lower),min(upper)
                    if high-low<=1:raise RuntimeError('当前窗口布局无法达到目标游戏尺寸，停止校准')
                    size=(low+high)//2
                else:size=outer+wanted-client
                width,height=geometry[4:6]
                if axis:height=size
                else:width=size
                if min(width,height)<=0:raise RuntimeError('校准窗口尺寸无效')
            x,y=centered_window_position(self.calibration_bounds(),(width,height))
            log(f'启动校准：游戏区域{geometry[2]}×{geometry[3]}，居中设置外框{width}×{height}，位置({x},{y})')
            # Keep the other axis fixed while bracketing a discontinuous response.
            if not u.SetWindowPos(self.root,None,x,y,width,height,0x14):
                raise RuntimeError('无法调整游戏窗口尺寸')
            for _ in range(15):checkpoint();time.sleep(.1)
            self.check()
        raise RuntimeError('启动校准未达到1920×1015，停止后续任务')

    def capture(self):
        self.check();before=self.measure()
        if not self.controller.post_screencap().wait().succeeded:raise RuntimeError('后台截图失败')
        self.check()
        if before!=self.measure():raise RuntimeError('截图期间窗口位置或尺寸变化，请重新开始')
        img=self.controller.cached_image
        if img is None:raise RuntimeError('后台截图为空')
        x,y,w,h,rw,rh=before
        if abs(img.shape[1]-rw)>3 or abs(img.shape[0]-rh)>3:raise RuntimeError('截图尺寸与窗口不一致，停止点击')
        if min(w,h)<200 or x<0 or y<0 or x+w>img.shape[1] or y+h>img.shape[0]:raise RuntimeError('游戏截图区域无效')
        self.geometry=before
        image=img[y:y+h,x:x+w].copy()
        if image.std()<5:raise RuntimeError('游戏截图为黑屏或未加载')
        return image

    def click(self,x,y):
        self.check()
        if self.geometry is None or self.geometry!=self.measure():raise RuntimeError('窗口尺寸变化，请重新识别后再点击')
        w,h=self.geometry[2:4]
        old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(self.target))
        try:
            r=W.RECT();u.GetClientRect(self.target,ctypes.byref(r))
            mx,my=client_to_message(x,y,(w,h),(r.right,r.bottom))
            lp=(my<<16)|(mx&0xffff)
            def send(message,value):
                if self.input_method=='PostMessage':return u.PostMessageW(self.target,message,value,lp)
                result=ctypes.c_size_t()
                return u.SendMessageTimeoutW(self.target,message,value,lp,2,1000,ctypes.byref(result))
            if not send(0x200,0):raise RuntimeError('后台鼠标消息发送失败')
            if not send(0x201,1):raise RuntimeError('后台按下消息发送失败')
            time.sleep(.08)
            if not send(0x202,0):raise RuntimeError('后台释放消息发送失败')
        finally:u.SetThreadDpiAwarenessContext(old)

    def hold(self,x,y,seconds=.35,cancelled=lambda:False):
        """Bounded background hold. Always attempt release after a down attempt."""
        if isinstance(seconds,bool) or not .1<=seconds<=1:
            raise ValueError('长按时间须为0.1至1秒')
        self.check()
        if cancelled():return False
        geometry=self.geometry
        if geometry is None or geometry!=self.measure():raise RuntimeError('长按前窗口尺寸变化')
        old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(self.target))
        attempted=False
        try:
            r=W.RECT();u.GetClientRect(self.target,ctypes.byref(r))
            mx,my=client_to_message(x,y,geometry[2:4],(r.right,r.bottom))
            lp=(my<<16)|(mx&0xffff)
            def send(message,value):
                if self.input_method=='PostMessage':return u.PostMessageW(self.target,message,value,lp)
                result=ctypes.c_size_t()
                return u.SendMessageTimeoutW(self.target,message,value,lp,2,1000,ctypes.byref(result))
            if not send(0x200,0):raise RuntimeError('长按移动消息失败')
            attempted=True
            if not send(0x201,1):raise RuntimeError('长按按下结果不确定')
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if cancelled():return False
                self.check()
                # Compare geometry in the same DPI context used by capture and
                # the pre-hold check, not the target's message-coordinate context.
                message_context=u.SetThreadDpiAwarenessContext(old)
                try:current_geometry=self.measure()
                finally:u.SetThreadDpiAwarenessContext(message_context)
                if current_geometry!=geometry:raise RuntimeError('长按期间窗口变化')
                time.sleep(min(.05,max(0,deadline-time.monotonic())))
            return True
        finally:
            try:
                if attempted and not send(0x202,0):raise RuntimeError('长按释放消息失败，停止运行')
            finally:u.SetThreadDpiAwarenessContext(old)

    def hover(self,x,y):
        """Move the target window's virtual pointer; send no button messages."""
        self.check()
        if self.geometry is None or self.geometry!=self.measure():raise RuntimeError('窗口尺寸变化，请重新识别后再悬停')
        w,h=self.geometry[2:4]
        old=u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(self.target))
        try:
            r=W.RECT();u.GetClientRect(self.target,ctypes.byref(r))
            mx,my=client_to_message(x,y,(w,h),(r.right,r.bottom))
            lp=(my<<16)|(mx&0xffff)
            if self.input_method=='PostMessage':ok=u.PostMessageW(self.target,0x200,0,lp)
            else:
                result=ctypes.c_size_t()
                ok=u.SendMessageTimeoutW(self.target,0x200,0,lp,2,1000,ctypes.byref(result))
            if not ok:raise RuntimeError('后台悬停消息发送失败')
        finally:u.SetThreadDpiAwarenessContext(old)

    def save(self,image,path):Image.fromarray(image[:,:,::-1]).save(path)
