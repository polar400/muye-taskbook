"""Audit saved serif digit pixels and run backend regressions. No game/window IO."""
from pathlib import Path
import ast
from datetime import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from ranked_vision import (read_white_power,white_digit_candidates,white_ink,
                           white_power_templates)

SAMPLES=[
    ('出错任务/排位战/证据/859054be011704e1a56a2121.png',[1109537,1007171,960878,1345437,690256]),
    ('出错任务/排位战/证据/45706e4f3dec2230d7449180.png',[1155227,752120,1066599,618173,769353]),
    ('resources/local/catalog/ranked/20261016-973-cross-ready/game.png',[1312030,1698132,1645952,1579496,866320]),
    ('resources/local/ranked-1920-calibration.png',[672886,1174445,1313308,1419289,1162291]),
]
PROTECTED=['local_flows.py','wanted_task.py','native_worker.py','ranked_pipeline.py',
           'app.py','mission_desk_ui.py','config.json','run.json','resources/tasks.json',
           'logs/2026-10-18.log','resources/local/catalog/digits/index.json']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserved():
    paths=[ROOT/p for p in PROTECTED]
    for folder in ('resources/local/image','resources/local/catalog/ranked/20261016-973-cross-ready',
                   '出错任务/排位战/证据'):
        paths.extend((ROOT/folder).glob('*.png'))
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def main():
    before=preserved()
    catalog=ROOT/'resources/local/catalog'
    bank=json.loads((catalog/'digits/index.json').read_text(encoding='utf-8'))
    family=next(f for f in bank['families'] if f['id']=='white_serif_small')
    assert set(family['digits'])==set('0123456789')
    template_audit=[]
    for digit,ref in family['digits'].items():
        path=catalog/ref['catalogPath'];assert digest(path)==ref['sha256']
        mp=catalog/ref['manifest'];manifest=json.loads(mp.read_text(encoding='utf-8'))
        asset=next(a for a in manifest['assets'] if a['id']==ref['assetId'])
        with Image.open(path) as im:rgb=im.convert('RGB');size=rgb.size;pixels=rgb.tobytes()
        source=mp.parent/manifest['sourceImage'];assert digest(source)==manifest['sourceSha256']
        with Image.open(source) as im:assert pixels==im.convert('RGB').crop(asset['sourceBox']).tobytes()
        with Image.open(mp.parent/manifest['gameImage']) as im:assert pixels==im.convert('RGB').crop(asset['box']).tobytes()
        mask=white_ink(np.array(rgb),190);ys,xs=np.where(mask)
        template_audit.append({'digit':digit,'path':ref['catalogPath'],'sha256':digest(path),
                               'cropSize':list(size),'inkSize':[int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)],
                               'sourceBox':asset['sourceBox'],'sourceSha256':manifest['sourceSha256'],
                               'sourcePixelsVerified':True})
    assert len(white_power_templates())==10
    ocr=LocalOCR();samples=[];accepted=0;rejected=0;accepted_digits=set()
    for name,expected in SAMPLES:
        with Image.open(ROOT/name) as im:image=np.array(im.convert('RGB'))[:,:,::-1].copy()
        words=ocr.read(image)
        labels=sorted([i for i in words if re.search(r'战力|战斗力',i['text']) and i['box'][1]>550],key=lambda i:i['box'][0])
        assert len(labels)==len(expected)==5
        rows=[]
        for item,value in zip(labels,expected):
            reading=read_white_power(image,item)
            assert reading is None or reading==value,(name,value,reading)
            accepted+=reading is not None;rejected+=reading is None
            if reading is not None:accepted_digits.update(str(reading))
            x,y,w,h=item['box'];patch=image[max(0,y-3):y+h+3,max(0,x-3):x+w+12,::-1]
            ys,xs=np.where(white_ink(patch,205))
            numbers=patch[ys.min():ys.max()+1,xs.min():xs.max()+1]
            candidates={str(t):[{'meanIoU':float(1-cost),'text':text,'minimumIoU':float(minimum)}
                               for cost,text,minimum in white_digit_candidates(white_ink(numbers,t),white_power_templates())[:2]]
                        for t in (190,200)}
            rows.append({'originalOCR':item,'expected':value,'templateValue':reading,
                         'brightInkSize':[numbers.shape[1],numbers.shape[0]],'candidates':candidates})
        samples.append({'image':name,'sha256':digest(ROOT/name),'opponents':rows})
    assert accepted_digits==set('0123456789')
    modules=['tests_ranked_white_digits','tests_ranked','tests_ranked_battle','tests_ranked_pipeline',
             'tests_ranked_pipeline_images','tests_ranked_options','tests_wanted']
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m','unittest',*modules]
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    process=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    after=preserved();changed=[name for name,h in before.items() if after.get(name)!=h]
    assert not changed,changed
    sources=['ranked_vision.py','tests_ranked_white_digits.py','tools/verify_ranked_white_templates.py']
    for name in sources:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    report={'generatedAt':datetime.now().astimezone().isoformat(),'mode':'offline saved images only',
            'templateFamily':'white_serif_small','templates':template_audit,'samples':samples,
            'accepted':accepted,'rejected':rejected,'wrongAccepted':0,'acceptedDigits':''.join(sorted(accepted_digits)),
            'rules':{'thresholds':[190,200],'heightRange':[12,14],'widthRange':[20,100],
                     'maxInkDensity':.8,'minimumGlyphIoU':.55,'minimumMeanIoU':.65,
                     'minimumAlternativeLead':.035,'lengthRange':[4,9],
                     'fallbackOnlyWhenNoNumericOCR':True,'characterSubstitution':False},
            'command':command,'exitCode':process.returncode,'output':process.stdout+process.stderr,
            'protectedFileCount':len(before),'protectedChanged':changed,'runtimeTemplatesAdded':0,
            'sourceHashes':{name:digest(ROOT/name) for name in sources},'syntaxParsed':sources,
            'actualGameInputs':0,
            'limitations':['Shape fallback deliberately rejects unsupported or ambiguous ink; it is not a universal font reader.',
                           'Only the archived 1920x1015 small serif appearance is validated, not every resolution/font.',
                           'Backend checks do not validate current UI or a new live game run.']}
    output=ROOT/'verification/ranked-white-template-recognition-20261019.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(output),'accepted':accepted,'rejected':rejected,'wrongAccepted':0,
                      'protectedFileCount':len(before),'exitCode':process.returncode},ensure_ascii=False),flush=True)
    print(process.stdout+process.stderr,flush=True)
    raise SystemExit(process.returncode)


if __name__=='__main__':main()
