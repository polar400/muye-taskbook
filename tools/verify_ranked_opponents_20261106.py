"""Replay labelled ranked panels through production readers; never opens a game."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock
import argparse
import ast
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)];sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from tools.prepare_ranked_number_bank import SOURCES
from tools.verify_ranked_numbers import HOLDOUT
from PIL import Image
import numpy as np

OCT26=['verification/failure-20261026-'+name+'-ranked.png' for name in (
       '160736-2d7b29ca4e80','204732-a0f03c0154b2','205955-5c231a4f137f',
       '210009-0df10f72096d','210317-1c9435634012')]
NOV6=['verification/failure-20261106-005541-308d39bb9a19-ranked.png',
      'verification/failure-20261106-005612-02e7419ac0d1-ranked.png']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,default=ROOT)
    args=parser.parse_args();ocr=LocalOCR();samples=[]
    groups=[('bank source',SOURCES),('historical holdout',HOLDOUT),
            ('Oct26 holdout',[(p,[1430931,1095433,935536,1059743,730541]) for p in OCT26]),
            ('Nov6 holdout',[(p,[1499302,1455783,1313308,2350943,715530]) for p in NOV6])]
    bank=json.loads((ROOT/'resources/local/ranked_numbers/bank.json').read_text(encoding='utf-8'))
    assert not {s['path'] for s in bank['sources']} & set(NOV6)
    for group,frames in groups:
        for name,expected in frames:
            flow=LocalFlows(Mock(),ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
            flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
            flow.items=ocr.read(flow.image)
            count,own,opponents=flow.ranked_state();actual=[o['power'] for o in opponents]
            assert actual==expected,(name,actual,expected)
            if name in NOV6:assert (count,own)==(7,571238)
            flow.window.click.assert_not_called()
            samples.append(dict(group=group,path=name,sha256=digest(ROOT/name),remaining=count,own=own,
                                expected=expected,actual=actual,evidence=flow.ranked_number_evidence))
    output=(ROOT/'verification/ranked-opponents-tests-20261106.txt').read_text(encoding='utf-8-sig')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    assert match and '\nOK\n' in output and 'FAILED' not in output,output[-3000:]
    protected=json.loads((ROOT/'verification/ranked-opponents-baseline-20261106.json').read_text(encoding='utf-8'))
    changed=[name for name,old in protected.items() if digest(ROOT/name)!=old]
    assert not changed,changed
    files=['ranked_numbers.py','tests_ranked_opponents_20261106.py','tools/verify_ranked_opponents_20261106.py']
    for name in files:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    report=dict(generatedAt=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                mode='offline original pixels; simulated game transitions and input only',actualGameInputs=0,
                tests=int(match[1]),seconds=float(match[2]),testOutput=output,
                frames=len(samples),accepted=sum(len(s['actual']) for s in samples),wrongAccepted=0,
                samples=samples,bankSha256=digest(ROOT/'resources/local/ranked_numbers/bank.json'),
                sourceHashes={p:digest(ROOT/p) for p in files},protectedCount=len(protected),
                protectedHashes=protected,protectedChanged=changed,
                beforeCodeSha256=digest(ROOT/'verification/ranked-opponents-before-20261106.py'),
                redOutput=(ROOT/'verification/ranked-opponents-red-20261106.txt').read_text(encoding='utf-8'),
                limitations=['Only calibrated 1920x1015 saved appearances were tested.',
                             'Repeated failure frames show the same lineups; they are not independent unseen fonts.',
                             'No live-game challenge/refresh/settlement acceptance; simulated returned panel is an older independent frame.',
                             'Unknown or conflicting evidence still stops; no blanket font coverage claim.'])
    target=args.output_root/'verification/ranked-opponents-20261106.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('frames','accepted','wrongAccepted','tests','seconds','protectedChanged')},ensure_ascii=False))


if __name__=='__main__':main()
