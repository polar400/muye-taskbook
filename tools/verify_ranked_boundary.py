"""Offline audit of the Oct 26 touching-digit fix. No window or game input."""
from pathlib import Path
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta
import ast
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from tools.prepare_ranked_number_bank import SOURCES
from tools.verify_ranked_numbers import HOLDOUT
from PIL import Image
import numpy as np


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline=json.loads((ROOT/'verification/ranked-09-boundary-baseline-20261026.json').read_text(encoding='utf-8'))
    ocr=LocalOCR();rows=[]
    current=[(str(p.relative_to(ROOT)),[1430931,1095433,935536,1059743,730541])
             for p in sorted((ROOT/'verification').glob('failure-20261026-*-ranked.png'))]
    assert len(current)==5
    sources={s['path'] for s in json.loads((ROOT/'resources/local/ranked_numbers/bank.json').read_text(encoding='utf-8'))['sources']}
    assert not sources & {p for p,_ in current}
    for group,samples in (('bank source',SOURCES),('historical holdout',HOLDOUT),('Oct26 holdout',current)):
        for name,expected in samples:
            flow=LocalFlows(Mock(),ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
            flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
            flow.items=ocr.read(flow.image)
            count,own,opponents=flow.ranked_state()
            actual=[o['power'] for o in opponents]
            assert actual==expected,(name,actual,expected)
            flow.window.click.assert_not_called()
            rows.append(dict(group=group,path=name,sha256=digest(ROOT/name),remaining=count,
                             own=own,expected=expected,actual=actual,evidence=flow.ranked_number_evidence))
    output=(ROOT/'verification/ranked-09-boundary-tests-20261026.txt').read_text(encoding='utf-8-sig')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    assert match and '\nOK\n' in output and 'FAILED' not in output,output[-3000:]
    protected={p:digest(ROOT/p) for p in baseline}
    changed=[p for p,h in baseline.items() if protected[p]!=h]
    assert not changed,changed
    files=['ranked_numbers.py','tests_ranked_numbers.py','tools/verify_ranked_boundary.py']
    for name in files:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    report=dict(generatedAt=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                mode='offline archived pixels and simulated game IO',actualGameInputs=0,
                frames=len(rows),accepted=sum(len(r['actual']) for r in rows),wrongAccepted=0,
                uniqueOct26Crops=len({digest(p) for p in (ROOT/'verification').glob('failure-20261026-*-ranked-numbers/opponent-1.png')}),
                tests=int(match[1]),seconds=float(match[2]),testOutput=output,
                redOutput='verification/ranked-09-boundary-red-20261026.txt',
                sourceHashes={p:digest(ROOT/p) for p in files},protectedHashes=protected,
                protectedChanged=changed,samples=rows,
                limitations=['Five Oct26 frames repeat the same opponent lineup, not five unseen fonts.',
                             'No live-game challenge, refresh, settlement or desktop acceptance this phase.',
                             'Only calibrated 1920x1015 screenshots; unknown or conflicting evidence still stops.'])
    target=ROOT/'verification/ranked-09-boundary-20261026.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('frames','accepted','wrongAccepted','tests','seconds','protectedChanged','uniqueOct26Crops')},ensure_ascii=False))


if __name__=='__main__':main()
