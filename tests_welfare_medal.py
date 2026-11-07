"""Medal claim regression from the actual skipped reward, without live game input."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image
from adapters.local_ocr import LocalOCR
import numpy as np
from welfare_vision import WelfareVision, BUTTONS
from welfare_task import WelfareTask
ROOT = Path(__file__).resolve().parent
RUN = ROOT/'verification/welfare-20261105-233044-4da3a7f2'
def frame(name='021.png'):
    return np.array(Image.open(RUN/name).convert('RGB'))[:, :, ::-1].copy()
class MedalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = WelfareVision(LocalOCR())
    def test_actual_skipped_medal_is_claimable(self):
        for name in ('020.png', '021.png', '025.png', '035.png', '045.png'):
            with self.subTest(frame=name):
                result = self.vision.button(frame(name), 'medal_daily')
                self.assertEqual(result['state'], 'claimable')
                x,y = result['point']
                self.assertTrue(1240 < x < 1400 and 540 < y < 600)
    def test_grey_weekly_and_paid_buttons_are_skipped(self):
        for slot in ('monthly', 'large_monthly', 'medal_weekly'):
            self.assertEqual(self.vision.button(frame(), slot)['state'], 'unavailable')
    def test_simulated_daily_claim_sent_once(self):
        current=[frame()]
        after=frame()
        l,t,r,b=BUTTONS['medal_daily']
        after[t:b,l:r]=np.mean(after[t:b,l:r],axis=2,keepdims=True).astype(np.uint8)
        self.assertEqual(self.vision.button(after,'medal_daily')['state'],'unavailable')
        window=Mock()
        window.capture.side_effect=lambda:current[0]
        window.click.side_effect=lambda x,y:current.__setitem__(0,after)
        with tempfile.TemporaryDirectory(prefix='welfare-medal-',dir=ROOT/'verification') as folder:
            task=WelfareTask(window,self.vision.ocr,folder,vision=self.vision,emit=lambda text:None)
            task.pause=lambda seconds:None
            task.claim('medal_daily')
            self.assertEqual(task.report['rewards'][0]['status'],'claim_sent')
        window.click.assert_called_once()
    def test_dimmed_panel_not_claimable(self):
        with self.assertRaises(RuntimeError):
            self.vision.button((frame()*.45).astype(np.uint8),'medal_daily')
if __name__=='__main__':
    unittest.main(verbosity=2)
