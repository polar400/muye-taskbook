"""Offline replay of the single-key test evidence. Never sends game input."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import grocery_key_live_test as probe
from grocery_vision import GroceryVision
from grocery_recognition import np
from PIL import Image

ROOT=Path(__file__).resolve().parent
EVIDENCE=ROOT/'verification/grocery-key-live-20261031'


class NeverInput:
    def __init__(self, image=None): self.image=image; self.captures=0; self.clicks=0
    def capture(self):
        self.captures+=1
        if self.image is None: raise AssertionError('Capture must not occur')
        return np.asarray(self.image)[:,:,::-1].copy()
    def click(self,*args):
        self.clicks+=1
        raise AssertionError('Offline checks must never click')


class GrocerySingleKeyTest(unittest.TestCase):
    def test_recorded_buy_or_confirm_can_never_be_replayed(self):
        for label in ('buy-one-key','confirm-one-key'):
            with self.subTest(label=label), tempfile.TemporaryDirectory(dir=ROOT/'verification') as temp:
                folder=Path(temp)
                (folder/'input-journal.json').write_text(json.dumps({'actions':[{'label':label}]}),encoding='utf-8')
                window=NeverInput()
                with patch.object(probe,'FOLDER',folder),patch.object(probe,'active_worker_check'):
                    with self.assertRaisesRegex(RuntimeError,'禁止自动重放'):
                        probe.guarded_click(window,EVIDENCE/'key-preflight-2.png',(0,0,20,20),(10,10),label,True)
                self.assertEqual(window.captures,0)
                self.assertEqual(window.clicks,0)

    def test_buy_and_confirm_cannot_bypass_consumption_flag(self):
        for label in ('buy-one-key','confirm-one-key'):
            window=NeverInput()
            with patch.object(probe,'active_worker_check'):
                with self.assertRaisesRegex(RuntimeError,'单次消费校验'):
                    probe.guarded_click(window,EVIDENCE/'key-preflight-2.png',(0,0,20,20),(10,10),label,False)
            self.assertEqual(window.captures,0)

    def test_changed_page_blocks_click_before_journal_write(self):
        with Image.open(EVIDENCE/'02-current.png') as image, tempfile.TemporaryDirectory(dir=ROOT/'verification') as temp:
            folder=Path(temp);window=NeverInput(image.convert('RGB'))
            with patch.object(probe,'FOLDER',folder),patch.object(probe,'active_worker_check'):
                with self.assertRaisesRegex(RuntimeError,'画面与已核对证据不一致'):
                    probe.guarded_click(window,EVIDENCE/'01-current.png',(1500,170,65,65),(1532,201),'stale-offer')
            self.assertEqual(window.clicks,0)
            self.assertFalse((folder/'input-journal.json').exists())

    def test_actual_before_after_currency_reads_are_exact(self):
        vision=GroceryVision()
        for filename,moon in (('key-preflight-2.png',361080),('confirm-one-key-after.png',360880)):
            with self.subTest(filename=filename),Image.open(EVIDENCE/filename) as image:
                balances,_=probe.read_test_balances(vision,image.convert('RGB'))
                self.assertEqual(balances,{'sun':13609,'moon':moon,'sign':9600,'mystery':321})

    def test_actual_confirmation_contains_one_key_and_exact_total(self):
        with Image.open(EVIDENCE/'confirmation-preflight-2.png') as image:
            window=NeverInput(image.convert('RGB'))
            result=probe.observe_confirmation(window,persist=False)
        self.assertEqual((result['quantity'],result['total']),(1,200))
        self.assertEqual(window.clicks,0)


if __name__=='__main__':unittest.main()
