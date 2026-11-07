"""Nov 6 opponent regressions: original pixels and simulated game input only."""
from pathlib import Path
from unittest.mock import Mock
import unittest

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_numbers import NumberRecognitionError,opponent_region,read_opponent,shape_reading
from ranked_pipeline import RankedSession,run_ranked_pipeline
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent
FRAMES=['verification/failure-20261106-005541-308d39bb9a19-ranked.png',
        'verification/failure-20261106-005612-02e7419ac0d1-ranked.png']
POWERS=[1499302,1455783,1313308,2350943,715530]


class RankedOpponentNov6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR();cls.flows=[]
        for name in FRAMES:
            flow=LocalFlows(Mock(),cls.ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
            flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
            flow.items=cls.ocr.read(flow.image);cls.flows.append(flow)

    def test_both_original_panels_read_all_values_without_input(self):
        for flow in self.flows:
            with self.subTest(frame=FRAMES[self.flows.index(flow)]):
                count,own,opponents=flow.ranked_state()
                self.assertEqual((count,own),(7,571238))
                self.assertEqual([o['power'] for o in opponents],POWERS)
                flow.window.click.assert_not_called()

    def test_real_12px_four_preserves_diagonal_and_matches_both_views(self):
        flow=self.flows[1]
        buttons=sorted([i for i in flow.items if i['text']=='挑战' and i['box'][1]>550],key=lambda i:i['box'][0])
        rgb,_=opponent_region(flow.image,buttons[3])
        # The source bright core is 12px; recovered grey edges may add rows.
        shape=shape_reading(rgb)
        self.assertEqual(shape['value'],2350943)
        self.assertTrue(all(v.get('value')==2350943 and v['meanIoU']>=.8
                            and v['minimumIoU']>=.65 and v['lead']>=.08 for v in shape['views']))

    def test_real_first_opponent_still_rejects_conflicting_numeric_ocr(self):
        flow=self.flows[1]
        button=min([i for i in flow.items if i['text']=='挑战' and i['box'][1]>550],key=lambda i:i['box'][0])
        ocr=Mock();ocr.read.side_effect=[[{'text':'1499302','score':.99}],
                                       [{'text':'149930','score':.99}]]
        with self.assertRaisesRegex(NumberRecognitionError,'冲突'):
            read_opponent(flow.image,button,ocr)
        self.assertEqual(ocr.read.call_count,2)

    def test_damaged_numeric_ink_cannot_be_rescued_by_repeated_ocr(self):
        flow=self.flows[1]
        button=min([i for i in flow.items if i['text']=='挑战' and i['box'][1]>550],key=lambda i:i['box'][0])
        image=flow.image.copy();x,y,r,b=opponent_region(image,button)[1]
        image[y+3:y+9,x:r]=0
        ocr=Mock();ocr.read.return_value=[{'text':'1499302','score':.99}]
        with self.assertRaises(NumberRecognitionError):read_opponent(image,button,ocr)

    def test_current_pixels_drive_stable_preflight_and_one_simulated_round(self):
        from tests_ranked_pipeline import Game,FAST
        flow=self.flows[1];session=RankedSession(flow)
        session.frame_seq=1
        self.assertFalse(session.recognize('stable',flow.image))
        self.assertFalse(session.recognize('stable',flow.image))
        session.frame_seq=2
        self.assertTrue(session.recognize('stable',flow.image))
        # The returned 6-count panel is an independently archived older frame;
        # page transitions/results/input are simulated, not a live-game claim.
        returned=LocalFlows(Mock(),self.ocr,flow.cfg,lambda:None,Mock())
        returned.image=np.array(Image.open(ROOT/'resources/local/ranked-remaining6-1920.png').convert('RGB'))[:,:,::-1].copy()
        returned.items=self.ocr.read(returned.image)
        game=Game(count=7,results=('victory',),limit=1)
        game.cfg.update(rankedServer='连服',tolerance=1000);game.server='连服'
        readings=[]
        def actual_state():
            selected=flow if game.count==7 else returned
            count,own,opponents=selected.ranked_state()
            self.assertEqual(count,game.count);readings.append((count,own))
            for opponent in opponents:opponent['button']=dict(opponent['button'],type='challenge')
            return count,own,opponents
        game.ranked_state=actual_state
        run_ranked_pipeline(game,pipeline_override=FAST)
        self.assertEqual(game.inputs,['challenge','end','confirm','close'])
        self.assertEqual((game.page,game.count),('home',6))
        self.assertIn((7,571238),readings)
        self.assertTrue(any(e.get('status')=='done' and e.get('completed')==1 for e in game.events))
        flow.window.click.assert_not_called();returned.window.click.assert_not_called()
        game.window.click.assert_not_called()


if __name__=='__main__':unittest.main()
