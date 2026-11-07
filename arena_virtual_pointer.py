"""Unapplied arena-only virtual-pointer prototype. Requires explicit authorization.

Temporarily replaces two Flash-module import pointers, never the system cursor.
No remote threads, executable-file edits, purchases, or mouse button messages.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import struct

from arena_pointer_pe import Module,imports
from adapters.background_window import client_to_message

ROOT=Path(__file__).resolve().parent


def pointer_stubs(x,y,hwnd,*,clock,started,original_cursor,original_hit):
    def expiry(original):
        # Unsigned elapsed time handles GetTickCount wraparound. After 5 seconds
        # tail-call the real API even if the Python probe was forcibly stopped.
        return (b'\xb8'+struct.pack('<I',clock)+b'\xff\xd0\x2d'+struct.pack('<I',started)+
                b'\x3d'+struct.pack('<I',5000)+b'\x72\x07\xb8'+struct.pack('<I',original)+b'\xff\xe0')
    # x86 stdcall GetCursorPos(PPOINT): preserve nonvolatile registers, handle NULL.
    cursor=(b'\x8b\x44\x24\x04\x85\xc0\x74\x15'+b'\xc7\x00'+struct.pack('<i',x)+
            b'\xc7\x40\x04'+struct.pack('<i',y)+b'\xb8\x01\x00\x00\x00\xc2\x04\x00'+
            b'\x31\xc0\xc2\x04\x00')
    # x86 stdcall WindowFromPoint(POINT): 8 argument bytes; target Flash HWND only.
    hit=b'\xb8'+struct.pack('<I',hwnd)+b'\xc2\x08\x00'
    return expiry(original_cursor)+cursor,expiry(original_hit)+hit


class PointerTransaction:
    """Restore all modified slots, including an uncertain write, on every exit."""
    def __init__(self,memory,entries):self.memory=memory;self.entries=entries;self.touched=[]

    def start(self):
        if self.touched:raise RuntimeError('虚拟鼠标入口已启用，拒绝重复启用')
        try:
            for address,original,replacement in self.entries:
                self.touched.append((address,original,replacement))
                self.memory.replace(address,original,replacement)
        except BaseException:
            self.stop();raise

    def stop(self):
        errors=[]
        for address,original,replacement in reversed(self.touched):
            try:
                current=self.memory.read(address,len(original))
                if current==original:continue
                if current!=replacement:raise RuntimeError('虚拟鼠标入口被其他代码改变，未覆盖')
                self.memory.replace(address,replacement,original)
            except Exception as error:errors.append(str(error))
        self.touched=[]
        if errors:raise RuntimeError('虚拟鼠标入口恢复失败：'+'；'.join(errors))

    def __enter__(self):self.start();return self
    def __exit__(self,*error):self.stop()


class RenderMemory:
    def __init__(self,pid):
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        for name,args,result in (
            ('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
            ('CloseHandle',[W.HANDLE],W.BOOL),
            ('ReadProcessMemory',[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)],W.BOOL),
            ('WriteProcessMemory',[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)],W.BOOL),
            ('VirtualProtectEx',[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t,W.DWORD,ctypes.POINTER(W.DWORD)],W.BOOL),
            ('VirtualAllocEx',[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t,W.DWORD,W.DWORD],ctypes.c_void_p),
            ('FlushInstructionCache',[W.HANDLE,ctypes.c_void_p,ctypes.c_size_t],W.BOOL)):
            fn=getattr(self.k,name);fn.argtypes=args;fn.restype=result
        self.handle=self.k.OpenProcess(0x1000|0x10|0x20|0x8,False,pid)
        if not self.handle:raise RuntimeError('无法打开游戏渲染进程，未修改入口')

    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None

    def read(self,address,size):
        buffer=ctypes.create_string_buffer(size);done=ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,address,buffer,size,ctypes.byref(done)) or done.value!=size:
            raise RuntimeError('游戏鼠标入口读取失败')
        return buffer.raw

    def write(self,address,data):
        buffer=ctypes.create_string_buffer(data);done=ctypes.c_size_t()
        if not self.k.WriteProcessMemory(self.handle,address,buffer,len(data),ctypes.byref(done)) or done.value!=len(data):
            raise RuntimeError('游戏虚拟鼠标写入结果不确定')

    def replace(self,address,expected,data):
        if self.read(address,len(data))!=expected:raise RuntimeError('游戏鼠标入口已变化，停止')
        protection=W.DWORD()
        if not self.k.VirtualProtectEx(self.handle,address,len(data),4,ctypes.byref(protection)):
            raise RuntimeError('游戏鼠标入口保护切换失败')
        try:
            self.write(address,data)
            if self.read(address,len(data))!=data:raise RuntimeError('游戏虚拟鼠标入口写入未确认')
        finally:
            ignored=W.DWORD()
            if not self.k.VirtualProtectEx(self.handle,address,len(data),protection.value,ctypes.byref(ignored)):
                raise RuntimeError('游戏鼠标入口保护恢复失败')

    def stubs(self,payload):
        address=self.k.VirtualAllocEx(self.handle,None,4096,0x3000,4)
        if not address or address>0xffffffff:raise RuntimeError('32位虚拟鼠标代码页分配失败')
        self.write(address,payload);old=W.DWORD()
        if not self.k.VirtualProtectEx(self.handle,address,4096,0x20,ctypes.byref(old)):
            raise RuntimeError('虚拟鼠标代码页保护失败')
        if not self.k.FlushInstructionCache(self.handle,address,len(payload)):
            raise RuntimeError('虚拟鼠标代码页同步失败')
        # Keep one 4KiB page until process exit: a thread may still be returning
        # from the old stub after its import slot has been restored.
        return address


class ArenaVirtualPointer:
    def __init__(self,window,*,purpose='hover'):
        files={'hover':'arena-virtual-pointer-authorization-20261020.json',
               'lower-once':'arena-lower-virtual-authorization-20261020.json'}
        if purpose not in files:raise ValueError('未知竞技场虚拟指针试验范围')
        authorization=ROOT/'verification'/files[purpose]
        auth=json.loads(authorization.read_text(encoding='utf-8')) if authorization.exists() else {}
        if (auth.get('decision')!='allowed_by_user' or auth.get('remaining')!=1
                or (purpose=='lower-once' and auth.get('scopeCode')!='arena-lower-confirm-once')):
            raise RuntimeError('尚未获准游戏渲染进程虚拟鼠标试验；未修改进程')
        window.check();self.window=window;self.memory=None;self.transaction=None;self.evidence={}
        self.u=ctypes.WinDLL('user32',use_last_error=True)
        for name,args,result in (
            ('GetWindowThreadProcessId',[W.HWND,ctypes.POINTER(W.DWORD)],W.DWORD),
            ('GetWindowDpiAwarenessContext',[W.HWND],ctypes.c_void_p),
            ('SetThreadDpiAwarenessContext',[ctypes.c_void_p],ctypes.c_void_p),
            ('GetClientRect',[W.HWND,ctypes.POINTER(W.RECT)],W.BOOL),
            ('ClientToScreen',[W.HWND,ctypes.POINTER(W.POINT)],W.BOOL)):
            fn=getattr(self.u,name);fn.argtypes=args;fn.restype=result

    def prepare(self,x,y):
        self.window.check();pid=W.DWORD();self.u.GetWindowThreadProcessId(self.window.target,ctypes.byref(pid))
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
        k.Module32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(Module)];k.Module32FirstW.restype=W.BOOL
        k.Module32NextW.argtypes=[W.HANDLE,ctypes.POINTER(Module)];k.Module32NextW.restype=W.BOOL
        k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
        snapshot=k.CreateToolhelp32Snapshot(0x18,pid.value)
        if snapshot==ctypes.c_void_p(-1).value:raise RuntimeError('无法核对游戏Flash模块')
        row=Module();row.dwSize=ctypes.sizeof(row);matches=[]
        try:
            ok=k.Module32FirstW(snapshot,ctypes.byref(row))
            while ok:
                if row.szModule.lower()=='npswf32_25_0_0_127.dll':
                    matches.append((row.szExePath,row.modBaseAddr,row.modBaseSize))
                ok=k.Module32NextW(snapshot,ctypes.byref(row))
        finally:k.CloseHandle(snapshot)
        matches=list(dict.fromkeys(matches))
        if len(matches)!=1:raise RuntimeError('当前只支持实测的唯一32位Flash模块；未修改入口')
        path,base,size=matches[0];machine,functions=imports(path)
        wanted={name:[f for f in functions if f['name']==name] for name in ('GetCursorPos','WindowFromPoint','GetTickCount')}
        if machine!=0x14c or any(len(rows)!=1 or rows[0]['width']!=4 for rows in wanted.values()):
            raise RuntimeError('Flash鼠标导入格式不符；未修改入口')
        if self.window.geometry is None or self.window.geometry!=self.window.measure():raise RuntimeError('窗口几何变化')
        old=self.u.SetThreadDpiAwarenessContext(self.u.GetWindowDpiAwarenessContext(self.window.target))
        try:
            rect=W.RECT();self.u.GetClientRect(self.window.target,ctypes.byref(rect))
            mx,my=client_to_message(x,y,self.window.geometry[2:4],(rect.right,rect.bottom))
            point=W.POINT(mx,my)
            if not self.u.ClientToScreen(self.window.target,ctypes.byref(point)):raise RuntimeError('无法核对虚拟鼠标坐标')
        finally:self.u.SetThreadDpiAwarenessContext(old)
        self.memory=RenderMemory(pid.value)
        try:
            originals={}
            for name in wanted:
                rva=wanted[name][0]['iatRva']
                if not 0<=rva<=size-4:raise RuntimeError('Flash导入指针越界')
                original=self.memory.read(base+rva,4)
                if int.from_bytes(original,'little')==0:raise RuntimeError('Flash导入指针为空')
                originals[name]=original
            k.GetTickCount.restype=W.DWORD
            cursor,hit=pointer_stubs(point.x,point.y,int(self.window.target),
                clock=int.from_bytes(originals['GetTickCount'],'little'),started=k.GetTickCount(),
                original_cursor=int.from_bytes(originals['GetCursorPos'],'little'),
                original_hit=int.from_bytes(originals['WindowFromPoint'],'little'))
            if len(cursor)>64:raise RuntimeError('虚拟鼠标代码布局异常')
            allocation=self.memory.stubs(cursor+b'\x90'*(64-len(cursor))+hit)
            entries=[]
            for name,offset in (('GetCursorPos',0),('WindowFromPoint',64)):
                rva=wanted[name][0]['iatRva']
                address=base+rva;original=originals[name]
                entries.append((address,original,struct.pack('<I',allocation+offset)))
            self.transaction=PointerTransaction(self.memory,entries)
            self.evidence=dict(pid=pid.value,module=path,screenLogical=[point.x,point.y],
                               point=[x,y],allocation=allocation,retainedBytes=4096,expiresAfterMs=5000,
                               entries=[dict(address=a,original=o.hex(),replacement=r.hex()) for a,o,r in entries])
        except BaseException:self.close();raise

    @contextmanager
    def override(self,x,y):
        if self.transaction is not None:raise RuntimeError('虚拟鼠标上下文不能重复使用')
        self.prepare(x,y)
        try:
            with self.transaction:yield self
        finally:self.close()

    def close(self):
        if self.memory:self.memory.close();self.memory=None
