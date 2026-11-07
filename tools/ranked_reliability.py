"""Offline ranked acceptance: sealed labels, lineup splits and honest denominators."""
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def lineup_id(powers):
    return hashlib.sha256(json.dumps(sorted(powers)).encode()).hexdigest()[:16]


def validate_suite(suite):
    ids=set();sources=set();splits={}
    for case in suite['cases']:
        if case['caseId'] in ids or case['sha256'] in sources:
            raise ValueError('duplicate case identity/source pixels')
        ids.add(case['caseId']);sources.add(case['sha256'])
        if case['kind']=='positive':
            expected=case['expected'];powers=expected['opponents']
            if len(powers)!=5 or any(type(v)!=int or v<=0 for v in powers):
                raise ValueError('five independently labelled positive powers required')
            if type(expected['own'])!=int or expected['own']<=0 or not 1<=expected['remaining']<=20:
                raise ValueError('complete positive own power and count required')
            group=lineup_id(powers)
            if case['lineupId']!=group:raise ValueError('lineup identity disagrees with labels')
            if group in splits and splits[group]!=case['split']:
                raise ValueError('same lineup crosses development/regression/holdout')
            splits[group]=case['split']
        elif case['kind']!='negative' or case['expected']!='reject':
            raise ValueError('unknown case kind/label')


def metrics(suite,rows,promoted=()):
    by_id={r['caseId']:r for r in rows};promoted=set(promoted)
    groups=defaultdict(list);negatives=[]
    for case in suite['cases']:
        if case['caseId'] not in by_id:continue
        if case['kind']=='negative':negatives.append(by_id[case['caseId']])
        elif case['split']=='holdout' and case['lineupId'] not in promoted:
            groups[case['lineupId']].append(by_id[case['caseId']])
    # Every available frame in a group must pass. Repeated animation frames
    # cannot increase the primary denominator or hide a failing observation.
    successes=sum(all(r['correct'] for r in group) for group in groups.values())
    rate=successes/len(groups) if groups else None
    wrong=sum(bool(r.get('wrongAccepted')) for r in rows)
    wrong_components=sum(bool(r.get('wrongComponentAccepts')) for r in rows)
    rejected=sum(r['correct'] for r in negatives)
    target=suite['target'];enough=len(groups)>=target['distinctHoldoutLineups'] and len(negatives)>=target['negativeCases']
    quality=rate is not None and rate>=target['completePanelRate'] and not wrong and not wrong_components and rejected==len(negatives)
    return dict(holdoutLineups=len(groups),completeLineups=successes,completePanelRate=rate,
                negativeCases=len(negatives),correctRejections=rejected,wrongAccepted=wrong,
                wrongComponentAccepts=wrong_components,promotedLineups=sorted(promoted),
                missingHoldoutLineups=max(0,target['distinctHoldoutLineups']-len(groups)),
                missingNegativeCases=max(0,target['negativeCases']-len(negatives)),
                sampleTargetMet=enough,observedQualityMet=quality,acceptancePassed=enough and quality)


def read_promotions(suite,path):
    if not path.exists():return set()
    ledger=json.loads(path.read_text(encoding='utf-8'));groups=set()
    for entry in ledger['entries']:
        expected={c['caseId'] for c in suite['cases'] if c.get('lineupId')==entry['lineupId'] and c['split']=='holdout'}
        if not expected or set(entry['caseIds'])!=expected:
            raise ValueError('promotion must include all frames of a held-out lineup')
        groups.add(entry['lineupId'])
    return groups


def evaluate(case,ocr):
    from unittest.mock import Mock,patch
    import numpy as np
    from PIL import Image
    from local_flows import LocalFlows
    from ranked_vision import read_red_power
    image=np.array(Image.open(ROOT/case['path']).convert('RGB'))[:,:,::-1].copy()
    if image.shape!=(1015,1920,3):raise ValueError('source is not calibrated: '+case['path'])
    window=Mock();window.click.side_effect=AssertionError('offline evaluator must not send input')
    flow=LocalFlows(window,ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
    flow.image=image;own_readings=[]
    def traced_own(*args):
        value=read_red_power(*args);own_readings.append(value);return value
    start=time.perf_counter();flow.items=ocr.read(image)
    accepted=False;actual=None;error=None;visible=False
    with patch('local_flows.read_red_power',side_effect=traced_own):
        try:
            visible=flow.ranked_panel_visible()
            if visible:
                count,own,opponents=flow.ranked_state()
                actual=dict(remaining=count,own=own,opponents=[o['power'] for o in opponents]);accepted=True
            else:error='ranked panel gate rejected source'
        except RuntimeError as exc:error=str(exc)
    seconds=time.perf_counter()-start
    window.click.assert_not_called()
    correct=actual==case['expected'] if case['kind']=='positive' else not accepted
    wrong=accepted and not correct
    evidence=getattr(flow,'ranked_number_evidence',None)
    bad_components=[]
    if case['kind']=='positive':
        if any(v!=case['expected']['own'] for v in own_readings):bad_components.append('own')
        if evidence:
            for i,(row,expected) in enumerate(zip(evidence['opponents'],case['expected']['opponents']),1):
                if row.get('value') is not None and row['value']!=expected:bad_components.append('opponent-'+str(i))
    return dict(caseId=case['caseId'],path=case['path'],split=case['split'],kind=case['kind'],
                accepted=accepted,correct=correct,wrongAccepted=wrong,wrongComponentAccepts=bad_components,
                expected=case['expected'],actual=actual,ownReadings=own_readings,
                error=error,seconds=seconds,panelVisible=visible,evidence=evidence)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--suite',type=Path,required=True);parser.add_argument('--seal',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--splits',default='regression,development,rejection,holdout')
    parser.add_argument('--frozen-code',type=Path)
    parser.add_argument('--promoted-lineup',action='append',default=[])
    parser.add_argument('--promotions',type=Path)
    args=parser.parse_args()
    suite=json.loads(args.suite.read_text(encoding='utf-8'));seal=json.loads(args.seal.read_text(encoding='utf-8'))
    if digest(args.suite)!=seal['manifestSha256']:raise ValueError('suite seal mismatch')
    validate_suite(suite)
    ledger=args.promotions or args.suite.parent/'promotions.json'
    promoted=read_promotions(suite,ledger)|set(args.promoted_lineup)
    for case in suite['cases']:
        if digest(ROOT/case['path'])!=case['sha256']:raise ValueError('source changed: '+case['path'])
    sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)];sys.path.insert(0,str(ROOT/'vendor'))
    from adapters.local_ocr import LocalOCR
    import ranked_numbers,ranked_vision
    if args.frozen_code:
        # Only isolated offline subprocesses use this switch. Both versions
        # share assets whose protected hashes are audited separately.
        for module in (ranked_numbers,ranked_vision):
            path=args.frozen_code/(module.__name__+'.py')
            exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),module.__dict__)
    splits=set(args.splits.split(','));ocr=LocalOCR();rows=[]
    for case in suite['cases']:
        if case['split'] not in splits:continue
        row=evaluate(case,ocr)
        row['effectiveSplit']='development-promoted' if case.get('lineupId') in promoted else case['split']
        rows.append(row)
        print(json.dumps({k:row[k] for k in ('caseId','accepted','correct','error','seconds')},ensure_ascii=False),flush=True)
    summary=metrics(suite,rows,promoted)
    times=sorted(r['seconds'] for r in rows)
    if times:summary.update(meanSeconds=sum(times)/len(times),p95Seconds=times[min(len(times)-1,int(.95*len(times)))],maxSeconds=max(times))
    code_files=['ranked_numbers.py','ranked_vision.py','ranked_pipeline.py','local_flows.py']
    hashes={p:digest((args.frozen_code/p) if args.frozen_code and p in ('ranked_numbers.py','ranked_vision.py') else ROOT/p) for p in code_files}
    report=dict(generatedAt=datetime.now(timezone(timedelta(hours=8))).isoformat(),actualGameInputs=0,
                suiteSha256=digest(args.suite),variant='frozen baseline' if args.frozen_code else 'candidate',
                codeHashes=hashes,target=suite['target'],summary=summary,cases=rows,
                labelCorrections=suite.get('labelCorrections',[]),
                promotions=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else None,
                revealedHoldoutReplay=metrics(suite,rows),
                limitations=suite['limitations']+['Offline single-frame full-panel measurement; live multi-frame interaction is not measured.'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
