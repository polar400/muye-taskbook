"""Authorized live acceptance via native_worker, capped at one challenge.

Requires --execute-one-round. Uses existing background IO; never changes config,
does not buy attempts, and never retries an input whose result is uncertain.
"""
import ctypes
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import threading
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import game_windows
import native_worker as worker
from adapters.background_window import BackgroundWindow


def digest(p):return sha256(p.read_bytes()).hexdigest()


def main():
    if sys.argv[1:]!=['--execute-one-round']:
        raise SystemExit('实机验收需明确传入 --execute-one-round；请先获得用户授权')
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows=game_windows()
    if len(windows)!=1:raise RuntimeError('实机验收要求唯一且未最小化的游戏窗口')
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    folder=ROOT/'verification'/('ranked-live-'+stamp)
    folder.mkdir(exist_ok=False)
    cfg_hash={name:digest(ROOT/name) for name in ('config.json','run.json')}
    cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    cfg.update(tasks=['ranked'],rankedLimit=1,gameHwnd=windows[0][0],
               runId=stamp+'-ranked-acceptance',preview=False,diagnostic=False)
    snapshot=folder/'run.json'
    snapshot.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    last=ROOT/'verification/background-latest.png'
    if last.exists():shutil.copy2(last,folder/'previous-background-latest.png')
    events=[];inputs=[];node=['startup'];attempted=[0]
    lock=threading.Lock()
    original_emit=worker.emit
    def persist(name,data):
        (folder/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def emit(kind,message,**extra):
        with lock:
            events.append(dict(at=datetime.now(timezone.utc).isoformat(),kind=kind,message=message,**extra))
            if kind=='node' and extra.get('id')=='ranked':node[0]=extra.get('node','unknown')
            persist('events.json',events)
        original_emit(kind,message,**extra)
    class AuditWindow(BackgroundWindow):
        def click(self,x,y):
            if node[0]=='challenge':
                if attempted[0]>=1:raise RuntimeError('实机验收已发起过一场挑战，禁止第二次发送')
                attempted[0]+=1  # Persist BEFORE sending: uncertain sends are spent.
            entry=dict(node=node[0],point=[int(x),int(y)],status='attempting')
            inputs.append(entry);persist('inputs.json',inputs)
            if worker.flow is not None and worker.flow.image is not None:
                self.save(worker.flow.image,folder/f'input-{len(inputs):02d}-{node[0]}.png')
            try:
                result=super().click(x,y)
            except Exception:
                entry['status']='uncertain_or_failed';persist('inputs.json',inputs);raise
            entry['status']='sent';persist('inputs.json',inputs)
            return result
    worker.emit=emit;worker.BackgroundWindow=AuditWindow
    error=None
    sys.argv=['native_worker.py',str(snapshot)]
    threading.Thread(target=worker.commands,daemon=True).start()
    try:
        worker.main()
    except Exception as exc:
        error=str(exc)
        (folder/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        worker.report_error(exc)
    finally:
        if worker.flow is not None and worker.flow.image is not None:
            worker.window.save(worker.flow.image,folder/'final.png')
        assert all(digest(ROOT/name)==h for name,h in cfg_hash.items()),'用户配置／run.json发生变化'
    challenges=[a for a in events if a.get('node')=='challenge']
    finishes=[a for a in events if a.get('node')=='finish' and a.get('status')=='done']
    before=challenges[0].get('remaining') if challenges else None
    after=finishes[-1].get('remaining') if finishes else None
    passed=(error is None and attempted[0]==1 and before is not None and
            after==before-1 and finishes and finishes[-1].get('completed')==1)
    results=[a['message'] for a in events if a['message'].startswith('排位战结算：')]
    report=dict(status='passed' if passed else 'failed',error=error,
        challengeAttempts=attempted[0],before=before,after=after,results=results,
        endClickAttempts=sum(a['node']=='end_battle' for a in inputs),
        completed=finishes[-1].get('completed') if finishes else 0,
        homeConfirmed=bool(finishes),configUnchanged=True,evidenceFolder=str(folder))
    persist('report.json',report)
    print('LIVE_ACCEPTANCE '+json.dumps(report,ensure_ascii=False),flush=True)
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
