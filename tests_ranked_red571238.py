"""Nov 6 own-power regressions using original pixels; no game input."""
from pathlib import Path
from unittest.mock import Mock
import hashlib
import json
import unittest

from adapters.local_ocr import LocalOCR
from ranked_vision import read_red_power,split_glyphs
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent
FRAMES=['verification/failure-20261106-005541-308d39bb9a19-ranked.png',
        'verification/failure-20261106-005612-02e7419ac0d1-ranked.png']


def load(name):return np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()


def source_glyphs(image):
    h,w=image.shape[:2]
    rgb=image[int(h*.084):int(h*.145),int(w*.09):int(w*.27),::-1].astype('float32')
    r,g,b=rgb.transpose(2,0,1)
    return split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))


class RankedRed571238Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def test_both_real_failures_read_571238(self):
        for name in FRAMES:
            with self.subTest(frame=name):self.assertEqual(read_red_power(load(name),self.ocr),571238)

    def test_added_glyphs_can_read_a_different_power_without_numeric_ocr(self):
        glyphs=source_glyphs(load(FRAMES[0]))
        image=np.zeros((1015,1920,3),dtype='uint8')
        x=200
        # Reorder actual source masks to prove that no whole-power lookup is used.
        for index in (0,5,2,3,4,1):
            glyph=glyphs[index];h,w=glyph.shape
            image[90:90+h,x:x+w,2]=np.where(glyph,255,0)
            x+=w+5
        ocr=Mock();ocr.read.side_effect=AssertionError('verified shapes must not need OCR')
        self.assertEqual(read_red_power(image,ocr),581237)
        ocr.read.assert_not_called()

    def test_damaged_unknown_glyph_still_stops(self):
        image=load(FRAMES[0]);h,w=image.shape[:2]
        # Destroy a broad band across the artwork, leaving unverified shapes.
        image[105:113,int(w*.09):int(w*.27)]=0
        ocr=Mock();ocr.read.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'我方战力'):read_red_power(image,ocr)

    def test_template_pixels_and_sources_match_manifest(self):
        manifest=json.loads((ROOT/'resources/local/ranked-red571238-sources.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['annotation'],'571238')
        for source in manifest['sources']:
            path=ROOT/source['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),source['sha256'])
            glyphs=source_glyphs(load(source['path']))
            for row in manifest['templates']:
                path=ROOT/row['path'];pixels=np.array(Image.open(path).convert('L'))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
                self.assertTrue(np.array_equal(pixels,np.where(glyphs[row['glyphIndex']],0,255).astype('uint8')))


if __name__=='__main__':unittest.main()
