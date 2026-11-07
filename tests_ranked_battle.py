"""Ranked end-battle regressions using the user's missed-click frame."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from local_flows import LocalFlows

ROOT=Path(__file__).resolve().parent


class RankedBattleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR()
        cls.image=np.array(Image.open(ROOT/'resources/local/ranked-battle-1920.png').convert('RGB'))[:,:,::-1].copy()

    def flow(self):
        flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
        flow.image=self.image.copy()
        flow.ensure_ranked_server=Mock()
        return flow

    def test_user_frame_locates_end_battle_artwork(self):
        buttons=self.ocr.match(self.image,'end_battle')
        self.assertEqual(len(buttons),1)
        x,y,w,h=buttons[0]['box']
        self.assertTrue(1660<x+w/2<1795)
        self.assertTrue(900<y+h/2<1015)

    def test_oct15_animation_frame_keeps_end_button_identifiable(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'出错任务/排位战/证据/22e8008a8d7f470160865c92.png').convert('RGB'))[:,:,::-1].copy()
        button=flow.ranked_end_battle_button()
        self.assertIsNotNone(button)
        x,y,w,h=button['box']
        self.assertTrue(1660<x+w/2<1795)
        self.assertTrue(900<y+h/2<1015)
        flow.window.click.assert_not_called()

    def test_button_moves_with_artwork_and_ignores_outside_control_strip(self):
        flow=self.flow()
        glyph=self.image[902:1005,1668:1795].copy()
        flow.image[:]=0
        flow.image[886:989,1620:1747]=glyph
        button=flow.ranked_end_battle_button()
        self.assertEqual(button['box'],[1620,886,127,103])
        flow.image[:]=0
        flow.image[100:203,100:227]=glyph
        self.assertIsNone(flow.ranked_end_battle_button())
        flow.window.click.assert_not_called()

    def test_retreat_alone_never_becomes_end_battle(self):
        flow=self.flow();flow.image[880:1015,1610:1800]=0
        self.assertIsNone(flow.ranked_end_battle_button())
        flow.window.click.assert_not_called()

    def test_ambiguous_buttons_stop_without_input(self):
        flow=self.flow();flow.ocr=Mock()
        flow.ocr.match.return_value=[{'box':[40,30,127,103]},{'box':[185,30,127,103]}]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):flow.ranked_end_battle_button()
        flow.window.click.assert_not_called()

    def test_text_fallback_is_local_and_translates_coordinates(self):
        flow=self.flow();flow.ocr=Mock();flow.ocr.match.return_value=[]
        flow.ocr.read.return_value=[{'text':'结束战斗','box':[65,40,60,70]}]
        self.assertEqual(flow.ranked_end_battle_button()['box'],[1677,872,60,70])
        self.assertEqual(flow.ocr.read.call_args.args[0].shape[:2],(183,308))

    def test_finish_clicks_star_once_then_confirms_and_returns(self):
        flow=self.flow();flow.observe=Mock();flow.battle_settlement=Mock(return_value=False)
        flow.wait_text=Mock();flow.confirm=Mock();flow.ranked_battle_result=Mock(return_value='defeat')
        predicates=[]
        def wait(predicate,seconds=30):
            predicates.append(predicate)
            if len(predicates)==1:self.assertTrue(predicate())
        flow.wait=wait
        with patch('local_flows.time.sleep'):
            flow.finish_ranked_battle()
        flow.window.click.assert_called_once_with(1731,953)
        flow.wait_text.assert_called_once_with(r'^(确定|确认)$',900)
        flow.confirm.assert_called_once()
        self.assertEqual(predicates[-1],flow.ranked_panel_visible)

    def test_already_settled_never_clicks_battle_controls(self):
        flow=self.flow();flow.battle_settlement=Mock(return_value=True)
        flow.ranked_end_battle_button=Mock();flow.wait_text=Mock();flow.confirm=Mock()
        flow.ranked_battle_result=Mock(return_value='victory')
        flow.wait=lambda predicate,seconds=30:predicate() if seconds==120 else None
        flow.finish_ranked_battle()
        flow.ranked_end_battle_button.assert_not_called()
        flow.wait_text.assert_not_called();flow.window.click.assert_not_called()
        flow.confirm.assert_called_once()

    def test_resume_current_battle_before_reading_remaining_count(self):
        flow=self.flow();flow.observe=Mock();flow.enter=Mock();flow.close_panel=Mock()
        flow.finish_ranked_battle=Mock();flow.wait_ranked_ready=Mock(return_value=(0,None,[]))
        self.assertIsNone(flow.ranked())
        flow.finish_ranked_battle.assert_called_once();flow.enter.assert_not_called()
        flow.window.click.assert_not_called()

    def test_end_button_timeout_does_not_confirm_or_report_success(self):
        flow=self.flow();flow.wait=Mock(side_effect=RuntimeError('等待界面状态超时，已保存最后截图'))
        flow.confirm=Mock()
        with self.assertRaisesRegex(RuntimeError,'结束战斗按钮识别超时'):flow.finish_ranked_battle()
        flow.window.click.assert_not_called();flow.confirm.assert_not_called()

    def test_unknown_result_keeps_settlement_without_confirming(self):
        flow=self.flow();flow.battle_settlement=Mock(return_value=True)
        flow.ranked_battle_result=Mock(side_effect=RuntimeError('排位战胜负无法可靠识别'))
        flow.wait=lambda predicate,seconds=30:predicate()
        flow.confirm=Mock()
        with self.assertRaisesRegex(RuntimeError,'胜负无法'):flow.finish_ranked_battle()
        flow.confirm.assert_not_called();flow.window.click.assert_not_called()

    def test_real_archived_defeat_settlement_has_explicit_result(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'resources/local/ranked-defeat-1920.png').convert('RGB'))[:,:,::-1].copy()
        self.assertTrue(flow.battle_settlement())
        self.assertEqual(flow.ranked_battle_result(),'defeat')
        flow.window.click.assert_not_called()

    def test_user_defeat_screenshot_has_same_result(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'resources/local/ranked-defeat-user-1920.png').convert('RGB'))[:,:,::-1].copy()
        self.assertTrue(flow.battle_settlement())
        self.assertEqual(flow.ranked_battle_result(),'defeat')
        flow.window.click.assert_not_called()

    def test_real_settlement_without_outcome_or_hp_stays_unknown(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'resources/local/ranked-defeat-1920.png').convert('RGB'))[:,:,::-1].copy()
        flow.image[300:609,800:1150]=0
        flow.image[:120]=0
        # The statistics and confirm buttons still establish settlement, but
        # are insufficient to prove defeat after the result artwork is removed.
        self.assertTrue(flow.battle_settlement())
        with self.assertRaisesRegex(RuntimeError,'胜负无法可靠识别'):
            flow.ranked_battle_result()
        flow.window.click.assert_not_called()


if __name__=='__main__':unittest.main()
