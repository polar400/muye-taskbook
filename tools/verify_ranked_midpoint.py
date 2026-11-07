"""Audit the new development failure and the unchanged frozen ranked suite."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import ast
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from tools.ranked_reliability import evaluate,lineup_id,metrics,read_promotions,validate_suite


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'verification/ranked-575116-20261106'
    old=ROOT/'verification/ranked-reliability-20261106'
    suite=json.loads((old/'suite-v2.json').read_text(encoding='utf-8'))
    seal=json.loads((old/'suite-seal-v2.json').read_text(encoding='utf-8'))
    assert digest(old/'suite-v2.json')==seal['manifestSha256']
    sample=json.loads((folder/'development-sample.json').read_text(encoding='utf-8'))
    latest=dict(caseId='development-575116',kind='positive',split='development',path=sample['path'],
                sha256=digest(ROOT/sample['path']),lineupId=lineup_id(sample['opponents']),
                expected={k:sample[k] for k in ('remaining','own','opponents')})
    suite=dict(suite,cases=[*suite['cases'],latest]);validate_suite(suite)
    ocr=LocalOCR();rows=[]
    for case in suite['cases']:
        assert digest(ROOT/case['path'])==case['sha256'],case['path']
        row=evaluate(case,ocr);rows.append(row)
        assert row['correct'] and not row['wrongAccepted'] and not row['wrongComponentAccepts'],row
    evidence=rows[-1]['evidence']['opponents'][0]
    assert evidence['value']==575116 and evidence['shape']['requiredOCRReadings']==2
    assert evidence['shape']['midpointConfirmed']
    assert len([o for o in evidence['observations'] if o['value']==575116])>=2
    assert next(v for v in evidence['shape']['views'] if v['threshold']==190)['lead']<.08
    middle=next(v for v in evidence['shape']['views'] if v['threshold']==180)
    assert middle['value']==575116 and middle['lead']>=.08
    promoted=read_promotions(suite,old/'promotions.json');summary=metrics(suite,rows,promoted)
    assert summary['holdoutLineups']==3 and summary['missingHoldoutLineups']==17 and not summary['acceptancePassed']
    before=json.loads((folder/'before-hashes.json').read_text(encoding='utf-8'))
    changed=[p for p,h in before.items() if digest(ROOT/p)!=h]
    assert changed==['ranked_numbers.py'],changed
    output=(folder/'tests.txt').read_text(encoding='utf-8-sig')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',output)
    assert match and '\nOK\n' in output and 'FAILED' not in output,output[-2500:]
    files=['ranked_numbers.py','tests_ranked_midpoint.py','tools/verify_ranked_midpoint.py']
    for name in files:ast.parse((ROOT/name).read_text(encoding='utf-8'))
    positive=[r for r in rows if r['kind']=='positive'];negative=[r for r in rows if r['kind']=='negative']
    report=dict(generatedAt=datetime.now(timezone(timedelta(hours=8))).isoformat(),actualGameInputs=0,
                scope='Repair of Nov6 16:44 opponent 575116 grey-margin refusal; no game action',
                positiveFrames=len(positive),correctPositiveFrames=sum(r['correct'] for r in positive),
                negativeFrames=len(negative),correctRejections=sum(r['correct'] for r in negative),
                independentAcceptance=summary,tests=int(match[1]),seconds=float(match[2]),testOutput=output,
                redOutput=(folder/'red.txt').read_text(encoding='utf-8'),cases=rows,
                beforeHashes=before,protectedChanged=[],changedRuntimeFiles=changed,
                sourceHashes={p:digest(ROOT/p) for p in files},suiteSha256=seal['manifestSha256'],
                latestBeforeEvidence='verification/failure-20261106-164346-b6a32fb16ea1-ranked-numbers/evidence.json',
                limitations=['The newly diagnosed frame is development data, not independent validation.',
                             'Original three untuned lineups remain; the twenty-lineup target is still short by seventeen.',
                             'Three masks and OCR views share source pixels; they are quality checks, not independent real-world samples.',
                             'No fresh live challenge, refresh, purchase or unrelated-task repair in this phase.'])
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('positiveFrames','correctPositiveFrames','negativeFrames','correctRejections','tests','seconds','changedRuntimeFiles')},ensure_ascii=False))


if __name__=='__main__':main()
