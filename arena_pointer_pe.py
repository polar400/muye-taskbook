"""Read-only PE import helpers for arena render-process diagnostics."""
import ctypes
from ctypes import wintypes as W
import struct

class Module(ctypes.Structure):
    _fields_=[('dwSize',W.DWORD),('th32ModuleID',W.DWORD),('th32ProcessID',W.DWORD),
              ('GlblcntUsage',W.DWORD),('ProccntUsage',W.DWORD),('modBaseAddr',ctypes.c_void_p),
              ('modBaseSize',W.DWORD),('hModule',W.HMODULE),('szModule',W.WCHAR*256),('szExePath',W.WCHAR*260)]


def imports(path):
    wanted={'GetCursorPos','GetPhysicalCursorPos','GetMessagePos','WindowFromPoint','GetProcAddress','GetTickCount'}
    with open(path,'rb') as f:
        f.seek(60);pe=struct.unpack('<I',f.read(4))[0];f.seek(pe);header=f.read(24)
        if header[:4]!=b'PE\0\0':raise ValueError('Invalid PE file')
        machine,sections=struct.unpack_from('<HH',header,4);size=struct.unpack_from('<H',header,20)[0]
        optional=f.read(size);magic=struct.unpack_from('<H',optional)[0]
        width=4 if magic==0x10b else 8;directory=96 if width==4 else 112
        import_rva=struct.unpack_from('<I',optional,directory+8)[0];mapping=[]
        for _ in range(sections):
            row=f.read(40);virtual_size,virtual,raw_size,raw=struct.unpack_from('<IIII',row,8)
            mapping.append((virtual,max(virtual_size,raw_size),raw))
        def read(rva,size):
            section=next((s for s in mapping if s[0]<=rva<s[0]+s[1]),None)
            if section is None:return b''
            f.seek(section[2]+rva-section[0]);return f.read(size)
        found=[]
        if not import_rva:return machine,found
        for index in range(256):
            raw=read(import_rva+index*20,20)
            if len(raw)!=20:break
            original,stamp,chain,name,iat=struct.unpack('<IIIII',raw)
            if not (original or name or iat):break
            library=read(name,128).split(b'\0')[0].decode('ascii',errors='replace')
            if not original:continue
            for n in range(4096):
                raw=read(original+n*width,width)
                if len(raw)!=width:break
                value=int.from_bytes(raw,'little')
                if not value:break
                if value>>(width*8-1):continue
                name=read(value+2,128).split(b'\0')[0].decode('ascii',errors='replace')
                if name in wanted:found.append(dict(library=library,name=name,iatRva=iat+n*width,width=width))
        return machine,found

