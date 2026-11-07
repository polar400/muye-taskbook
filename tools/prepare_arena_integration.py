"""Prepare reviewable shared-file changes; never apply them automatically."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def proposed_sources():
    result={}
    def change(path,edits):
        source=(ROOT/path).read_text(encoding='utf-8')
        revised=source
        for before,after in edits:
            if revised.count(before)!=1:raise RuntimeError('共享文件已变化，请重新协调：'+path)
            revised=revised.replace(before,after,1)
        result[path]=(source,revised)
    change('resources/tasks.json',[
        ('    {"id":"escort","label":"押镖（接取）","entry":"Escort"}',
         '    {"id":"escort","label":"押镖（接取）","entry":"Escort"},\n    {"id":"arena","label":"竞技场","entry":"Arena"}'),
        ('    "Wanted":', '    "Arena":{"action":{"type":"Custom","handler":"arena"},"next":["Complete"]},\n    "Wanted":')])
    change('app.py',[
        ('from wanted_task_ui import show_wanted_task',
         'from wanted_task_ui import show_wanted_task\nfrom arena_task_ui import show_arena_task\nfrom arena_task import validate_arena_config'),
        ("        if key=='wanted':", "        if key=='arena':\n            show_arena_task(self,mode)\n            return\n        if key=='wanted':"),
        ("            local=cfg['backend']=='本地后台（免API）' or diagnostic",
         "            if not diagnostic:validate_arena_config(cfg)\n            local=cfg['backend']=='本地后台（免API）' or diagnostic")])
    change('native_worker.py',[
        ('from ranked_pipeline import run_ranked_pipeline',
         'from ranked_pipeline import run_ranked_pipeline\nfrom arena_task import run_arena, validate_arena_config'),
        ("    if 'survival' in cfg['tasks'] and not cfg.get('diagnostic'):survival_plan(cfg)",
         "    if not cfg.get('diagnostic'):validate_arena_config(cfg)\n    if 'survival' in cfg['tasks'] and not cfg.get('diagnostic'):survival_plan(cfg)"),
        ("        try:result=run_ranked_pipeline(flow) if task=='ranked' else flow.run(task)",
         "        try:result=run_arena(flow) if task=='arena' else run_ranked_pipeline(flow) if task=='ranked' else flow.run(task)"),
        ("tasks[task]+('：已接取，交付流程待补充' if accepted",
         "tasks[task]+('：竞技场界面已打开（本阶段目标）' if task=='arena' and result=='opened' else '：已接取，交付流程待补充' if accepted")])
    return result


if __name__=='__main__':
    sources=proposed_sources()
    output=ROOT/'verification/arena-shared-integration.patch'
    output.write_text(''.join(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                      fromfile='a/'+path,tofile='b/'+path)) for path,(before,after) in sources.items()),encoding='utf-8')
    (output.with_suffix('.json')).write_text(json.dumps({path:dict(
        beforeSha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
        proposedTextSha256Lf=hashlib.sha256(after.encode('utf-8')).hexdigest())
        for path,(_,after) in sources.items()},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared; shared files untouched:',output)
