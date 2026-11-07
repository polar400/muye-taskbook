"""Survival reset regressions; real OCR, reference glyphs and mocked game IO."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NEW = ('verification/failure-20261106-130948-38ab273018a5-survival.png',
       'verification/failure-20261106-131219-d075bd87471e-survival.png')


class ResetImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = LocalOCR()

    def flow(self, path):
        flow = LocalFlows(Mock(), self.ocr, {'reset':True}, lambda:None, Mock())
        flow.image = np.array(Image.open(ROOT / path).convert('RGB'))[:,:,::-1].copy()
        flow.items = self.ocr.read(flow.image)
        return flow

    def test_new_failures_read_reset_one_despite_missing_ocr_digit(self):
        for path in NEW:
            with self.subTest(path=path):
                flow = self.flow(path)
                self.assertFalse(any('1' in i['text'] for i in flow.hits('重置')))
                self.assertFalse(flow.ocr.match(flow.image, 'survival_reset1', threshold=.94))
                self.assertEqual(flow.survival_points(), (220,220))
                count,button = flow.survival_reset_state()
                self.assertEqual(count, 1)
                self.assertTrue(button['box'][1] > 800)
                flow.window.click.assert_not_called()

    def test_historical_zero_one_normal_and_elite(self):
        for path,count in (
            ('resources/local/survival-calibration.png',1),
            ('resources/local/survival-reset-calibration.png',0),
            ('resources/local/survival-reset1-1920-calibration.png',1),
            ('resources/local/survival-1920-calibration.png',0),
            ('resources/local/survival-1920-shifted-calibration.png',0),
            ('verification/failure-20261018-234702-3aa6ed0d9603-survival.png',0)):
            with self.subTest(path=path):
                self.assertEqual(self.flow(path).survival_reset_state()[0], count)

    def test_numeric_fallback_handles_both_known_digits_without_full_templates(self):
        for path,count in ((NEW[0],1), ('resources/local/survival-1920-calibration.png',0)):
            with self.subTest(count=count):
                flow = self.flow(path)
                flow.items = [dict(flow.hits('重置')[0], text='重置（剩余次)')]
                with patch.object(self.ocr,'match',return_value=[]):
                    self.assertEqual(flow.survival_reset_state()[0],count)

    def test_missing_or_damaged_glyph_never_becomes_one_or_zero(self):
        for corruption in ('erase','block'):
            with self.subTest(corruption=corruption):
                flow = self.flow(NEW[0])
                flow.image[935:969,1102:1115] = 0
                if corruption=='block':flow.image[945:959,1105:1113] = 255
                with patch.object(self.ocr,'match',return_value=[]):
                    with self.assertRaisesRegex(RuntimeError,'重置'):
                        flow.survival_reset_state()
                flow.window.click.assert_not_called()

    def test_duplicate_weak_or_misplaced_anchor_is_rejected(self):
        for variant in ('duplicate','weak','chat'):
            with self.subTest(variant=variant):
                flow = self.flow(NEW[0]);item=flow.hits('重置')[0]
                if variant=='duplicate':flow.items=[item,item]
                elif variant=='weak':flow.items=[dict(item,score=.79)]
                else:flow.items=[dict(item,box=[100,100,168,34])]
                with patch.object(self.ocr,'match',return_value=[]):
                    with self.assertRaisesRegex(RuntimeError,'重置'):
                        flow.survival_reset_state()
                flow.window.click.assert_not_called()

    def test_stable_ready_does_not_skip_full_points_with_one_reset(self):
        flow = self.flow(NEW[0]);flow.observe=Mock()
        def wait(predicate,seconds):
            with patch('local_flows.time.monotonic',side_effect=[0,1]):
                self.assertFalse(predicate());self.assertTrue(predicate())
        flow.wait=wait
        flow.wait_survival_ready()
        flow.window.click.assert_not_called()

    def test_reset_rechecks_frame_and_waits_for_zero_after_single_click(self):
        flow = self.flow(NEW[0])
        zero=self.flow('resources/local/survival-1920-calibration.png')
        events=[]
        flow.observe=Mock(side_effect=lambda: events.append('observe'))
        flow.window.click.side_effect=lambda *args:events.append('click')
        def wait(predicate):
            self.assertFalse(predicate())
            flow.image,flow.items=zero.image,zero.items
            self.assertTrue(predicate())
        flow.wait=wait
        with patch('local_flows.time.sleep'):flow.survival_reset()
        self.assertEqual(events[:2],['observe','click'])
        flow.window.click.assert_called_once()
        self.assertTrue(flow._survival_reset_done)

    def test_fresh_zero_prevents_sending_reset(self):
        flow = self.flow(NEW[0]);zero=self.flow('resources/local/survival-1920-calibration.png')
        def observe():flow.image,flow.items=zero.image,zero.items
        flow.observe=Mock(side_effect=observe)
        with self.assertRaisesRegex(RuntimeError,'变化'):flow.survival_reset()
        flow.window.click.assert_not_called()

    def test_conflicting_legacy_evidence_is_rejected(self):
        flow=self.flow(NEW[0])
        flow.items=[dict(flow.hits('重置')[0],text='重置（剩余0次)')]
        with patch.object(self.ocr,'match',side_effect=lambda image,name,**kw:
                          [{'box':[979,928,178,45]}] if name=='survival_reset1' else []):
            with self.assertRaisesRegex(RuntimeError,'重置'):flow.survival_reset_state()
        flow.window.click.assert_not_called()

    def test_small_translation_does_not_break_local_glyph_read(self):
        for dx,dy in ((-2,1),(2,-1)):
            with self.subTest(dx=dx,dy=dy):
                flow=self.flow(NEW[0]);anchor=flow.hits('重置')[0]
                flow.image=np.roll(flow.image,(dy,dx),axis=(0,1))
                x,y,w,h=anchor['box'];flow.items=[dict(anchor,box=[x+dx,y+dy,w,h])]
                with patch.object(self.ocr,'match',return_value=[]):
                    self.assertEqual(flow.survival_reset_state()[0],1)

    def test_multiple_local_digits_and_invalid_numeric_text_are_rejected(self):
        for variant in ('two_digits','unexpected_count'):
            with self.subTest(variant=variant):
                flow=self.flow(NEW[0]);anchor=flow.hits('重置')[0]
                if variant=='unexpected_count':flow.items=[dict(anchor,text='重置（剩余2次)')]
                else:
                    glyph=flow.image[941:964,1103:1115].copy()
                    flow.image[935:970,1099:1125]=0
                    flow.image[941:964,1099:1111]=glyph
                    flow.image[941:964,1112:1124]=glyph
                with patch.object(self.ocr,'match',return_value=[]):
                    with self.assertRaisesRegex(RuntimeError,'重置'):flow.survival_reset_state()
                flow.window.click.assert_not_called()

    def test_real_post_reset_grey_zero_accepts_ocr_punctuation_variants(self):
        path='verification/survival-reset-20261106/live-final.png'
        flow=self.flow(path)
        self.assertEqual(flow.survival_points(),(60,220))
        self.assertEqual(flow.survival_reset_state()[0],0)
        anchor=flow.hits('重置')[0]
        for text in ('重置【剩余0次)','重置［剩余0次］','重置（余0次）'):
            with self.subTest(text=text):
                flow.items=[dict(anchor,text=text)]
                self.assertEqual(flow.survival_reset_state()[0],0)
        flow.window.click.assert_not_called()

    def test_grey_zero_glyph_remains_readable_when_ocr_omits_digit(self):
        flow=self.flow('verification/survival-reset-20261106/live-final.png')
        flow.items=[dict(flow.hits('重置')[0],text='重置【剩余次)')]
        with patch.object(self.ocr,'match',return_value=[]):
            self.assertEqual(flow.survival_reset_state()[0],0)
        flow.window.click.assert_not_called()

    def test_real_preflight_frame_uses_digit_instead_of_damaged_surrounding_text(self):
        flow=self.flow('verification/survival-reset-20261106/live-continuation-final.png')
        self.assertEqual(flow.survival_points(),(60,220))
        self.assertEqual(flow.survival_reset_state()[0],0)
        flow.window.click.assert_not_called()

    def test_damaged_label_still_rejects_conflicting_count_token(self):
        flow=self.flow('verification/survival-reset-20261106/live-final.png')
        anchor=flow.hits('重置')[0]
        for text in ('重置（困余0次2','重置（困余1次2'):
            with self.subTest(text=text):
                flow.items=[dict(anchor,text=text)]
                if '余0次' in text:self.assertEqual(flow.survival_reset_state()[0],0)
                else:
                    with self.assertRaisesRegex(RuntimeError,'冲突'):flow.survival_reset_state()
        flow.window.click.assert_not_called()


if __name__ == '__main__':unittest.main()
