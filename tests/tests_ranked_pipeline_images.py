"""Pipeline recognition callbacks on preserved screenshots; no game IO."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_pipeline import RankedSession
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class PipelineImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = LocalOCR()

    def session(self, name):
        flow = LocalFlows(Mock(),self.ocr,{'rankedServer':'本服','rankedLimit':1},lambda:None,Mock())
        image = np.array(Image.open(ROOT/'resources/local'/name).convert('RGB'))[:,:,::-1].copy()
        flow.image = image
        return RankedSession(flow),image

    def test_stable_counts_and_powers_require_two_real_frames(self):
        session,image = self.session('ranked-local-live.png')
        for seq,expected in ((1,False),(2,True)):
            session.frame_seq = seq
            self.assertEqual(session.recognize('stable',image),expected)
        count,own,opponents = session.state
        self.assertEqual((count,own),(1,565140))
        self.assertEqual([o['power'] for o in opponents],[618173,600720,776157,1589780,1250298])
        session.flow.window.click.assert_not_called()

    def test_end_button_and_settlement_are_different_states(self):
        session,image = self.session('ranked-battle-1920.png')
        session.frame_seq = 1
        self.assertFalse(session.recognize('settlement',image))
        self.assertTrue(session.recognize('end_button',image))
        session.flow.window.click.assert_not_called()

    def test_latest_panel_start_wait_scope_and_return_use_same_detection(self):
        session,image=self.session(ROOT/'出错任务/排位战/证据/158ed082d1c10b09032c8de8.png')
        session.server='连服'
        session.frame_seq=1
        self.assertTrue(session.recognize('panel',image))
        session.flow.observe=Mock()
        context=Mock()
        session.action('start',context,'RankedStart')
        context.override_next.assert_called_with('RankedStart',['RankedPanel'])
        for seq,expected in ((2,False),(3,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('scoped',image),expected)
        session.in_flight=session.confirm_sent=session.scoped=True
        session.action('returned',context,'RankedReturned')
        context.override_next.assert_called_with('RankedReturned',['RankedRead'])
        for seq,expected in ((4,False),(5,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(1,565140))
        self.assertEqual(session.completed,0)
        session.flow.window.click.assert_not_called()

    def test_oct16_latest_failure_passes_two_frame_check(self):
        path=ROOT/'出错任务/排位战/证据/2b3eeebbb2e4eafbc1a4271e.png'
        session,image=self.session(path)
        for seq,expected in ((1,False),(2,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(5,572798))
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_post_refresh_cooldown_then_two_stable_real_frames(self):
        path=ROOT/'出错任务/排位战/证据/45706e4f3dec2230d7449180.png'
        session,image=self.session(path)
        session.frame_seq=1
        session.pending='defeat'
        session.count=2
        self.assertTrue(session.recognize('refreshed',image))
        session.action('refreshed',Mock(),'RankedRefreshed')
        for seq,expected in ((2,False),(3,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertIsNone(session.pending)
        self.assertEqual(session.state[:2],(2,565140))
        self.assertCountEqual([o['power'] for o in session.state[2]],
                             [1155227,752120,1066599,618173,769353])
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_latest_failure_power_passes_two_frame_pipeline_check(self):
        session,image = self.session('ranked-power340470-1920.png')
        for seq,expected in ((1,False),(2,True)):
            session.frame_seq = seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(7,340470))
        self.assertCountEqual([o['power'] for o in session.state[2]],
                              [547461,1389901,647519,611663,402865])
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_oct18_refresh_then_two_real_frames_read_touching_digits(self):
        path=ROOT/'出错任务/排位战/证据/859054be011704e1a56a2121.png'
        session,image=self.session(path)
        session.frame_seq=1;session.pending='defeat';session.count=2
        self.assertTrue(session.recognize('refreshed',image))
        session.action('refreshed',Mock(),'RankedRefreshed')
        for seq,expected in ((2,False),(3,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(2,569821))
        self.assertCountEqual([o['power'] for o in session.state[2]],
                             [1109537,1007171,960878,1345437,690256])
        self.assertEqual(session.read_errors,{})
        self.assertIsNone(session.pending)
        session.flow.window.click.assert_not_called()

    def test_new_failure_power_passes_two_frame_check(self):
        path=ROOT/'verification/failure-20261013-004210-3be11abb0f98-ranked.png'
        session,image = self.session(path)
        for seq,expected in ((1,False),(2,True)):
            session.frame_seq = seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(6,341307))
        self.assertCountEqual([o['power'] for o in session.state[2]],
                             [547461,1389901,647519,611663,402865])
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_real_settlement_keeps_explicit_victory(self):
        session,image = self.session('battle-settlement-calibration.png')
        session.frame_seq = 1
        self.assertTrue(session.recognize('settlement',image))
        session.flow.observe = Mock()
        self.assertEqual(session.read_result(),'victory')
        session.flow.window.click.assert_not_called()

    def test_real_victory_and_defeat_confirm_unique_button_once(self):
        for name, result in (('battle-settlement-calibration.png', 'victory'),
                             ('ranked-defeat-1920.png', 'defeat')):
            with self.subTest(result=result):
                session, image = self.session(name)
                session.frame_seq = 1
                self.assertTrue(session.recognize('settlement', image))
                session.flow.observe = Mock()
                session.in_flight = True
                session.action('result', Mock(), 'RankedSettlement')
                self.assertEqual(session.pending, result)
                with patch('local_flows.time.sleep'):
                    session.action('confirm', Mock(), 'RankedConfirm')
                session.flow.window.click.assert_called_once()
                x, y = session.flow.window.click.call_args.args
                # Both preserved scenes show 确定 below 战斗统计 at this location.
                self.assertTrue(870 < x < 1060 and 650 < y < 700, (x, y))
                self.assertTrue(session.confirm_sent)
                self.assertEqual(session.wait_label, '确认返回挑战面板')
                with self.assertRaisesRegex(RuntimeError, '拒绝重复确认'):
                    session.action('confirm', Mock(), 'RankedConfirm')
                session.flow.window.click.assert_called_once()
                self.assertEqual(session.completed, 0)

    def test_latest_archived_ending_animation_is_not_a_settlement(self):
        session, image = self.session(ROOT/'出错任务/排位战/证据/03a48dd9eac5765e324b51e2.png')
        session.frame_seq = 1
        self.assertFalse(session.recognize('settlement', image))
        session.flow.window.click.assert_not_called()

    def test_afternoon_failure_eights_pass_two_distinct_frame_checks(self):
        path=ROOT/'出错任务/排位战/证据/1d6c05e9d6c508ef8460ef10.png'
        session,image = self.session(path)
        session.frame_seq = 1
        self.assertFalse(session.recognize('stable',image))
        session.frame_seq = 2
        self.assertTrue(session.recognize('stable',image))
        self.assertEqual(session.state[:2],(7,572882))
        self.assertCountEqual([o['power'] for o in session.state[2]],
                              [672886,1174445,1313308,1419289,1162291])
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_cooldown_observation_needs_no_input(self):
        session,image = self.session('ranked-refresh-cooldown-live.png')
        session.frame_seq = 1
        self.assertTrue(session.recognize('refreshed',image))
        session.flow.window.click.assert_not_called()

    def test_oct19_full_frame_candidate_survives_local_omission_in_two_frames(self):
        path=ROOT/'出错任务/排位战/证据/562b157c91b3f43476ed8383.png'
        session,image=self.session(path)
        for seq,expected in ((1,False),(2,True)):
            session.frame_seq=seq
            self.assertEqual(session.recognize('stable',image),expected)
        self.assertEqual(session.state[:2],(4,341235))
        self.assertEqual([o['power'] for o in session.state[2]],[634467,815753,885384,962616,471398])
        self.assertEqual(session.read_errors,{})
        session.flow.window.click.assert_not_called()

    def test_real_failed_run_defeat_is_read_before_confirmation(self):
        session,image = self.session('ranked-defeat-1920.png')
        session.frame_seq = 1
        self.assertTrue(session.recognize('settlement',image))
        session.flow.observe = Mock()
        self.assertEqual(session.read_result(),'defeat')
        session.flow.window.click.assert_not_called()

    def test_defeat_settlement_throttle_cannot_hide_confirmed_page(self):
        session,image = self.session('battle-settlement-calibration.png')
        session.flow.ocr = Mock()
        session.flow.ocr.match.return_value = []
        session.flow.ocr.read.return_value = [{'text':'确定','box':[1,1,10,10]},
                                             {'text':'战斗统计','box':[1,20,10,10]}]
        session.flow.observe = Mock()
        session.flow.ranked_battle_result = Mock(return_value='defeat')
        session.flow._settlement_scan_at = 1e18
        self.assertEqual(session.read_result(),'defeat')
        session.flow.window.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
