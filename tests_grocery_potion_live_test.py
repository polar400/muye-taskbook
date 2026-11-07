"""Offline potion evidence replay. No live input is permitted."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from tools import grocery_potion_live_test as probe
from grocery_vision import GroceryVision,GroceryRecognitionError
from grocery_recognition import GroceryRecognizer,np

ROOT=Path(__file__).resolve().parent
EVIDENCE=ROOT/'verification/grocery-potion-live-20261031'


class NeverInput:
    def __init__(self,image=None):self.image=image;self.captures=0
    def capture(self):
        self.captures+=1
        if self.image is None:raise AssertionError('No capture allowed')
        return np.asarray(self.image)[:,:,::-1].copy()
    def click(self,*args):raise AssertionError('No input in offline replay')
    def hold(self,*args,**kwargs):raise AssertionError('No input in offline replay')


class PotionLiveTest(unittest.TestCase):
    def test_recorded_purchase_and_confirmation_cannot_replay(self):
        for label in ('buy-one-potion','confirm-one-potion'):
            with self.subTest(label=label),tempfile.TemporaryDirectory(dir=ROOT/'verification') as temp:
                folder=Path(temp);(folder/'input-journal.json').write_text(json.dumps({'actions':[{'label':label}]}),encoding='utf-8')
                w=NeverInput()
                with patch.object(probe,'FOLDER',folder),patch.object(probe.common,'active_worker_check'):
                    with self.assertRaisesRegex(RuntimeError,'禁止重放'):
                        probe.send(w,label,EVIDENCE/'preflight-2.png',[(0,0,20,20)],(10,10))
                self.assertEqual(w.captures,0)

    def test_both_directions_require_exact_1_6_seconds(self):
        for direction in ('up','down'):
            for duration in (None,.08,.2,.5,1.0,2.0):
                with self.subTest(direction=direction,duration=duration),tempfile.TemporaryDirectory(dir=ROOT/'verification') as temp:
                    w=NeverInput()
                    with patch.object(probe,'FOLDER',Path(temp)),patch.object(probe.common,'active_worker_check'):
                        with self.assertRaisesRegex(RuntimeError,'向上向下滑动必须1.6秒'):
                            probe.send(w,f'scroll-{direction}-1600ms-test',EVIDENCE/'02-current.png',
                                       [probe.ARROW_BOXES[direction]],probe.ARROW_POINTS[direction],duration)
                    self.assertEqual(w.captures,0)

    def test_actual_potion_preflight_reads_live_stock_not_web_reference(self):
        with Image.open(EVIDENCE/'preflight-2.png') as image:
            row=probe.fields(GroceryVision(),GroceryRecognizer(),image.convert('RGB'),[967,668,88,88])
        self.assertEqual(row['name'],'修行药水')
        self.assertEqual((row['quantity'],row['unit_price'],row['stock']),(1,200,80))
        self.assertEqual(row['balances']['moon'],360880)

    def test_actual_confirmation_is_one_potion_at_200(self):
        with Image.open(EVIDENCE/'confirmation-2.png') as image:
            w=NeverInput(image.convert('RGB'));row=probe.confirmation(w,persist=False)
        self.assertEqual((row['name'],row['quantity'],row['total']),('修行药水',1,200))

    def test_post_stock_is_79_and_low_confidence_balance_is_rejected(self):
        with Image.open(EVIDENCE/'confirm-one-potion-after.png') as source:
            image=source.convert('RGB');v=GroceryVision()
            text,_=v.read_text(image,(1062,719,112,32),r'库存(?:0|[1-9][0-9]{0,7})')
            self.assertEqual(text,'库存79')
            with self.assertRaises(GroceryRecognitionError):probe.common.read_test_balances(v,image)


if __name__=='__main__':unittest.main()
