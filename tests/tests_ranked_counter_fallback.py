"""Ranked-only caption-box fallback retains two-read agreement and conflict stops."""
from pathlib import Path
from unittest.mock import Mock
import unittest

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows,normalized
from ranked_vision import read_ranked_remaining
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FRAMES=['verification/failure-20261106-011630-9f9f174d8ec0-ranked.png',
        'verification/failure-20261106-011640-3c1baf0df03b-ranked.png']


class RankedCounterFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def test_real_separator_failures_pass_full_panel_and_numbers(self):
        for name in FRAMES:
            with self.subTest(frame=name):
                flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
                flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                self.assertTrue(flow.ranked_panel_visible())
                count,own,opponents=flow.ranked_state()
                self.assertEqual((count,own),(7,571238))
                self.assertEqual([o['power'] for o in opponents],[1499302,1455783,1313308,2350943,715530])
                flow.window.click.assert_not_called()

    def test_separator_alias_needs_a_second_read(self):
        image=np.zeros((1015,1920,3),dtype='uint8')
        for separator in (';','；'):
            item={'text':'剩余共战次数'+separator+'7','score':.99,'box':[1648,95,150,21]}
            ocr=Mock();ocr.read.return_value=[]
            with self.subTest(separator=separator):
                with self.assertRaisesRegex(RuntimeError,'可靠读取'):
                    read_ranked_remaining(image,[item],ocr,normalized)
                ocr.read.return_value=[item]
                self.assertEqual(read_ranked_remaining(image,[item],ocr,normalized),7)

    def test_separator_read_conflict_and_out_of_range_still_stop(self):
        image=np.zeros((1015,1920,3),dtype='uint8')
        def item(value):return {'text':'剩余共战次数;'+str(value),'score':.99,'box':[1648,95,150,21]}
        ocr=Mock();ocr.read.return_value=[item(6)]
        with self.assertRaisesRegex(RuntimeError,'冲突'):
            read_ranked_remaining(image,[item(7)],ocr,normalized)
        ocr.read.return_value=[item(21)]
        with self.assertRaisesRegex(RuntimeError,'异常'):
            read_ranked_remaining(image,[item(21)],ocr,normalized)

    def test_caption_box_fallback_requires_matching_full_text(self):
        image=np.zeros((1015,1920,3),dtype='uint8')
        item={'text':'剩余共战次数:7','score':.99,'box':[1648,95,150,21]}
        for final,success in (([item],True),([],False),([dict(item,text='剩余共战次数:6')],False),
                              ([dict(item,text='7')],False),([dict(item,score=.79)],False)):
            with self.subTest(final=final):
                ocr=Mock();ocr.read.side_effect=[[],[],final]
                if success:self.assertEqual(read_ranked_remaining(image,[item],ocr,normalized),7)
                else:
                    with self.assertRaises(RuntimeError):read_ranked_remaining(image,[item],ocr,normalized)


if __name__=='__main__':unittest.main()
