"""Real failed entry frames are holdouts: templates use only the original attachment."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

from adapters.local_ocr import LocalOCR
import numpy as np
from welfare_vision import WelfareVision, load
from welfare_task import WelfareTask

ROOT = Path(__file__).resolve().parents[1]
RUNS = ('welfare-20261027-005740-a146eb9d', 'welfare-20261027-010028-333dd707',
        'welfare-20261027-010200-a5e92b7a', 'welfare-20261027-012409-3895c8e3',
        'welfare-20261027-012424-6420f2a0', 'welfare-20261027-012555-03024030')


def frame(run, name='002.png'):
    return np.array(Image.open(ROOT/'verification'/run/name).convert('RGB'))[:, :, ::-1].copy()


class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = LocalOCR()
        cls.vision = WelfareVision(cls.ocr)

    def test_twelve_actual_failed_frames_find_one_entry(self):
        for run in RUNS:
            for name in ('001.png', '002.png'):
                with self.subTest(run=run, frame=name):
                    self.assertEqual(self.vision.unique(frame(run, name), 'entry'), [1452, 199, 109, 112])

    def test_real_failure_frame_enters_panel_once_in_simulation(self):
        current = [frame(RUNS[-1])]
        window = Mock()
        window.capture.side_effect = lambda: current[0]
        window.click.side_effect = lambda x, y: current.__setitem__(0, load('reference-3')[150:1165, 45:1965].copy())
        with tempfile.TemporaryDirectory(prefix='welfare-entry-', dir=ROOT/'verification') as folder:
            task = WelfareTask(window, self.ocr, folder, vision=self.vision, emit=lambda text: None)
            task.pause = lambda seconds: None
            task.open()
        window.click.assert_called_once_with(1506, 255)

    def test_november_actual_entry_frames(self):
        for run in ('welfare-20261105-231828-a34f23bf', 'welfare-20261105-231842-42b02a96'):
            for name in ('001.png', '002.png'):
                with self.subTest(run=run, frame=name):
                    self.assertEqual(self.vision.unique(frame(run, name), 'entry'), [1363, 199, 109, 112])

    def test_november_entry_requires_both_anchors(self):
        run = 'welfare-20261105-231842-42b02a96'
        for box in ((1388, 218, 1448, 282), (1380, 284, 1461, 305)):
            image = frame(run)
            l, t, r, b = box
            image[t:b, l:r] = 0
            self.assertFalse(self.vision.matches(image, 'entry'))
        image = frame(run)
        image[199:311, 1163:1272] = image[199:311, 1363:1472].copy()
        with self.assertRaises(RuntimeError):
            self.vision.unique(image, 'entry')
        self.assertFalse(self.vision.matches((frame(run)*.45).astype(np.uint8), 'entry'))

    def test_november_entry_opens_once_in_simulation(self):
        current = [frame('welfare-20261105-231842-42b02a96')]
        window = Mock()
        window.capture.side_effect = lambda: current[0]
        window.click.side_effect = lambda x, y: current.__setitem__(0, load('reference-3')[150:1165, 45:1965].copy())
        with tempfile.TemporaryDirectory(prefix='welfare-entry-', dir=ROOT/'verification') as folder:
            task = WelfareTask(window, self.ocr, folder, vision=self.vision, emit=lambda text: None)
            task.pause = lambda seconds: None
            task.open()
        window.click.assert_called_once_with(1417, 255)

    def test_november_title_must_align_with_gift(self):
        image = frame('welfare-20261105-231842-42b02a96')
        title = image[284:305, 1380:1461].copy()
        image[284:305, 1380:1461] = 0
        image[284:305, 1390:1471] = title
        self.assertFalse(self.vision.matches(image, 'entry'))

    def test_duplicate_entry_is_ambiguous(self):
        image = frame(RUNS[-1])
        image[199:311, 1152:1261] = image[199:311, 1452:1561].copy()
        self.assertEqual(len(self.vision.matches(image, 'entry')), 2)
        with self.assertRaises(RuntimeError):
            self.vision.unique(image, 'entry')

    def test_missing_gift_or_label_cannot_be_clicked(self):
        for box in ((1477, 218, 1537, 282), (1469, 284, 1550, 305)):
            image = frame(RUNS[-1])
            l, t, r, b = box
            image[t:b, l:r] = 0
            self.assertFalse(self.vision.matches(image, 'entry'))

    def test_dimmed_background_cannot_be_clicked(self):
        image = (frame(RUNS[-1]).astype(float)*.45).astype(np.uint8)
        self.assertFalse(self.vision.matches(image, 'entry'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
