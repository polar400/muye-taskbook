"""A grey-boundary tie needs a qualified midpoint and two agreeing numeric OCR reads."""
from pathlib import Path
from unittest.mock import Mock,patch
import unittest

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_numbers import NumberRecognitionError,arbitrate,opponent_region,read_opponent,shape_reading
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent
SOURCE='verification/failure-20261106-164346-b6a32fb16ea1-ranked.png'
POWERS=[575116,543060,962616,864010,470969]


def candidates(text='314159',lead=.2,cost=.4,minimum=.9):
    return [(cost,text,minimum),(cost+lead,'314150',.8)]


class RankedMidpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR()
        cls.image=np.array(Image.open(ROOT/SOURCE).convert('RGB'))[:,:,::-1].copy()
        cls.button={'box':[402,832,62,30]}

    def test_latest_failure_passes_complete_production_read(self):
        flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
        flow.image=self.image.copy();flow.items=self.ocr.read(flow.image)
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(2,341221))
        self.assertEqual([o['power'] for o in opponents],POWERS)
        flow.window.click.assert_not_called()

    def test_real_weak_margin_is_kept_as_evidence(self):
        rgb,_=opponent_region(self.image,self.button)
        result=shape_reading(rgb)
        self.assertEqual(result['value'],575116)
        self.assertEqual(result['requiredOCRReadings'],2)
        self.assertTrue(result['midpointConfirmed'])
        self.assertLess(next(v for v in result['views'] if v['threshold']==190)['lead'],.08)
        middle=next(v for v in result['views'] if v['threshold']==180)
        self.assertEqual(middle['value'],575116)
        self.assertGreaterEqual(middle['lead'],.08)

    def test_disagreement_missing_poor_tied_or_both_weak_primary_views_stop(self):
        cases=[(candidates(),candidates('314158',lead=.04)),
               (candidates(),[]),(candidates(),candidates(lead=.04,cost=1.5)),
               (candidates(),candidates(lead=0)),
               (candidates(lead=.04),candidates(lead=.04)),
               (candidates(),candidates('0314159',lead=.04))]
        for first,second in cases:
            with self.subTest(first=first,second=second):
                with patch('ranked_numbers.shape_candidates',side_effect=[first,second,AssertionError('must not rescue these views')]):
                    self.assertIsNone(shape_reading(np.zeros((13,53,3),dtype='uint8'))['value'])

    def test_midpoint_must_itself_agree_and_meet_unchanged_gates(self):
        for middle,expected in ((candidates(),314159),(candidates('314158'),None),
                                (candidates(minimum=.64),None),(candidates(cost=1.5),None),
                                (candidates(lead=.079),None),([],None)):
            with self.subTest(middle=middle):
                with patch('ranked_numbers.shape_candidates',side_effect=[candidates(),candidates(lead=.04),middle]):
                    self.assertEqual(shape_reading(np.zeros((13,53,3),dtype='uint8'))['value'],expected)

    def test_midpoint_cannot_use_shape_only_or_one_valid_ocr_read(self):
        # Even excellent IoU cannot make this new branch bypass numeric OCR.
        shape=dict(value=575116,midpointConfirmed=True,requiredOCRReadings=2,
                   views=[dict(meanIoU=.99,minimumIoU=.99)]*3)
        for observations in ([],[{'value':575116}],[{'value':575116},{'value':None}]):
            self.assertIsNone(arbitrate(observations,shape)[0])
        self.assertEqual(arbitrate([{'value':575116}]*2,shape)[0],575116)
        self.assertIsNone(arbitrate([{'value':575116},{'value':575110}],shape)[0])
        self.assertIsNone(arbitrate([{'value':575110}]*2,shape)[0])

    def test_real_midpoint_conflict_and_single_read_cannot_be_overridden(self):
        ocr=Mock();ocr.read.side_effect=[[{'text':'575116','score':.99}],
                                      [{'text':'575110','score':.99}],AssertionError('conflict must stop')]
        with self.assertRaisesRegex(NumberRecognitionError,'冲突'):read_opponent(self.image,self.button,ocr)
        ocr=Mock();ocr.read.side_effect=[[{'text':'575116','score':.99}],[],[],[]]
        with self.assertRaises(NumberRecognitionError):read_opponent(self.image,self.button,ocr)


if __name__=='__main__':unittest.main()
