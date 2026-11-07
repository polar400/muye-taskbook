"""Read-only inspection of pointer API imports in this game's render process."""
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow,u


from arena_pointer_pe import Module,imports


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('Expected one game window')
    w=BackgroundWindow(windows[0][0]);pid=W.DWORD()
    u.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)];u.GetWindowThreadProcessId.restype=W.DWORD
    u.GetWindowThreadProcessId(w.target,ctypes.byref(pid))
    k=ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Module32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(Module)];k.Module32FirstW.restype=W.BOOL
    k.Module32NextW.argtypes=[W.HANDLE,ctypes.POINTER(Module)];k.Module32NextW.restype=W.BOOL
    k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
    snapshot=k.CreateToolhelp32Snapshot(0x18,pid.value)
    if snapshot==ctypes.c_void_p(-1).value:raise RuntimeError('Module snapshot failed')
    row=Module();row.dwSize=ctypes.sizeof(row);modules=[]
    try:
        ok=k.Module32FirstW(snapshot,ctypes.byref(row))
        while ok:
            path=row.szExePath
            if path and not path.lower().startswith('c:\\windows\\'):
                try:
                    machine,found=imports(path)
                    modules.append(dict(name=row.szModule,path=path,base=row.modBaseAddr,machine=machine,imports=found))
                except (OSError,ValueError,struct.error) as error:modules.append(dict(name=row.szModule,error=str(error)))
            ok=k.Module32NextW(snapshot,ctypes.byref(row))
    finally:k.CloseHandle(snapshot)
    report=dict(root=w.root,target=int(w.target),pid=pid.value,readOnly=True,gameInputs=0,modules=modules)
    out=ROOT/'verification/arena-pointer-imports-20261020.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
