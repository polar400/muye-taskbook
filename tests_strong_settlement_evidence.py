"""Read-only reproduction of the 2026-11-05 strong settlement failure."""
import json
import re
import unittest
from pathlib import Path

from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '出错任务/强者降临/证据/2ba1d650762f427c6ffceb43.png'


class StrongSettlementEvidenceTests(unittest.TestCase):
    def test_archived_victory_has_full_frame_typo_and_readable_local_confirm(self):
        ocr = LocalOCR()
        image = np.array(Image.open(SOURCE).convert('RGB'))[:, :, ::-1].copy()
        full = ocr.read(image)
        crop = ocr.read(image[304:730, 576:1344].copy())
        exact = lambda words: [m for m in words if re.fullmatch(r'确定|确认', m['text'].strip())]
        self.assertEqual(exact(full), [])
        typo = [m for m in full if m['text'] == '确订']
        self.assertEqual(len(typo), 1)
        confirm = exact(crop)
        self.assertEqual(len(confirm), 1)
        self.assertGreater(confirm[0]['score'], .98)
        self.assertTrue(ocr.match(image, 'victory'))
        print(json.dumps({'source': str(SOURCE.relative_to(ROOT)),
                          'full_frame_typo': typo, 'local_confirm': confirm,
                          'crop_xyxy': [576, 304, 1344, 730],
                          'production_fixed': False}, ensure_ascii=True))


if __name__ == '__main__':
    unittest.main()
