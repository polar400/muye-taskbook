"""Non-claim rewards are skipped; no OCR wording may block this policy."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from adapters.local_ocr import LocalOCR
import numpy as np
from welfare_vision import WelfareVision, BUTTONS, load
from welfare_task import WelfareTask
from tests_welfare import FakeWindow, FakeVision, FakeOCR

ROOT = Path(__file__).resolve().parents[1]
RUNS = ('welfare-20261027-164018-d4431784', 'welfare-20261027-164314-6955d573',
        'welfare-20261027-164444-d37735b2')


class SkipImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = WelfareVision(LocalOCR())

    def test_actual_recharge_frames_skip_without_ocr(self):
        with patch.object(self.vision.ocr, 'read', side_effect=AssertionError('按钮OCR不应决定跳过')):
            for run in RUNS:
                path = sorted((ROOT/'verification'/run).glob('*.png'))[-1]
                image = np.array(Image.open(path).convert('RGB'))[:, :, ::-1].copy()
                with self.subTest(run=run):
                    result = self.vision.button(image, 'large_monthly')
                    self.assertEqual(result['state'], 'unavailable')
                    self.assertNotIn('point', result)

    def test_no_claim_template_skips_even_without_readable_text(self):
        image = load('reference-3')[150:1165, 45:1965].copy()
        l, t, r, b = BUTTONS['large_monthly']
        image[t:b, l:r] = 0
        with patch.object(self.vision.ocr, 'read', side_effect=AssertionError('不需要按钮OCR')):
            result = self.vision.button(image, 'large_monthly')
        self.assertEqual(result['state'], 'unavailable')
        self.assertFalse(result['received'])

    def test_non_welfare_page_still_stops(self):
        with self.assertRaises(RuntimeError):
            self.vision.button(np.zeros((1015, 1920, 3), dtype=np.uint8), 'large_monthly')


class SkipFlowTests(unittest.TestCase):
    def task(self, folder, vision):
        window = FakeWindow()
        task = WelfareTask(window, FakeOCR(), folder, vision=vision, emit=lambda text: None)
        task.pause = lambda seconds: None
        return task, window

    def test_recharge_slot_not_clicked_and_later_rewards_continue(self):
        class RechargeVision(FakeVision):
            def button(self, image, slot):
                if slot == 'large_monthly':
                    return {'state': 'unavailable', 'text': '充值', 'received': False}
                return super().button(image, slot)
        with tempfile.TemporaryDirectory(prefix='welfare-skip-', dir=ROOT/'verification') as folder:
            task, window = self.task(folder, RechargeVision())
            report = task.run()
        self.assertEqual(report['status'], 'done')
        self.assertNotIn((11, 0), window.inputs)
        self.assertIn((12, 0), window.inputs)
        self.assertIn((16, 0), window.inputs)
        self.assertEqual(window.page, 'home')

    def test_nonclaim_after_click_is_not_false_receipt(self):
        class NoReceiptVision(FakeVision):
            def button(self, image, slot):
                result = super().button(image, slot)
                if result['state'] == 'unavailable':
                    result['received'] = False
                return result
        with tempfile.TemporaryDirectory(prefix='welfare-skip-', dir=ROOT/'verification') as folder:
            task, window = self.task(folder, NoReceiptVision())
            window.page = 'daily'
            task.claim('large_monthly')
            result = task.report['rewards'][0]
        self.assertEqual(window.inputs, [(11, 0)])
        self.assertEqual(result['status'], 'claim_sent')


if __name__ == '__main__':
    unittest.main(verbosity=2)
