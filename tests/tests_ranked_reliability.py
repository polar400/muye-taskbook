"""Acceptance must not pass through duplicate images, tuning leakage or errors."""
import hashlib
import unittest
from tools.ranked_reliability import lineup_id,metrics,validate_suite,read_promotions
from pathlib import Path
from tempfile import TemporaryDirectory
import json


def fixture(groups=20):
    cases=[];rows=[]
    for i in range(groups):
        powers=[100000+i*10+j for j in range(5)]
        case=dict(caseId='p'+str(i),sha256=hashlib.sha256(str(i).encode()).hexdigest(),kind='positive',
                  split='holdout',lineupId=lineup_id(powers),expected=dict(own=99999,remaining=7,opponents=powers))
        cases.append(case);rows.append(dict(caseId=case['caseId'],correct=True,wrongAccepted=False,wrongComponentAccepts=[]))
    for i in range(10):
        case=dict(caseId='n'+str(i),sha256=hashlib.sha256(('negative'+str(i)).encode()).hexdigest(),
                  kind='negative',split='rejection',expected='reject')
        cases.append(case);rows.append(dict(caseId=case['caseId'],correct=True,wrongAccepted=False,wrongComponentAccepts=[]))
    return dict(target=dict(distinctHoldoutLineups=20,negativeCases=10,completePanelRate=.95,wrongAccepted=0),cases=cases),rows


class RankedReliabilityTests(unittest.TestCase):
    def test_nineteen_correct_and_one_refusal_can_pass_twenty_groups(self):
        suite,rows=fixture();rows[0]['correct']=False
        result=metrics(suite,rows)
        self.assertEqual(result['completePanelRate'],.95)
        self.assertTrue(result['acceptancePassed'])

    def test_nineteen_groups_at_one_hundred_percent_is_insufficient(self):
        suite,rows=fixture(19);result=metrics(suite,rows)
        self.assertEqual(result['completePanelRate'],1.)
        self.assertEqual(result['missingHoldoutLineups'],1)
        self.assertFalse(result['acceptancePassed'])

    def test_any_wrong_accepted_number_prevents_passing(self):
        for field,value in (('wrongAccepted',True),('wrongComponentAccepts',['opponent-4'])):
            suite,rows=fixture();rows[0][field]=value
            self.assertFalse(metrics(suite,rows)['acceptancePassed'])

    def test_duplicate_lineup_frames_do_not_increase_denominator(self):
        suite,rows=fixture()
        for case in suite['cases'][:20]:
            case['lineupId']=suite['cases'][0]['lineupId']
            case['expected']=suite['cases'][0]['expected']
        result=metrics(suite,rows)
        self.assertEqual(result['holdoutLineups'],1)
        self.assertFalse(result['acceptancePassed'])

    def test_failed_frame_cannot_hide_behind_a_passing_duplicate(self):
        suite,rows=fixture()
        duplicate=dict(suite['cases'][0],caseId='another-frame',sha256='different pixels')
        suite['cases'].append(duplicate)
        rows.append(dict(caseId='another-frame',correct=False,wrongAccepted=False,wrongComponentAccepts=[]))
        self.assertEqual(metrics(suite,rows)['completeLineups'],19)

    def test_promoting_a_lineup_removes_all_its_frames_from_holdout(self):
        suite,rows=fixture()
        duplicate=dict(suite['cases'][0],caseId='another-frame',sha256='different pixels')
        suite['cases'].append(duplicate)
        rows.append(dict(caseId='another-frame',correct=True,wrongAccepted=False,wrongComponentAccepts=[]))
        result=metrics(suite,rows,[duplicate['lineupId']])
        self.assertEqual(result['holdoutLineups'],19)
        self.assertFalse(result['acceptancePassed'])

    def test_same_lineup_cannot_cross_development_and_holdout(self):
        suite,_=fixture();case=dict(suite['cases'][0],caseId='leak',sha256='different pixels',split='development')
        suite['cases'].append(case)
        with self.assertRaisesRegex(ValueError,'crosses'):validate_suite(suite)

    def test_promotion_ledger_cannot_keep_a_failed_sibling_as_holdout(self):
        suite,_=fixture();first=suite['cases'][0]
        suite['cases'].append(dict(first,caseId='sibling',sha256='different pixels'))
        with TemporaryDirectory() as folder:
            path=Path(folder)/'promotions.json'
            path.write_text(json.dumps({'entries':[dict(lineupId=first['lineupId'],caseIds=[first['caseId']])]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'all frames'):read_promotions(suite,path)
            path.write_text(json.dumps({'entries':[dict(lineupId=first['lineupId'],caseIds=[first['caseId'],'sibling'])]}),encoding='utf-8')
            self.assertEqual(read_promotions(suite,path),{first['lineupId']})


if __name__=='__main__':unittest.main()
