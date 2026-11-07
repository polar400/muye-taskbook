"""Grocery-only continuous arrow holds. Shared input duration limits stay intact."""
from contextlib import contextmanager
import ctypes
import time

SCROLL_SECONDS = 1.6
ARROW_POINTS = {'up': (1567, 145), 'down': (1567, 899)}
ARROW_BOXES = {'up': (1551, 127, 33, 35), 'down': (1551, 880, 33, 35)}


@contextmanager
def _native_transport(window, point):
    from adapters.background_window import u, W, client_to_message
    old = u.SetThreadDpiAwarenessContext(u.GetWindowDpiAwarenessContext(window.target))
    try:
        rect = W.RECT()
        if not u.GetClientRect(window.target, ctypes.byref(rect)):
            raise RuntimeError('无法读取杂货屋窗口客户区')
        mx, my = client_to_message(*point, window.geometry[2:4], (rect.right, rect.bottom))
        packed = (my << 16) | (mx & 0xffff)

        def send(message, value):
            if window.input_method == 'PostMessage':
                return u.PostMessageW(window.target, message, value, packed)
            result = ctypes.c_size_t()
            return u.SendMessageTimeoutW(window.target, message, value, packed, 2, 1000, ctypes.byref(result))

        def measure():
            message_context = u.SetThreadDpiAwarenessContext(old)
            try:
                return window.measure()
            finally:
                u.SetThreadDpiAwarenessContext(message_context)

        yield send, measure
    finally:
        u.SetThreadDpiAwarenessContext(old)


def scroll_once(window, direction, *, cancelled=lambda: False,
                _transport=None, _clock=None, _sleep=None):
    """Hold one verified grocery arrow continuously for 1.6 seconds.

    Caller must first capture and verify the shop/arrow position. No screen
    capture or page selection is inferred here. Returns False on cancellation.
    """
    if direction not in ARROW_POINTS:
        raise ValueError('杂货屋滚动方向须为up或down')
    window.check()
    if cancelled():
        return False
    geometry = window.geometry
    if geometry is None or geometry[2:4] != (1920, 1015) or geometry != window.measure():
        raise RuntimeError('杂货屋滚动前窗口尺寸或位置变化')
    transport = _native_transport if _transport is None else _transport
    clock = time.monotonic if _clock is None else _clock
    sleep = time.sleep if _sleep is None else _sleep
    with transport(window, ARROW_POINTS[direction]) as (send, measure):
        attempted = False
        try:
            if not send(0x200, 0):
                raise RuntimeError('杂货屋滚动移动消息失败')
            attempted = True
            if not send(0x201, 1):
                raise RuntimeError('杂货屋滚动按下结果不确定')
            deadline = clock() + SCROLL_SECONDS
            while True:
                remaining = deadline - clock()
                if remaining <= 0:
                    return True
                if cancelled():
                    return False
                window.check()
                if measure() != geometry:
                    raise RuntimeError('杂货屋滚动期间窗口变化')
                sleep(min(.05, remaining))
        finally:
            if attempted and not send(0x202, 0):
                raise RuntimeError('杂货屋滚动释放消息失败，停止运行')


def drag_thumb(window, start_y, end_y, *, cancelled=lambda:False,
               _transport=None, _clock=None, _sleep=None):
    """Drag an independently located scrollbar thumb for a continuous 1.6s."""
    transport=_native_transport if _transport is None else _transport
    clock=time.monotonic if _clock is None else _clock
    sleep=time.sleep if _sleep is None else _sleep
    if not (175<=start_y<=866 and 175<=end_y<=866): raise ValueError('滑块坐标越界')
    if cancelled(): return False
    window.check()
    geometry=window.geometry
    if geometry is None or geometry[2:4]!=(1920,1015) or window.measure()!=geometry:
        raise RuntimeError('拖动前窗口变化')
    point=(1567,int(start_y));pressed=False
    try:
        with transport(window,point) as (send,measure):
            if not send(0x200,0): raise RuntimeError('滑块定位失败')
            pressed=True
            if not send(0x201,1): raise RuntimeError('滑块按下结果不确定')
        started=clock()
        while True:
            if cancelled(): return False
            elapsed=clock()-started
            point=(1567,round(start_y+(end_y-start_y)*min(1,elapsed/SCROLL_SECONDS)))
            with transport(window,point) as (send,measure):
                if measure()!=geometry: raise RuntimeError('拖动期间窗口变化')
                if not send(0x200,1): raise RuntimeError('滑块移动结果不确定')
            if elapsed>=SCROLL_SECONDS: return True
            sleep(min(.05,SCROLL_SECONDS-elapsed))
    finally:
        if pressed:
            with transport(window,point) as (send,measure):
                if not send(0x202,0): raise RuntimeError('滑块释放消息失败')
