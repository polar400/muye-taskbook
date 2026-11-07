from unittest.mock import Mock
import unittest
from team_instance_task import TeamInstanceTask,ASSETS
from PIL import Image
import numpy as np

class CloseTests(unittest.TestCase):
    def task(self):
        flow=Mock();flow.items=[];flow.cfg={}
        flow.image=np.array(Image.open(ASSETS/'recommended-reference.png').convert('RGB').crop((45,127,1965,1142)))[:,:,::-1].copy()
        return TeamInstanceTask(flow)

    def test_actual_close_and_background_home_exclusion(self):
        task=self.task()
        self.assertIsNotNone(task.template(['dungeon_close'],(1500,40,1750,180)))
        self.assertFalse(task.home_visible())

    def test_close_once_then_two_home_observations(self):
        task=self.task();calls=[]
        def click(label,reader):
            self.assertIsNotNone(reader());calls.append(label)
        task.click=click;task.home_visible=Mock(side_effect=[False,True,True])
        task.sleep=Mock()
        task.return_home()
        self.assertEqual(calls,['关闭组队副本'])
        self.assertEqual(task.home_visible.call_count,3)
