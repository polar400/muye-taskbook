import unittest
from unittest.mock import Mock
from team_instance_task import TeamInstanceTask, ASSETS
from PIL import Image
import numpy as np

class TeamInstanceTests(unittest.TestCase):
    def test_live_selected_activity_can_participate(self):
        task = self.task()
        source = ASSETS.parents[2]/'verification/failure-20261023-134652-84f2addf5c43-team_instance.png'
        task.f.image = np.array(Image.open(source).convert('RGB'))[:,:,::-1].copy()
        self.assertIsNotNone(task.row())
        self.assertTrue(task.selected())
        self.assertIsNotNone(task.participate())
        task.f.image[150:190,1160:1310] = 0
        self.assertIsNone(task.participate())

    def test_failed_live_home_kunai(self):
        from adapters.local_ocr import LocalOCR
        task = self.task()
        source = ASSETS.parents[2]/'verification/failure-20261023-133956-1a3c7e37dd58-team_instance.png'
        task.f.image = np.array(Image.open(source).convert('RGB'))[:,:,::-1].copy()
        task.f.ocr = LocalOCR()
        self.assertIsNotNone(task.kunai())

    def task(self):
        flow = Mock()
        flow.image = np.array(Image.open(ASSETS/'activities-game.png').convert('RGB'))[:,:,::-1].copy()
        flow.items = []
        return TeamInstanceTask(flow)

    def test_real_active_tab_and_team_row(self):
        task = self.task()
        self.assertIsNotNone(task.limited())
        self.assertIsNotNone(task.row())

    def test_real_kunai_pixels_but_background_icon_cannot_be_clicked(self):
        task = self.task()
        match = task.template(['kunai'],(0,100,270,400))
        self.assertGreater(match['score'],.99)
        self.assertIsNone(task.kunai())

    def test_duplicate_row_stops(self):
        task = self.task()
        task.f.image[400:451,303:448] = task.f.image[286:337,303:448].copy()
        with self.assertRaisesRegex(RuntimeError,'不唯一'):
            task.row()

    def test_highlight_with_other_detail_never_participates(self):
        task = self.task()
        task.f.items = [dict(text='羁绊对决',score=.99,box=[1152,140,138,34])]
        self.assertIsNone(task.participate())

    def test_matching_detail_authorizes_real_participate_template(self):
        task = self.task()
        task.f.items = [dict(text='组队副本',score=.99,box=[1152,140,138,34])]
        self.assertIsNotNone(task.participate())

    def test_popup_blocks_navigation(self):
        task = self.task()
        task.f.items = [dict(text='确定',score=.99,box=[850,500,80,30])]
        self.assertIsNone(task.limited())
        self.assertIsNone(task.row())
        self.assertIsNone(task.participate())

    def test_blank_and_wrong_size_rejected(self):
        task = self.task()
        task.f.image[:] = 0
        self.assertIsNone(task.row())
        task.f.image = task.f.image[::2,::2]
        with self.assertRaisesRegex(RuntimeError,'1920'):
            task.limited()

    def test_click_is_never_replayed_after_input_error(self):
        task = self.task()
        task.wait = Mock(return_value=dict(box=[1,2,30,40]))
        task.f.click_item.side_effect = RuntimeError('uncertain input')
        with self.assertRaisesRegex(RuntimeError,'uncertain'):
            task.click('参加',Mock())
        with self.assertRaisesRegex(RuntimeError,'重复'):
            task.click('参加',Mock())
        self.assertEqual(task.f.click_item.call_count,1)

    def test_timeout_sends_no_click(self):
        task = self.task()
        task.clock = Mock(side_effect=[0,0,0,31])
        with self.assertRaises(TimeoutError):
            task.click('参加',lambda:None)
        task.f.click_item.assert_not_called()

    def test_successful_navigation_is_not_opened_claim(self):
        task = self.task()
        task.limited = Mock(return_value=True)
        task.wait = Mock(return_value=True)
        task.click = Mock()
        task.f.cfg = {}
        self.assertEqual(task.run(),'opened')
        self.assertEqual([c.args[0] for c in task.click.call_args_list],['组队副本条目','参加'])

if __name__=='__main__':
    unittest.main()
