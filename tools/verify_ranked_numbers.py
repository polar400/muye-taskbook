"""Audit unified numeric reading on labelled archived frames. Never opens a game."""
from pathlib import Path
from datetime import datetime
import ast
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from tools.prepare_ranked_number_bank import SOURCES
from unittest.mock import Mock
from PIL import Image
import numpy as np

HOLDOUT=[
 ('出错任务/排位战/证据/ac3c382f3b9deeb677c9b8fb.png',[634467,674651,750130,962616,471398]),
 ('出错任务/排位战/证据/859054be011704e1a56a2121.png',[1109537,1007171,960878,1345437,690256]),
 ('出错任务/排位战/证据/2b3eeebbb2e4eafbc1a4271e.png',[718017,1498553,726435,1320372,774074]),
 ('resources/local/ranked-local-live.png',[618173,600720,776157,1589780,1250298]),
]
MODULES=['tests_ranked_numbers','tests_ranked_white_digits','tests_ranked','tests_ranked_battle',
         'tests_ranked_pipeline','tests_ranked_pipeline_images','tests_ranked_options','tests_wanted','tests_wanted_idle']
SOURCES_CODE=['ranked_numbers.py','local_flows.py','ranked_vision.py','ranked_pipeline.py','native_worker.py',
              'wanted_task.py','wanted_task_ui.py','tests_ranked_numbers.py','tests_ranked_white_digits.py',
              'tests_ranked.py','tests_wanted_idle.py','tools/prepare_ranked_number_bank.py',
              'tools/verify_ranked_numbers.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def preserved():
    names=['app.py','mission_desk_ui.py','config.json','run.json','resources/tasks.json','failure_archive.py',
           'logs/2026-10-19.log','resources/local/catalog/digits/index.json']
    paths=[ROOT/p for p in names]
    for folder in ('resources/local/image','resources/local/catalog/ranked/20261016-973-cross-ready',
                   '出错任务/排位战/证据'):
        paths.extend((ROOT/folder).glob('*.png'))
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def main():
    before=preserved();ocr=LocalOCR();samples=[];accepted=0
    bank=json.loads((ROOT/'resources/local/ranked_numbers/bank.json').read_text(encoding='utf-8'))
    assert min(bank['variantCounts'].values())>=2
    assert not {s['path'] for s in bank['sources']} & {p for p,_ in HOLDOUT}
    for split,group in (('bank_source',SOURCES),('held_out_frame',HOLDOUT)):
        for name,expected in group:
            image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
            flow=LocalFlows(Mock(),ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
            flow.image=image;flow.items=ocr.read(image)
            count,own,opponents=flow.ranked_state()
            assert [o['power'] for o in opponents]==expected,(name,expected,opponents)
            rows=flow.ranked_number_evidence['opponents']
            assert all(r['shape']['value']==value for r,value in zip(rows,expected))
            flow.window.click.assert_not_called()
            for row,value in zip(rows,expected):row['expected']=value
            samples.append({'split':split,'path':name,'sha256':digest(ROOT/name),
                            'remaining':count,'own':own,'opponents':rows})
            accepted+=len(opponents)
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m','unittest',*MODULES]
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    after=preserved();changed=[p for p,h in before.items() if after.get(p)!=h]
    assert not changed,changed
    for name in SOURCES_CODE:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    output=result.stdout+result.stderr
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    report={'generatedAt':datetime.now().astimezone().isoformat(),'mode':'offline only','actualGameInputs':0,
            'bank':'resources/local/ranked_numbers/bank.json','bankSha256':digest(ROOT/'resources/local/ranked_numbers/bank.json'),
            'variantCounts':bank['variantCounts'],'variants':len(bank['templates']),
            'bankSourceFrameCount':len(SOURCES),'heldOutFrameCount':len(HOLDOUT),
            'samples':samples,'accepted':accepted,'wrongAccepted':0,'qualifiedShapeCount':accepted,
            'command':command,'exitCode':result.returncode,'output':output,
            'tests':int(match[1]) if match else None,'seconds':float(match[2]) if match else None,
            'protectedBefore':before,'protectedChanged':changed,'syntaxParsed':SOURCES_CODE,
            'sourceHashes':{p:digest(ROOT/p) for p in SOURCES_CODE},
            'wanted':{'source':'resources/local/wanted/idle-home-sources.json','quietDecrementLog':True,
                      'stableHomeSeconds':10,'minimumObservations':3,'requiresAutoConfirmationThisRun':True,
                      'questPanelRequired':True,'activeWantedOrDialogOrMovementResets':True,
                      'nativeQueueContinuationTested':True},
            'flowEvidence':'Real Maa Tasker with archived numeric pixels/OCR and simulated game transitions/inputs; real victory/defeat button fixtures also tested.',
            'limitations':['Only calibrated 1920x1015 appearance tested; unknown/conflicting readings still stop.',
                           'Training/holdout split is by frame, not a claim of unseen-font validation.',
                           'No new live-game execution or current desktop visual acceptance.']}
    target=ROOT/'verification/ranked-unified-numbers-20261019.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'accepted':accepted,'wrongAccepted':0,
                      'variants':len(bank['templates']),'tests':report['tests'],'exitCode':result.returncode},ensure_ascii=False),flush=True)
    print(output,flush=True)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
