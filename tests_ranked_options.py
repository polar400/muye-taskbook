"""Ranked scope, bounded attempts, explicit outcomes and refresh policy."""
import unittest
from unittest.mock import Mock,patch
from pathlib import Path
from adapters.local_ocr import LocalOCR
import numpy as np
from PIL import Image
from local_flows import LocalFlows
from ranked_policy import ranked_options

ROOT=Path(__file__).resolve().parent


class RankedPolicyTests(unittest.TestCase):
    def flow(self,cfg=None):
        flow=LocalFlows(Mock(),Mock(),cfg or {},lambda:None,Mock())
        flow.image=np.zeros((1015,1920,3),dtype=np.uint8)
        flow.observe=Mock();flow.ensure_ranked_server=Mock();flow.ranked_panel_visible=Mock(return_value=True)
        flow.close_panel=Mock();flow.click_item=Mock()
        return flow

    def state(self,count,power=100,box=None):
        return count,100,[{'power':power,'button':{'box':box or [400,850,70,30]}}] if count else []

    def test_defaults_migrate_and_invalid_values_stop_before_observation(self):
        self.assertEqual(ranked_options({}),('连服',0))
        self.assertEqual(ranked_options({'rankedServer':'联服','rankedLimit':3}),('连服',3))
        for cfg in ({'rankedServer':'全部'},{'rankedLimit':-1},{'rankedLimit':21},{'rankedLimit':True},{'rankedLimit':1.5}):
            flow=self.flow(cfg)
            with self.assertRaises(ValueError):flow.ranked()
            flow.observe.assert_not_called();flow.window.click.assert_not_called()

    def test_limit_counts_loss_and_skips_refresh_after_last_attempt(self):
        flow=self.flow({'rankedServer':'本服','rankedLimit':1})
        flow.wait_ranked_ready=Mock(side_effect=[self.state(5),self.state(4)])
        flow.finish_ranked_battle=Mock(return_value='defeat');flow.refresh_ranked_after_defeat=Mock()
        flow.ranked()
        flow.ensure_ranked_server.assert_called_once_with('本服')
        flow.finish_ranked_battle.assert_called_once();flow.refresh_ranked_after_defeat.assert_not_called()
        flow.close_panel.assert_called_once()

    def test_available_count_smaller_than_limit_and_default_use_all(self):
        for limit in (0,5):
            flow=self.flow({'rankedLimit':limit})
            flow.wait_ranked_ready=Mock(side_effect=[self.state(1),self.state(0)])
            flow.finish_ranked_battle=Mock(return_value='defeat');flow.refresh_ranked_after_defeat=Mock()
            flow.ranked()
            flow.finish_ranked_battle.assert_called_once();flow.refresh_ranked_after_defeat.assert_not_called()

    def test_failure_refreshes_and_reselects_from_new_opponents(self):
        flow=self.flow()
        new_box=[900,850,70,30]
        flow.wait_ranked_ready=Mock(side_effect=[self.state(2),self.state(1),self.state(1,101,new_box),self.state(0)])
        flow.finish_ranked_battle=Mock(side_effect=['defeat','victory'])
        flow.refresh_ranked_after_defeat=Mock()
        flow.ranked()
        flow.refresh_ranked_after_defeat.assert_called_once()
        self.assertEqual(flow.click_item.call_args_list[-1].args[0]['box'],new_box)

    def test_refresh_cooldown_continues_without_wait_or_refresh_click(self):
        flow=self.flow()
        flow.wait_ranked_ready=Mock(side_effect=[self.state(2),self.state(1),self.state(1),self.state(0)])
        flow.finish_ranked_battle=Mock(side_effect=['defeat','defeat'])
        flow.ranked_refresh_state=Mock(return_value=('cooldown',None));flow.wait=Mock()
        flow.ranked()
        self.assertEqual(flow.click_item.call_count,2)
        flow.wait.assert_not_called()

    def test_refresh_cannot_spend_challenge_or_reuse_stale_state(self):
        flow=self.flow()
        flow.wait_ranked_ready=Mock(side_effect=[self.state(3),self.state(2),self.state(1)])
        flow.finish_ranked_battle=Mock(return_value='defeat');flow.refresh_ranked_after_defeat=Mock()
        with self.assertRaisesRegex(RuntimeError,'刷新后挑战次数'):flow.ranked()
        flow.click_item.assert_called_once()

    def test_decreased_count_checked_even_at_user_limit(self):
        flow=self.flow({'rankedLimit':1})
        flow.wait_ranked_ready=Mock(side_effect=[self.state(2),self.state(2)])
        flow.finish_ranked_battle=Mock(return_value='victory')
        with self.assertRaisesRegex(RuntimeError,'次数未减少'):flow.ranked()
        flow.close_panel.assert_not_called()

    def test_mode_switch_waits_for_two_confirmations(self):
        flow=self.flow();flow.ensure_ranked_server=LocalFlows.ensure_ranked_server.__get__(flow)
        flow.ranked_server_state=Mock(side_effect=['连服','本服','本服'])
        flow.ranked_server_button=Mock(return_value={'box':[1639,4,41,72]})
        def wait(predicate,seconds):
            self.assertFalse(predicate());self.assertTrue(predicate())
        flow.wait=wait;flow.ensure_ranked_server('本服')
        flow.click_item.assert_called_once()

    def test_current_mode_does_not_toggle(self):
        flow=self.flow();flow.ensure_ranked_server=LocalFlows.ensure_ranked_server.__get__(flow)
        flow.ranked_server_state=Mock(return_value='连服')
        flow.ensure_ranked_server('连服');flow.click_item.assert_not_called()

    def test_explicit_outcomes_and_health_cannot_conflict(self):
        for text,wanted in [('失败','defeat'),('胜利','victory')]:
            flow=self.flow();flow.ocr.match.return_value=[]
            flow.ocr.read.side_effect=[[{'text':text}],[],[]]
            self.assertEqual(flow.ranked_battle_result(),wanted)
        flow=self.flow();flow.ocr.match.return_value=[]
        flow.ocr.read.side_effect=[[],[{'text':'0/233479'}],[{'text':'1200/212575'}]]
        self.assertEqual(flow.ranked_battle_result(),'defeat')
        flow=self.flow();flow.ocr.match.return_value=[]
        flow.ocr.read.side_effect=[[{'text':'胜利'}],[{'text':'0/233479'}],[{'text':'1200/212575'}]]
        with self.assertRaisesRegex(RuntimeError,'胜负无法'):flow.ranked_battle_result()

    def test_missing_victory_never_implies_defeat(self):
        flow=self.flow();flow.ocr.match.return_value=[];flow.ocr.read.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'胜负无法'):flow.ranked_battle_result()

    def test_cooldown_has_priority_over_button_art(self):
        flow=self.flow();flow.ocr.match.return_value=[{'box':[100,80,122,46]}]
        for text in ('刷新冷却中','03:25','还需15秒'):
            flow.ocr.read.return_value=[{'text':text}]
            self.assertEqual(flow.ranked_refresh_state(),('cooldown',None))

    def test_unknown_or_paid_refresh_stops_without_next_challenge(self):
        flow=self.flow();flow.ranked_refresh_state=Mock(return_value=('unknown',None))
        with self.assertRaisesRegex(RuntimeError,'无法确认刷新'):flow.refresh_ranked_after_defeat()
        flow.click_item.assert_not_called()
        flow=self.flow();flow.items=[{'text':'消耗元宝购买刷新'}]
        flow.ranked_refresh_state=Mock(return_value=('ready',{'box':[1661,889,122,46]}))
        flow.wait_ranked_ready=Mock(return_value=self.state(1));flow.confirm=Mock()
        flow.wait=lambda predicate,seconds:predicate()
        with self.assertRaisesRegex(RuntimeError,'付费提示'):flow.refresh_ranked_after_defeat()
        flow.confirm.assert_not_called()

    def test_refresh_accepts_two_changed_opponent_states(self):
        flow=self.flow();flow.ranked_refresh_state=Mock(return_value=('ready',{'box':[1661,889,122,46]}))
        flow.wait_ranked_ready=Mock(return_value=self.state(1,150))
        flow.ranked_state=Mock(side_effect=[self.state(1,101),self.state(1,101)])
        def wait(predicate,seconds):
            self.assertFalse(predicate());self.assertTrue(predicate())
        flow.wait=wait;flow.refresh_ranked_after_defeat()
        flow.click_item.assert_called_once()


class RankedControlImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def flow(self,name):
        flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
        flow.image=np.array(Image.open(ROOT/'resources/local'/name).convert('RGB'))[:,:,::-1].copy()
        return flow

    def test_preserved_cross_panel_and_both_switch_targets(self):
        flow=self.flow('ranked-remaining6-live.png')
        self.assertEqual(flow.ranked_server_state(),'连服')
        self.assertGreater(flow.ranked_server_button('本服')['box'][0],1580)
        self.assertGreater(flow.ranked_server_button('连服')['box'][0],1680)
        state,button=flow.ranked_refresh_state()
        self.assertEqual(state,'ready');self.assertGreater(button['box'][1],850)
        flow.window.click.assert_not_called()

    def test_real_victory_settlement_reads_explicit_result(self):
        flow=self.flow('battle-settlement-calibration.png')
        self.assertEqual(flow.ranked_battle_result(),'victory')
        flow.window.click.assert_not_called()

    def test_real_local_panel_title_and_five_opponents(self):
        flow=self.flow('ranked-local-live.png')
        self.assertEqual(flow.ranked_server_state(),'本服')
        flow.items=flow.ocr.read(flow.image)
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(1,565140))
        self.assertEqual([o['power'] for o in opponents],[618173,600720,776157,1589780,1250298])
        flow.window.click.assert_not_called()

    def test_real_refresh_countdown_skips_input_and_waiting(self):
        flow=self.flow('ranked-refresh-cooldown-live.png')
        self.assertEqual(flow.ranked_refresh_state(),('cooldown',None))
        flow.observe=Mock();flow.wait=Mock()
        flow.refresh_ranked_after_defeat()
        flow.window.click.assert_not_called();flow.wait.assert_not_called()


if __name__=='__main__':unittest.main()
