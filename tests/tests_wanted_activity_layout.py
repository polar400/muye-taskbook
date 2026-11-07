"""Completed daily-list variants: saved pixels and mocked game IO only."""
import hashlib
import json
import unittest
from unittest.mock import Mock, call, patch

from adapters.local_ocr import LocalOCR
import numpy as np
from PIL import Image
from local_flows import LocalFlows
from wanted_task import WantedTask
from tests_wanted import ROOT

FAILURES=('3bbb2b405695d9d538e256a6','c16d65c386bdf5451ff4362a','d12d52e1af766a07db527f97')


class WantedActivityLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def task(self,identity=FAILURES[-1]):
        flow=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
        flow.image=np.array(Image.open(ROOT/f'出错任务/通缉任务/证据/{identity}.png').convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        return WantedTask(flow)

    def test_three_real_timeouts_have_completed_list_and_need_two_frames(self):
        for identity in FAILURES:
            with self.subTest(identity=identity):
                task=self.task(identity)
                self.assertIsNone(task.button('wanted_row',(.14,.16,.3,.74)))
                close=task.completed_activity_close()
                self.assertIsNotNone(close)
                self.assertEqual(close['box'],[1622,21,46,50])
                self.assertFalse(task.activity_completed())
                self.assertTrue(task.activity_completed())
                task.f.window.click.assert_not_called()

    def test_real_initial_completed_list_runs_to_home_without_auto_or_participate(self):
        task=self.task();flow=task.f;activity=flow.image.copy()
        home=np.array(Image.open(ROOT/'resources/local/catalog/home/20261016-973-village/game.png').convert('RGB'))[:,:,::-1].copy()
        state={'image':activity};flow.capture_ready=Mock(side_effect=lambda:state['image'])
        def click(x,y):
            if (x,y)==(1645,46):state['image']=home
        flow.window.click.side_effect=click
        with patch('local_flows.time.sleep'):
            task.run()
        self.assertEqual(flow.window.click.call_args_list,[call(399,95),call(1645,46)])
        self.assertEqual(task.sent,{'日常活动','关闭已完成日常活动'})
        self.assertTrue(task.home_visible())

    def test_variant_keeps_identity_wanted_dialog_and_close_guards(self):
        for feature in ('tab','rows','close','wanted-text','wanted-art','detail','dialog'):
            with self.subTest(feature=feature):
                task=self.task();flow=task.f
                if feature=='tab':flow.image[50:140,290:510]=0
                elif feature=='rows':flow.image[330:475,310:475]=0
                elif feature=='close':flow.image[15:80,1615:1675]=0
                elif feature=='wanted-text':flow.items.append({'text':'通缉任务','score':.99,'box':[350,350,120,35]})
                elif feature=='wanted-art':
                    active=np.array(Image.open(ROOT/'resources/local/catalog/activities/20261016-973-daily/game.png').convert('RGB'))[:,:,::-1].copy()
                    flow.image[500:554,311:477]=active[337:391,311:477]
                    self.assertIsNotNone(task.button('wanted_row',(.14,.16,.3,.74)))
                elif feature=='detail':
                    active=np.array(Image.open(ROOT/'出错任务/通缉任务/证据/831508e2d050f1b570feb564.png').convert('RGB'))[:,:,::-1].copy()
                    flow.image[154:186,1185:1308]=active[154:186,1185:1308]
                else:flow.items.append({'text':'是','score':.99,'box':[820,550,30,25]})
                self.assertIsNone(task.completed_activity_close())
                flow.window.click.assert_not_called()

    def test_one_absent_frame_does_not_survive_missing_layout(self):
        task=self.task();self.assertFalse(task.activity_completed())
        original=task.f.image.copy();task.f.image[330:475,310:475]=0
        self.assertFalse(task.activity_completed())
        task.f.image=original
        self.assertFalse(task.activity_completed());self.assertTrue(task.activity_completed())

    def test_variant_close_requires_home_and_never_replays(self):
        task=self.task();activity=task.f.image.copy();task.f.capture_ready=Mock(return_value=activity)
        clock=[0];task.clock=lambda:clock[0]
        task.sleep=lambda _:clock.__setitem__(0,clock[0]+10)
        with patch('local_flows.time.sleep'),self.assertRaisesRegex(TimeoutError,'确认返回木叶村'):
            task.complete_from_activity()
        task.f.window.click.assert_called_once_with(1645,46)
        with self.assertRaisesRegex(RuntimeError,'拒绝重复'):
            task.complete_from_activity()
        task.f.window.click.assert_called_once()

    def test_new_template_pixels_and_source_hashes(self):
        manifest=json.loads((ROOT/'resources/local/wanted/completed-activity-layout-20261019.json').read_text(encoding='utf-8'))
        for entry in manifest['sources']:
            self.assertEqual(hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
        asset=manifest['asset']
        self.assertEqual(hashlib.sha256((ROOT/asset['path']).read_bytes()).hexdigest(),asset['sha256'])
        expected=np.array(Image.open(ROOT/asset['source']).convert('RGB').crop(asset['sourceBox']))
        self.assertTrue(np.array_equal(expected,np.array(Image.open(ROOT/asset['path']).convert('RGB'))))


if __name__=='__main__':unittest.main()
