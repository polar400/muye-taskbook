"""Offline wanted layout verification, source audit and targeted regression."""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from wanted_task import WantedTask
from PIL import Image
import numpy as np


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    manifest=json.loads((ROOT/'resources/local/wanted/completed-activity-layout-20261019.json').read_text(encoding='utf-8'))
    ocr=LocalOCR();frames=[]
    for source in manifest['sources']:
        flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock())
        flow.image=np.array(Image.open(ROOT/source['path']).convert('RGB'))[:,:,::-1].copy()
        flow.items=ocr.read(flow.image);task=WantedTask(flow)
        frames.append(dict(source,layoutMatches=task.matches('wanted_daily_completed_rows',(.14,.3,.3,.49)),
                           close=task.completed_activity_close(),wantedRow=task.button('wanted_row',(.14,.16,.3,.74))))
        assert frames[-1]['close'] and frames[-1]['wantedRow'] is None
        flow.window.click.assert_not_called()
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m','unittest',
             'tests_wanted','tests_wanted_idle','tests_wanted_activity_layout']
    result=subprocess.run(command,cwd=ROOT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                          capture_output=True,text=True,encoding='utf-8')
    output=result.stdout+result.stderr;match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    baseline=json.loads((ROOT/'verification/wanted-activity-layout-before-20261019.json').read_text(encoding='utf-8'))
    changed=[p for p,sha in baseline.items() if digest(ROOT/p)!=sha]
    assert not changed,changed
    syntax=['tests_wanted_activity_layout.py','tools/prepare_wanted_activity_layout.py','tools/verify_wanted_activity_layout.py']
    for name in syntax:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    report={'generatedAt':datetime.now().astimezone().isoformat(),'mode':'offline saved pixels and mock IO',
            'actualGameInputs':0,'rootCause':'Completed Strong row disappeared; old Strong/Quiz layout did not match Quiz/Login.',
            'implementation':'Add one wanted_daily_completed_rows template variant using existing loader; no runtime Python changed.',
            'frames':frames,'command':command,'exitCode':result.returncode,'output':output,
            'tests':int(match[1]) if match else None,'seconds':float(match[2]) if match else None,
            'beforeFix':{'tests':1,'failedSubcases':3,'outputFile':'verification/wanted-activity-layout-red-20261019.txt'},
            'baselineFile':'verification/wanted-activity-layout-before-20261019.json',
            'baselineCount':len(baseline),'baselineChanged':changed,'syntaxParsed':syntax,
            'hashes':{name:digest(ROOT/name) for name in syntax+[manifest['asset']['path']]},
            'limitations':['No live game execution.','Covers saved calibrated list appearances; unknown layouts still stop.'],
            'retainedGuards':['two consecutive frames','daily tab','wanted template and text exclusion',
                              'wanted detail exclusion','central dialog exclusion','unique close','home after one close']}
    path=ROOT/'verification/wanted-activity-layout-20261019.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'verification/wanted-activity-layout-tests-20261019.txt').write_text(output,encoding='utf-8')
    print(json.dumps({'report':str(path),'tests':report['tests'],'seconds':report['seconds'],
                      'exitCode':result.returncode,'protectedFiles':len(baseline),'changed':changed,
                      'scores':[f['layoutMatches'][0]['score'] for f in frames]},ensure_ascii=False))
    print(output)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
