import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from local_flows import LocalFlows

ROOT=Path(__file__).resolve().parents[1]


class StrongTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR()
        cls.image=np.array(Image.open(ROOT/'resources/local/strong-1920-calibration.png').convert('RGB'))[:,:,::-1].copy()
        cls.items=cls.ocr.read(cls.image)

    def flow(self):
        flow=LocalFlows(Mock(),self.ocr,{'difficulty':'阿修罗级'},lambda:None,Mock())
        flow.image=self.image.copy();flow.items=self.items
        return flow

    def test_user_screenshot_reward_count_and_art_start_are_identified(self):
        flow=self.flow()
        self.assertFalse(flow.hits('普通奖励次数'))
        self.assertFalse(flow.hits('进入战斗'))
        count,buttons=flow.strong_reward_state()
        self.assertEqual(count,1)
        self.assertEqual(set(buttons),{'天级','夜叉级','阿修罗级'})
        start=flow.strong_start_button()
        x,y,w,h=start['box']
        self.assertTrue(600<x<870 and 620<y<750)
        flow.window.click.assert_not_called()

    def test_unknown_or_conflicting_count_does_not_enter_battle(self):
        flow=self.flow()
        flow.ocr=Mock()
        buttons={'天级':{'box':[521,787,158,86]},'夜叉级':{'box':[880,784,171,88]},'阿修罗级':{'box':[1226,787,263,87]}}
        flow.strong_panel_buttons=Mock(return_value=buttons)
        flow.ocr.match.return_value=[];flow.ocr.read.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'奖励次数'):flow.strong_reward_state()
        flow.ocr.match.return_value=[{'box':[0,0,10,10]}]
        with self.assertRaisesRegex(RuntimeError,'冲突'):flow.strong_reward_state()
        flow.window.click.assert_not_called()

    def test_missing_difficulty_option_blocks_panel_readiness(self):
        flow=self.flow();flow.ocr=Mock()
        flow.ocr.match.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'三个难度'):flow.strong_panel_buttons()
        flow.window.click.assert_not_called()

    def test_restarting_from_existing_panel_selects_each_difficulty(self):
        for grade in ('天级','夜叉级','阿修罗级'):
            with self.subTest(grade=grade):
                flow=self.flow();flow.cfg['difficulty']=grade
                flow.observe=Mock();flow.enter=Mock();flow.home=Mock()
                flow.battle=Mock(return_value=True);flow.click_item=Mock()
                flow.strong()
                flow.enter.assert_not_called()
                self.assertEqual(flow.click_item.call_args_list[0].args[0]['template'],{'天级':'strong_sky','夜叉级':'strong_yaksha','阿修罗级':'strong_asura'}[grade])
                self.assertEqual(flow.click_item.call_args_list[1].args[0]['template'],'strong_enter')
                flow.battle.assert_called_once()

    def test_zero_ordinary_reward_skips_even_if_cooperation_has_reward(self):
        flow=self.flow()
        # Replace only the ordinary count crop with the real zero glyph from
        # this screenshot's cooperation counter; keep the ordinary label left.
        flow.image[904:947,885:930]=self.image[904:947,1278:1323]
        flow.items=[{'text':'本周可用组织协作奖励次数:7','box':[992,911,286,26]}]
        self.assertEqual(flow.strong_reward_state()[0],0)
        flow.observe=Mock();flow.close_panel=Mock();flow.battle=Mock();flow.click_item=Mock()
        flow.strong()
        flow.close_panel.assert_called_once();flow.battle.assert_not_called();flow.click_item.assert_not_called()

    def test_transient_black_frame_is_retried_but_minimized_is_not(self):
        flow=self.flow()
        flow.window.capture.side_effect=[RuntimeError('游戏截图为黑屏或未加载'),self.image]
        with patch('local_flows.time.sleep'):self.assertIs(flow.capture_ready(),self.image)
        self.assertEqual(flow.window.capture.call_count,2)
        flow.window.capture=Mock(side_effect=RuntimeError('游戏已最小化'))
        with self.assertRaisesRegex(RuntimeError,'最小化'):flow.capture_ready()
        flow.window.capture.assert_called_once()

    def test_persistent_black_frame_still_stops_without_input(self):
        flow=self.flow();flow.window.capture.side_effect=RuntimeError('游戏截图为黑屏或未加载')
        with patch('local_flows.time.sleep'),patch('local_flows.time.monotonic',side_effect=[0,0,4]):
            with self.assertRaisesRegex(RuntimeError,'黑屏'):flow.capture_ready()
        flow.window.click.assert_not_called()

    def test_main_entry_waits_for_ready_before_difficulty_click(self):
        flow=self.flow();buttons=flow.strong_panel_buttons()
        events=[]
        flow.observe=Mock();flow.enter=Mock(side_effect=lambda _:events.append('enter'))
        flow.strong_panel_buttons=Mock(side_effect=RuntimeError('面板未加载'))
        flow.wait_strong_ready=Mock(side_effect=lambda:(events.append('ready') or (1,buttons)))
        flow.wait=Mock(side_effect=lambda predicate,seconds: self.assertTrue(predicate()))
        flow.click_item=Mock(side_effect=lambda button,**_:events.append(button['template']))
        flow.battle=Mock(return_value=True);flow.home=Mock()
        flow.strong()
        self.assertEqual(events,['enter','ready','strong_asura','strong_enter'])


if __name__=='__main__':unittest.main()
