"""White opponent digit fallback regressions on saved pixels; no game IO."""
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from adapters.local_ocr import LocalOCR  # Set up bundled imports before numpy.
import numpy as np
from PIL import Image
from local_flows import normalized
from local_flows import LocalFlows
from ranked_pipeline import RankedSession
from ranked_vision import (read_opponent_power,read_white_power,white_digit_candidates,
                           white_ink,white_power_templates)

ROOT=Path(__file__).resolve().parent


class WhiteDigitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image=np.array(Image.open(ROOT/'出错任务/排位战/证据/859054be011704e1a56a2121.png').convert('RGB'))[:,:,::-1].copy()
        cls.item={'text':'战斗力:%0878','box':[890,870,134,22],'score':.95}

    def test_percent_only_ocr_uses_saved_touching_numeric_pixels(self):
        ocr=Mock()
        ocr.read.return_value=[{'text':'9%0878','score':.95}]
        self.assertEqual(read_opponent_power(self.image,self.item,ocr,normalized),960878)
        self.assertEqual(ocr.read.call_count,7)

    def test_empty_ocr_can_be_recovered_from_the_same_original_pixels(self):
        ocr=Mock();ocr.read.return_value=[]
        self.assertEqual(read_opponent_power(self.image,self.item,ocr,normalized),960878)

    def test_other_saved_opponent_values_are_not_fixed_to_the_failure_number(self):
        cases=[([644,902,148,31],1007171),([1118,826,142,22],1345437)]
        for box,expected in cases:
            with self.subTest(expected=expected):
                ocr=Mock();ocr.read.return_value=[]
                self.assertEqual(read_opponent_power(self.image,dict(self.item,box=box),ocr,normalized),expected)

    def test_touching_glyphs_do_not_depend_on_empty_column_splitting(self):
        rgb=self.image[867:895,887:1036,::-1]
        ys,xs=np.where(white_ink(rgb,205))
        numbers=rgb[ys.min():ys.max()+1,xs.min():xs.max()+1]
        mask=white_ink(numbers,190)
        from ranked_vision import split_glyphs
        self.assertLess(len(split_glyphs(mask)),6)
        self.assertEqual(read_white_power(self.image,self.item),960878)

    def test_numeric_conflict_low_score_or_invalid_length_never_calls_templates(self):
        cases=[('960878',.99),('960878',.79),('123',.99),('1234567890',.99)]
        for text,score in cases:
            with self.subTest(text=text,score=score):
                ocr=Mock();ocr.read.side_effect=[[],[],[{'text':text,'score':score}],[],[]]
                with patch('ranked_vision.read_white_power',side_effect=AssertionError('numeric OCR must block fallback')):
                    with self.assertRaisesRegex(RuntimeError,'不一致'):
                        read_opponent_power(self.image,self.item,ocr,normalized)

    def test_caption_candidate_blocks_templates_when_numeric_views_are_unknown(self):
        item=dict(self.item,text='战斗力:960879')
        ocr=Mock();ocr.read.return_value=[]
        with patch('ranked_vision.read_white_power',side_effect=AssertionError('candidate must not be replaced')):
            with self.assertRaisesRegex(RuntimeError,'不一致'):
                read_opponent_power(self.image,item,ocr,normalized)

    def test_stretched_numeric_conflict_also_blocks_templates(self):
        ocr=Mock();ocr.read.side_effect=[[],[],[],[],
            [{'text':'960878','score':.99}],[{'text':'960879','score':.99}],[]]
        with patch('ranked_vision.read_white_power',side_effect=AssertionError('stretched conflict must not be replaced')):
            with self.assertRaisesRegex(RuntimeError,'不一致'):
                read_opponent_power(self.image,self.item,ocr,normalized)

    def test_unresolved_saved_font_shapes_remain_unknown(self):
        image=np.array(Image.open(ROOT/'resources/local/ranked-1920-calibration.png').convert('RGB'))[:,:,::-1].copy()
        # Preserved 1313308 cannot satisfy the strict two-mask shape criteria;
        # the fallback must not promote its weaker 1313368 alternative.
        # The exact archived caption box is resolved once by the real OCR.
        ocr=LocalOCR()
        item=next(i for i in ocr.read(image) if '1313308' in i['text'])
        self.assertIsNone(read_white_power(image,item))
        unknown=Mock();unknown.read.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'不一致'):
            read_opponent_power(image,dict(item,text='战斗力:%'),unknown,normalized)

    def test_pure_numeric_caption_with_low_score_blocks_templates(self):
        ocr=Mock();ocr.read.return_value=[]
        for text in ('战斗力:960878','960878','战斗力:1234567890'):
            with self.subTest(text=text):
                with patch('ranked_vision.read_white_power',side_effect=AssertionError('low score is not permission to guess')):
                    with self.assertRaisesRegex(RuntimeError,'不一致'):
                        read_opponent_power(self.image,dict(self.item,text=text,score=.79),ocr,normalized)

    def test_unknown_blank_solid_and_wrong_size_pixels_are_rejected(self):
        for kind in ('blank','solid','occluded','large_font'):
            with self.subTest(kind=kind):
                image=self.image.copy()
                if kind=='blank':image[867:895,887:1036]=0
                elif kind=='solid':image[867:895,887:1036]=255
                elif kind=='occluded':image[877:883,961:1023]=0
                else:
                    image[867:895,887:1036]=0
                    image[868:893,970:1020]=255
                self.assertIsNone(read_white_power(image,self.item))

    def test_unverified_or_missing_template_bank_cannot_supply_a_value(self):
        with patch('ranked_vision.white_power_templates',return_value=()):
            self.assertIsNone(read_white_power(self.image,self.item))
        white_power_templates.cache_clear()
        try:
            with patch('pathlib.Path.read_bytes',return_value=b'changed pixels'):
                self.assertEqual(white_power_templates(),())
        finally:white_power_templates.cache_clear()
        self.assertEqual({d for d,_ in white_power_templates()},set('0123456789'))

    def test_weak_ambiguous_disagreeing_and_leading_zero_shapes_are_rejected(self):
        good=[(.30,'960878',.70)]
        for results in (([(.351,'960878',.70)],good),
                        ([(.30,'960878',.54)],good),
                        ([(.30,'960878',.70),(.32,'960879',.70)],good),
                        (good,[(.30,'960879',.70)]),
                        ([(.30,'060878',.70)],good)):
            with self.subTest(results=results):
                with patch('ranked_vision.white_digit_candidates',side_effect=results):
                    self.assertIsNone(read_white_power(self.image,self.item))

    def test_digit_search_has_no_path_for_blank_or_unknown_rectangles(self):
        for mask in (np.zeros((13,53),dtype=bool),np.ones((13,53),dtype=bool)):
            self.assertEqual(white_digit_candidates(mask,white_power_templates()),[])

    def test_template_recovery_still_requires_two_distinct_pipeline_frames(self):
        from ranked_numbers import read_opponent
        ocr=LocalOCR()
        flow=LocalFlows(Mock(),ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
        session=RankedSession(flow)
        unknown=Mock();unknown.read.return_value=[{'text':'9%0878','score':.95}]
        def read(image,button,reader):
            if 900<button['box'][0]<1000:
                return read_opponent(image,button,unknown)
            return read_opponent(image,button,reader)
        with patch('local_flows.read_opponent',side_effect=read):
            session.frame_seq=1
            self.assertFalse(session.recognize('stable',self.image))
            session.frame_seq=2
            self.assertTrue(session.recognize('stable',self.image))
        self.assertEqual(session.state[:2],(2,569821))
        self.assertEqual([o['power'] for o in session.state[2]],[1109537,1007171,960878,1345437,690256])
        self.assertGreaterEqual(unknown.read.call_count,4)
        flow.window.click.assert_not_called()


if __name__=='__main__':
    unittest.main()
