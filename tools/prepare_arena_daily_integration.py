"""Prepare, never apply, the two shared changes required by arena daily tasks."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def proposals():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    revised=app
    for old,new in (
        ("        self.ranked_server = tk.StringVar(value='连服')",
         "        self.arena_mode = tk.StringVar(value='休闲战斗')\n        self.ranked_server = tk.StringVar(value='连服')"),
        ("            server=cfg.get('rankedServer','连服')",
         "            self.arena_mode.set(cfg.get('arenaMode','休闲战斗'))\n            server=cfg.get('rankedServer','连服')"),
        ("                    rankedServer=self.ranked_server.get(),rankedLimit=ranked_limit,",
         "                    arenaMode=self.arena_mode.get(),\n                    rankedServer=self.ranked_server.get(),rankedLimit=ranked_limit,")):
        if revised.count(old)!=1:raise RuntimeError('app.py已变化，请重新核对接入位置')
        revised=revised.replace(old,new,1)
    source=(ROOT/'adapters/background_window.py').read_text(encoding='utf-8')
    marker='    def save(self,image,path):'
    if source.count(marker)!=1 or '    def hover(' in source:raise RuntimeError('悬停接口已变化，请重新核对')
    method='''    def hover(self,x,y):
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

'''
    return {'app.py':(app,revised),'adapters/background_window.py':(source,source.replace(marker,method+marker,1))}


if __name__=='__main__':
    sources=proposals()
    for name,(_,after) in sources.items():compile(after,name,'exec')
    folder=ROOT/'verification'
    (folder/'arena-daily-shared.patch').write_text(''.join(''.join(difflib.unified_diff(
        before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
        for name,(before,after) in sources.items()),encoding='utf-8')
    (folder/'arena-daily-shared.json').write_text(json.dumps({name:dict(
        beforeSha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),
        proposedTextSha256Lf=hashlib.sha256(after.encode('utf-8')).hexdigest())
        for name,(_,after) in sources.items()},indent=2),encoding='utf-8')
    print('Two proposed shared files compile; patch prepared, not applied')
