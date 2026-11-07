import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from local_flows import LocalFlows

ROOT = Path(__file__).resolve().parents[1]


class HostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = LocalOCR()
        cls.image = np.array(Image.open(ROOT/'resources/local/hosting-1920-calibration.png').convert('RGB'))[:, :, ::-1].copy()
        cls.items = cls.ocr.read(cls.image)
        cls.first_image = np.array(Image.open(ROOT/'resources/local/hosting-first-confirm-1920.png').convert('RGB'))[:, :, ::-1].copy()
        cls.first_items = cls.ocr.read(cls.first_image)

    def flow(self):
        flow = LocalFlows(Mock(), self.ocr, {}, lambda: None, Mock())
        flow.image = self.image.copy()
        flow.items = self.items
        return flow

    def test_current_user_screenshot_computer_is_recognized(self):
        buttons = self.ocr.match(self.image, 'computer')
        self.assertEqual(len(buttons), 1)
        x, y, w, h = buttons[0]['box']
        self.assertTrue(675 <= x+w/2 <= 700 and 135 <= y+h/2 <= 160)

    def test_user_first_activation_dialog_identifies_confirmation(self):
        flow = self.flow()
        flow.image = self.first_image.copy()
        flow.items = self.first_items
        button = flow.hosting_activation_dialog()
        self.assertIsNotNone(button)
        x, y, w, h = button['box']
        self.assertTrue(815 <= x+w/2 <= 845 and 570 <= y+h/2 <= 590)
        flow.window.click.assert_not_called()

    def frames(self, flow, frames):
        sequence = iter(frames)
        last = None
        def observe():
            nonlocal last
            last = next(sequence, last)
            flow.image = self.first_image.copy() if last == 'first' else self.image.copy()
            if last == 'first':
                flow.items = self.first_items
            elif last == 'active':
                flow.items = [{'text': '托管中', 'box': [700, 50, 100, 30]}]
            elif last == 'settings':
                flow.items = [{'text': '托管设置', 'box': [328, 105, 98, 29]},
                              {'text': '开始托管', 'box': [744, 898, 96, 29]}]
            else:
                flow.items = [{'text': '确定', 'box': [808, 568, 45, 24]}]
        flow.observe = Mock(side_effect=observe)

    def test_first_start_confirms_once_then_requires_active_state(self):
        flow = self.flow()
        self.frames(flow, ['first', 'first', 'active'])
        with patch('local_flows.time.sleep'):
            flow.wait_hosting_started()
        self.assertEqual(flow.observe.call_count, 3)
        flow.window.click.assert_called_once_with(830, 580)
        self.assertEqual(flow.items[0]['text'], '托管中')

    def test_same_day_direct_start_needs_no_confirmation(self):
        flow = self.flow()
        self.frames(flow, ['active'])
        flow.wait_hosting_started()
        flow.window.click.assert_not_called()

    def test_unrelated_confirmation_is_not_clicked_and_times_out(self):
        flow = self.flow()
        self.frames(flow, ['unknown'])
        with patch('local_flows.time.sleep'), patch('local_flows.time.monotonic', side_effect=[0, 0, 2]):
            with self.assertRaisesRegex(RuntimeError, '未确认托管中'):
                flow.wait_hosting_started(seconds=1)
        flow.window.click.assert_not_called()

    def test_stuck_first_prompt_is_not_confirmed_twice_or_reported_active(self):
        flow = self.flow()
        self.frames(flow, ['first', 'first'])
        with patch('local_flows.time.sleep'), patch('local_flows.time.monotonic', side_effect=[0, 0, 0, 2]):
            with self.assertRaisesRegex(RuntimeError, '未确认托管中'):
                flow.wait_hosting_started(seconds=1)
        flow.window.click.assert_called_once_with(830, 580)

    def test_unknown_card_count_or_purchase_prompt_blocks_confirmation(self):
        for message in ('消耗托管卡x2，有效期持续到次日5:00', '消耗托管卡11，有效期持续到次日5:00',
                        '购买托管卡需要元宝', '托管卡不足'):
            with self.subTest(message=message):
                flow = self.flow()
                flow.ocr = Mock()
                flow.ocr.read.return_value = [{'text': text, 'box': [100, 100, 100, 20]}
                    for text in ('您今天为首次进入托管状态', message, '是否确认进入托管状态', '确定', '取消')]
                flow.ocr.match.return_value = []
                with self.assertRaisesRegex(RuntimeError, '停止'):
                    flow.hosting_activation_dialog()
                flow.window.click.assert_not_called()

    def test_restart_from_first_prompt_skips_entry_and_start_button(self):
        flow = self.flow()
        self.frames(flow, ['first', 'first', 'active'])
        flow.home = Mock()
        flow.hosting_computer_button = Mock()
        flow.click_text = Mock()
        flow.wait = Mock(side_effect=lambda *args: setattr(flow, 'items',
                              [{'text': '托管结束', 'box': [600, 500, 100, 20]}]))
        with patch('local_flows.time.sleep'):
            flow.hosting()
        flow.window.click.assert_called_once_with(830, 580)
        flow.hosting_computer_button.assert_not_called()
        flow.click_text.assert_not_called()
        flow.home.assert_called_once()

    def test_restart_from_settings_can_start_directly(self):
        flow = self.flow()
        self.frames(flow, ['settings', 'active'])
        flow.home = Mock()
        flow.hosting_computer_button = Mock()
        flow.wait_text = Mock()
        flow.wait = Mock(side_effect=lambda *args: setattr(flow, 'items',
                              [{'text': '托管结束', 'box': [600, 500, 100, 20]}]))
        with patch('local_flows.time.sleep'):
            flow.hosting()
        flow.window.click.assert_called_once_with(792, 912)
        flow.hosting_computer_button.assert_not_called()
        flow.wait_text.assert_not_called()
        flow.home.assert_called_once()

    def test_badge_anchored_match_uses_game_coordinates(self):
        flow = self.flow()
        self.assertEqual(len(flow.hits(r'^中忍勋章$')), 1)
        button = flow.hosting_computer_button()
        x, y, w, h = button['box']
        self.assertEqual([x, y, w, h], [670, 129, 36, 34])
        flow.window.click.assert_not_called()

    def test_unrelated_monitor_outside_player_panel_is_ignored(self):
        flow = self.flow()
        flow.image[500:534, 1000:1036] = self.image[129:163, 670:706]
        self.assertEqual(flow.hosting_computer_button()['box'], [670, 129, 36, 34])

    def test_unreadable_badge_still_requires_unique_artwork_in_player_panel(self):
        flow = self.flow()
        flow.items = []
        self.assertEqual(flow.hosting_computer_button()['box'], [670, 129, 36, 34])
        flow.image[129:163, 670:706] = 0
        self.assertIsNone(flow.hosting_computer_button())
        flow.window.click.assert_not_called()

    def test_two_monitors_under_badge_stop_without_input(self):
        flow = self.flow()
        flow.image[129:163, 710:746] = self.image[129:163, 670:706]
        with self.assertRaisesRegex(RuntimeError, '不唯一'):
            flow.hosting_computer_button()
        flow.window.click.assert_not_called()

    def test_start_hosting_is_not_clicked_until_entrance_panel_is_confirmed(self):
        flow = self.flow()
        flow.observe = Mock()
        flow.home = Mock()
        flow.click_text = Mock()
        flow.wait_text = Mock(side_effect=RuntimeError('未出现开始托管'))
        with patch('local_flows.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, '未出现开始托管'):
                flow.hosting()
        flow.window.click.assert_called_once_with(688, 146)
        flow.wait_text.assert_called_once_with(r'^开始托管$')
        flow.click_text.assert_not_called()


if __name__ == '__main__':
    unittest.main()
