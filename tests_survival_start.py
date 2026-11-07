"""Survival-only start recognition and mocked input regression tests."""
import unittest
from pathlib import Path
from unittest.mock import Mock

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from PIL import Image
import numpy as np

from survival_start import survival_start_button, start_survival_battle

ROOT = Path(__file__).resolve().parent


def button(box=(881, 143, 191, 45), score=1.):
    return {'box': list(box), 'score': score}


class SurvivalStartTests(unittest.TestCase):
    def flow(self):
        flow = LocalFlows(Mock(), Mock(), {}, lambda: None, Mock())
        flow.image = np.zeros((1015, 1920, 3), dtype=np.uint8)
        flow.items = []
        flow.ocr.match.return_value = []
        flow.observe = Mock()
        return flow

    def wait_once(self, predicate):
        self.assertTrue(predicate())

    def test_specialized_template_clicks_once_after_fresh_observation(self):
        flow = self.flow()
        flow.ocr.match.side_effect = lambda image, name, **kw: [button()] if name == 'survival_start' else []
        flow.wait = self.wait_once
        start_survival_battle(flow)
        flow.observe.assert_called_once()
        flow.window.click.assert_called_once_with(976, 165)

    def test_legacy_template_remains_supported(self):
        flow = self.flow()
        flow.ocr.match.side_effect = lambda image, name, **kw: [button()] if name == 'start_battle' else []
        self.assertEqual(survival_start_button(flow)['box'], button()['box'])

    def test_ocr_and_overlapping_templates_are_one_button(self):
        flow = self.flow()
        flow.items = [dict(button((912, 145, 110, 40)), text='开 战')]
        flow.ocr.match.return_value = [button()]
        self.assertIsNotNone(survival_start_button(flow))

    def test_multiple_distinct_buttons_stop_without_input(self):
        flow = self.flow()
        flow.ocr.match.return_value = [button(), button((1100, 143, 100, 45))]
        with self.assertRaisesRegex(RuntimeError, '不唯一'):
            start_survival_battle(flow)
        flow.window.click.assert_not_called()

    def test_chat_and_low_confidence_ocr_are_rejected(self):
        flow = self.flow()
        for item in (dict(button((100, 800, 80, 30)), text='开战'),
                     dict(button(score=.79), text='开战')):
            with self.subTest(item=item):
                flow.items = [item]
                self.assertIsNone(survival_start_button(flow))
        flow.window.click.assert_not_called()

    def test_disappeared_or_moved_button_stops_before_click(self):
        for fresh in ([], [button((1050, 143, 100, 45))]):
            with self.subTest(fresh=fresh):
                flow = self.flow()
                flow.ocr.match.side_effect = lambda image, name, **kw: [button()] if name == 'survival_start' else []
                flow.wait = self.wait_once
                def observe():
                    flow.ocr.match.side_effect = lambda image, name, **kw: fresh if name == 'survival_start' else []
                flow.observe.side_effect = observe
                with self.assertRaisesRegex(RuntimeError, '变化'):
                    start_survival_battle(flow)
                flow.window.click.assert_not_called()

    def test_ambiguous_fresh_frame_stops_before_click(self):
        flow = self.flow()
        flow.ocr.match.return_value = [button()]
        flow.wait = self.wait_once
        flow.observe.side_effect = lambda: setattr(flow.ocr.match, 'return_value', [button(), button((1100,143,100,45))])
        with self.assertRaisesRegex(RuntimeError, '不唯一'):
            start_survival_battle(flow)
        flow.window.click.assert_not_called()

    def test_unknown_frame_times_out_without_input(self):
        flow = self.flow()
        def wait(predicate):
            self.assertFalse(predicate())
            raise RuntimeError('等待界面状态超时')
        flow.wait = wait
        with self.assertRaisesRegex(RuntimeError, '超时'):
            start_survival_battle(flow)
        flow.window.click.assert_not_called()

    def test_input_failure_is_not_retried(self):
        flow = self.flow()
        flow.ocr.match.return_value = [button()]
        flow.wait = self.wait_once
        flow.window.click.side_effect = RuntimeError('input uncertain')
        with self.assertRaisesRegex(RuntimeError, 'input uncertain'):
            start_survival_battle(flow)
        self.assertEqual(flow.window.click.call_count, 1)


class SurvivalStartImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = LocalOCR()

    def flow(self, path):
        flow = LocalFlows(Mock(), self.ocr, {}, lambda: None, Mock())
        flow.image = np.array(Image.open(ROOT / path).convert('RGB'))[:, :, ::-1].copy()
        flow.items = self.ocr.read(flow.image)
        return flow

    def test_failure_image_is_recognized_and_clicked_once(self):
        flow = self.flow('verification/failure-20261105-131716-1b65ccbc4f36-survival.png')
        self.assertFalse(flow.hits(r'^开战$'))
        self.assertFalse(flow.ocr.match(flow.image, 'start_battle'))
        flow.window.capture.return_value = flow.image
        start_survival_battle(flow)
        flow.window.click.assert_called_once_with(976,165)
        self.assertEqual(flow.window.capture.call_count, 2)  # wait frame + send-time recheck

    def test_existing_panels_and_reward_overlay_are_rejected(self):
        for path in ('resources/local/survival-1920-calibration.png',
                     'verification/failure-20261018-234702-3aa6ed0d9603-survival.png',
                     'resources/local/survival-reward-popup-calibration.png'):
            with self.subTest(path=path):
                flow = self.flow(path)
                self.assertIsNone(survival_start_button(flow))
                flow.window.click.assert_not_called()

    def test_independent_october_preparation_frame_is_recognized(self):
        flow = self.flow('verification/failure-20261031-190829-7ec210e60456-survival.png')
        found = survival_start_button(flow)
        self.assertEqual(found['box'], [881,143,191,45])
        flow.window.click.assert_not_called()

    def test_production_survival_branch_reaches_battle_then_claims(self):
        flow = self.flow('verification/failure-20261105-131716-1b65ccbc4f36-survival.png')
        frame, items = flow.image, flow.items
        flow.observe = Mock(side_effect=lambda: setattr(flow, 'items', items))
        flow.enter = Mock(); flow.wait_text = Mock(); flow.wait_survival_ready = Mock()
        flow.survival_reset = Mock(); flow.battle_settlement = Mock(return_value=False)
        flow.dismiss_survival_reward_popup = Mock(return_value=False)
        flow.survival_points = Mock(side_effect=[(0,220),(220,220)])
        flow.survival_candidate = Mock(return_value=('SS',1,1390,148))
        flow.cfg = {'reset':False, 'survivalGrades':['SS'], 'survivalCounts':{'SS':1}}
        flow.battle = Mock(); flow.close_panel = Mock()
        flow.click_text = Mock(); flow.survival_rewards_finished = Mock(return_value=True)
        def wait(predicate, seconds=30):
            flow.image = frame
            self.assertTrue(predicate())
        flow.wait = wait
        flow.survival()
        self.assertEqual(flow.window.click.call_args_list, [((1390,148),), ((976,165),)])
        flow.battle.assert_called_once()
        self.assertEqual(flow._survival_used, {'SS':1})
        flow.close_panel.assert_called_once()


if __name__ == '__main__':
    unittest.main()
