"""Verify auto-path presence/absence and wanted completion on saved pixels only."""
from pathlib import Path
from datetime import datetime
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)];sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from wanted_task import WantedTask
from PIL import Image
import numpy as np


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    paths=[ROOT/p for p in ('app.py','mission_desk_ui.py','config.json','run.json','logs/2026-10-19.log',
                           'local_flows.py','native_worker.py','ranked_numbers.py','resources/tasks.json',
                           'resources/local/ranked_numbers/bank.json')]
    paths+=list((ROOT/'resources/local/image').glob('*.png'))
    paths+=list((ROOT/'resources/local/wanted').glob('*.png'))
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def main():
    before=protected();ocr=LocalOCR();frames=[]
    for filename,expected in (('autopath-home-game.png',True),('idle-home-game.png',False)):
        path=ROOT/'resources/local/wanted'/filename
        image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock());flow.image=image;flow.items=ocr.read(image)
        task=WantedTask(flow);matches=task.matches('wanted_autopath',(.36,.08,.6,.2))
        visible=task.autopath_visible();assert visible==expected
        frames.append({'path':str(path.relative_to(ROOT)),'sha256':digest(path),'expectedAutopath':expected,
                       'autopathVisible':visible,'templateMatches':matches,
                       'localOCR':ocr.read(image[81:203,691:1152])})
        flow.window.click.assert_not_called()
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m','unittest','tests_wanted','tests_wanted_idle']
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    changed=[p for p,sha in before.items() if digest(ROOT/p)!=sha]
    assert not changed,changed
    sources=['wanted_task.py','wanted_task_ui.py','tests_wanted_idle.py',
             'tools/prepare_wanted_autopath.py','tools/verify_wanted_autopath.py']
    for filename in sources:ast.parse((ROOT/filename).read_text(encoding='utf-8'))
    output=result.stdout+result.stderr;match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    report={'generatedAt':datetime.now().astimezone().isoformat(),'mode':'offline, mock game IO','actualGameInputs':0,
            'frames':frames,'manifest':'resources/local/wanted/autopath-sources.json',
            'manifestSha256':digest(ROOT/'resources/local/wanted/autopath-sources.json'),
            'rules':{'requiresThisRunAutoConfirmation':True,'homeRequired':True,'secondsWithoutAutopath':10,
                     'minimumObservations':3,'pauseExcluded':True,'templateThreshold':.9,'roi':[.36,.08,.6,.2],
                     'retainedGuards':['stable scene','quest panel without wanted/auto','no central dialog'],
                     'initialHomeIsNotCompletion':True,'originalZeroAndMissingActivityRoutesRetained':True},
            'beforeFix':{'command':'python -X utf8 -X faulthandler -B -m unittest tests_wanted_idle.WantedIdleTests.test_real_autopath_art_cannot_finish_even_when_ocr_misses_it_and_scene_is_static tests_wanted_idle.WantedIdleTests.test_autopath_reappearance_resets_the_whole_ten_second_window',
                         'tests':2,'failures':2,'seconds':1.184,'exitCode':1,
                         'failure':'Old static-home timer could finish with the auto-path banner still present; banner reappearance did not reset it.'},
            'command':command,'exitCode':result.returncode,'output':output,
            'tests':int(match[1]) if match else None,'seconds':float(match[2]) if match else None,
            'protectedBefore':before,'protectedChanged':changed,'syntaxParsed':sources,
            'sourceHashes':{p:digest(ROOT/p) for p in sources},'runtimeTemplatesAdded':1,
            'limitations':['Only supplied calibrated appearance and local ROI validated, not all future renderings.',
                           'No live game input; UI helper wording parsed, no desktop visual acceptance claimed.']}
    path=ROOT/'verification/wanted-autopath-completion-20261019.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(path),'tests':report['tests'],'exitCode':result.returncode,
                      'positiveMatchScore':frames[0]['templateMatches'][0]['score']},ensure_ascii=False),flush=True)
    print(output,flush=True)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
