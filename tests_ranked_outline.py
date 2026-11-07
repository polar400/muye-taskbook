"""Promoted blind failures are regression fixtures, never independent holdouts."""
from pathlib import Path
from unittest.mock import Mock
import unittest

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_numbers import NumberRecognitionError,opponent_region,read_opponent,shape_reading
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent
NOV6='verification/failure-20261106-011716-016eae9a5cb8-ranked.png'


class RankedOutlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def test_promoted_count_and_outline_failures_read_complete_panels(self):
        cases=[('verification/failure-20261015-005552-aca6468c75aa-ranked.png',3,565140,
                [1312030,1698132,1645952,1579496,773414]),
               ('verification/failure-20261015-005756-3a8e83f16e96-ranked.png',3,565140,
                [1312030,1698132,1645952,1579496,773414]),
               (NOV6,5,341221,[1353663,992838,750130,855344,470969])]
        for name,count,own,powers in cases:
            with self.subTest(frame=name):
                flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
                flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                self.assertTrue(flow.ranked_panel_visible())
                actual_count,actual_own,opponents=flow.ranked_state()
                self.assertEqual((actual_count,actual_own),(count,own))
                self.assertEqual([o['power'] for o in opponents],powers)
                flow.window.click.assert_not_called()

    def test_original_grey_diagonal_of_four_is_present_in_numeric_crop(self):
        image=np.array(Image.open(ROOT/NOV6).convert('RGB'))[:,:,::-1].copy()
        rgb,_=opponent_region(image,{'box':[1486,836,70,30]})
        reading=shape_reading(rgb)
        self.assertEqual(reading['value'],470969)
        self.assertTrue(all(v.get('value')==470969 for v in reading['views']))

    def test_ocr_misreading_four_as_one_must_not_be_accepted(self):
        image=np.array(Image.open(ROOT/NOV6).convert('RGB'))[:,:,::-1].copy()
        ocr=Mock();ocr.read.return_value=[{'text':'170969','score':.99}]
        with self.assertRaisesRegex(NumberRecognitionError,'冲突'):
            read_opponent(image,{'box':[1486,836,70,30]},ocr)


if __name__=='__main__':unittest.main()
