"""Welfare reference-image and bounded flow checks; no game window or input."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from welfare_vision import WelfareVision, load, BUTTONS
from welfare_task import WelfareTask
from adapters.local_ocr import LocalOCR
import numpy as np
from PIL import Image


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = WelfareVision(LocalOCR())
        cls.daily = load('reference-3')[150:1165, 45:1965].copy()
        cls.online = load('reference-7')[150:1165, 45:1965].copy()

    def test_real_daily_states(self):
        v = self.vision
        self.assertEqual(v.panel(self.daily, 'daily'), (0, 0))
        self.assertEqual(v.tier(self.daily), '上忍')
        self.assertEqual(v.button(self.daily, 'monthly')['state'], 'unavailable')
        self.assertFalse(v.button(self.daily, 'monthly')['received'])
        self.assertEqual(v.button(self.daily, 'large_monthly')['state'], 'claimable')
        for slot in ('medal_daily', 'medal_weekly'):
            self.assertEqual(v.button(self.daily, slot)['state'], 'unavailable')
            self.assertFalse(v.button(self.daily, slot)['received'])

    def test_real_online_three_claims(self):
        self.assertEqual(self.vision.panel(self.online, 'online'), (0, 0))
        points = [self.vision.button(self.online, slot)['point'] for slot in ('online_1', 'online_2', 'online_3')]
        self.assertEqual(points, [(728, 764), (1022, 764), (1317, 764)])

    def test_live_received_status(self):
        image = load('reference-claimed-live')
        self.assertEqual(self.vision.button(image, 'large_monthly')['state'], 'unavailable')

    def live_frame(self, name):
        path = Path(__file__).resolve().parents[1]/'verification/welfare-20261027-003252-54f155ca'/name
        return np.array(Image.open(path).convert('RGB'))[:, :, ::-1].copy()

    def test_independent_live_home_entry(self):
        path = Path(__file__).resolve().parents[1]/'verification/welfare-live-before-20261027.png'
        image = np.array(Image.open(path).convert('RGB'))[:, :, ::-1].copy()
        self.assertEqual(self.vision.unique(image, 'entry'), [1452, 199, 109, 112])

    def test_independent_live_tier_feedback(self):
        for name, tier in (('015.png', '上忍'), ('025.png', '中忍'), ('035.png', '下忍')):
            self.assertEqual(self.vision.tier(self.live_frame(name)), tier)

    def test_independent_live_online_claim_results(self):
        image = self.live_frame('066.png')
        for slot in ('online_1', 'online_2', 'online_3'):
            self.assertEqual(self.vision.button(image, slot)['state'], 'unavailable')

    def test_independent_live_closed_home(self):
        image = self.live_frame('072.png')
        self.assertFalse(self.vision.matches(image, 'close'))
        self.assertTrue(self.vision.ocr.match(image, 'entry_survival'))
        self.assertTrue(self.vision.ocr.match(image, 'entry_ranked'))

    def test_other_page_navigation(self):
        image = load('reference-2')[150:1165, 45:1965].copy()
        self.assertEqual(self.vision.panel(image), (0, 0))
        self.vision.unique(image, 'daily_tab')
        with self.assertRaises(RuntimeError):
            self.vision.panel(image, 'daily')

    def test_reject_blank_and_wrong_size(self):
        for image in (np.zeros_like(self.daily), self.daily[:900]):
            with self.assertRaises(RuntimeError):
                self.vision.panel(image, 'daily')

    def test_dimmed_modal_background_rejected(self):
        image = (self.daily.astype(float)*.45).astype(np.uint8)
        with self.assertRaises(RuntimeError):
            self.vision.panel(image, 'daily')

    def test_grey_claim_is_not_active_claim(self):
        crop = load('claim_daily')
        gray = np.repeat(crop.mean(axis=2, keepdims=True).astype(np.uint8), 3, axis=2)
        self.assertFalse(self.vision.matches(gray, 'claim_daily', .92))

    def test_unreadable_nonclaim_slot_skips(self):
        image = self.daily.copy()
        l, t, r, b = BUTTONS['large_monthly']
        image[t:b, l:r] = 0
        result = self.vision.button(image, 'large_monthly')
        self.assertEqual(result['state'], 'unavailable')
        self.assertFalse(result['received'])

    def test_purchase_and_activation_are_not_claim_templates(self):
        for slot in ('monthly', 'medal_daily', 'medal_weekly'):
            crop, _ = self.vision.region(self.daily, BUTTONS[slot], 'daily')
            self.assertFalse(self.vision.matches(crop, 'claim_daily', .92))

    def test_tier_changes_synthetic_not_live(self):
        from welfare_vision import TIERS
        # Only verifies selection feedback mechanics. No real middle/lower sample exists.
        for selected in TIERS:
            image = self.daily.copy()
            for name, (l, t, r, b) in TIERS.items():
                image[t:b, l:r] = 220 if name == selected else 130
            self.assertEqual(self.vision.tier(image), selected)
        for l, t, r, b in TIERS.values():
            image[t:b, l:r] = 130
        with self.assertRaises(RuntimeError):
            self.vision.tier(image)


class FakeWindow:
    def __init__(self):
        self.page = 'fund'
        self.tier = '上忍'
        self.claimed = set()
        self.inputs = []
        self.failed_input = False
        self.ignore_claim = False

    def capture(self):
        return self

    def save(self, image, path):
        pass

    def click(self, x, y):
        self.inputs.append((x, y))
        if self.failed_input:
            raise RuntimeError('后台释放失败')
        if x == 1:
            self.page = 'daily'
        elif x == 2:
            self.page = 'online'
        elif x == 3:
            self.page = 'home'
        elif x in (4, 5, 6):
            self.tier = {4: '上忍', 5: '中忍', 6: '下忍'}[x]
        elif not self.ignore_claim:
            self.claimed.add((x, self.tier if x == 13 else None))


class FakeVision:
    slots = dict(zip(('monthly', 'large_monthly', 'medal_daily', 'medal_weekly',
                      'online_1', 'online_2', 'online_3'), range(10, 17)))
    def panel(self, im, page=None):
        if im.page == 'home' or (page and im.page != page):
            raise RuntimeError('未显示所需面板')
        return (0, 0)
    def matches(self, im, name):
        return [{'box': [3, 0, 0, 0]}] if name == 'close' and im.page != 'home' else []
    def unique(self, im, name):
        return [{'daily_tab': 1, 'online_tab': 2, 'close': 3, 'entry': 0}[name], 0, 0, 0]
    def button(self, im, slot):
        self.panel(im, 'online' if slot.startswith('online') else 'daily')
        x = self.slots[slot]
        key = (x, im.tier if slot == 'medal_weekly' else None)
        if slot == 'monthly' or key in im.claimed:
            return {'state': 'unavailable', 'text': '已领取' if key in im.claimed else '购买', 'received': key in im.claimed}
        return {'state': 'claimable', 'point': (x, 0)}
    def tier(self, im):
        self.panel(im, 'daily')
        return im.tier
    def tier_point(self, im, name):
        return {'上忍': 4, '中忍': 5, '下忍': 6}[name], 0


class FakeOCR:
    def match(self, im, name):
        return [1] if im.page == 'home' else []


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='welfare-test-', dir=Path(__file__).resolve().parents[1]/'verification')
        self.addCleanup(self.temp.cleanup)
        self.window = FakeWindow()
        self.task = WelfareTask(self.window, FakeOCR(), self.temp.name, vision=FakeVision(), emit=lambda text: None)
        self.task.pause = lambda seconds: None

    def test_full_order_and_close(self):
        report = self.task.run()
        self.assertEqual(report['status'], 'done')
        self.assertEqual([x for x, y in self.window.inputs], [1, 11, 12, 13, 5, 13, 6, 13, 2, 14, 15, 16, 3])
        self.assertEqual(len(report['rewards']), 9)
        self.assertEqual(sum(r['status'] == 'claimed_confirmed' for r in report['rewards']), 8)
        self.assertEqual(self.window.page, 'home')

    def test_already_claimed_zero_claim_inputs(self):
        self.window.claimed.update((x, None) for x in (11, 12, 14, 15, 16))
        self.window.claimed.update((13, tier) for tier in ('上忍', '中忍', '下忍'))
        report = self.task.run()
        self.assertEqual(report['status'], 'done')
        self.assertTrue(all(x < 10 for x, y in self.window.inputs))

    def test_partial_send_failure_not_replayed(self):
        self.window.failed_input = True
        with self.assertRaisesRegex(RuntimeError, '释放失败'):
            self.task.run()
        self.assertEqual(len(self.window.inputs), 1)
        report = json.loads((Path(self.temp.name)/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'stopped')
        self.assertEqual(report['actions'][0]['state'], 'attempted')

    def test_no_feedback_stops_without_replay_or_false_claim(self):
        self.window.page = 'daily'
        self.window.ignore_claim = True
        clock = iter(range(1000))
        with patch('welfare_task.time.monotonic', side_effect=lambda: next(clock)):
            with self.assertRaisesRegex(RuntimeError, '反馈未确认'):
                self.task.run()
        self.assertEqual(self.window.inputs, [(11, 0)])
        self.assertFalse(any(r['status'] == 'claimed_confirmed' for r in self.task.report['rewards']))

    def test_stop_before_any_input(self):
        def stopped():
            raise RuntimeError('用户停止')
        self.task.checkpoint = stopped
        with self.assertRaisesRegex(RuntimeError, '用户停止'):
            self.task.run()
        self.assertFalse(self.window.inputs)

    def test_changed_frame_before_send(self):
        points = iter([(1, 0), (1, 0), (2, 0)])
        with self.assertRaisesRegex(RuntimeError, '发送前状态变化'):
            self.task.send('test', lambda im: next(points))
        self.assertFalse(self.window.inputs)

    def test_close_requires_home_feedback(self):
        with self.assertRaisesRegex(RuntimeError, '尚未关闭'):
            self.task.home(self.window)
        self.window.page = 'home'
        self.assertEqual(self.task.home(self.window), 'home')


if __name__ == '__main__':
    unittest.main(verbosity=2)
