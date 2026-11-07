import unittest
from unittest.mock import Mock,patch
from team_instance_rewards import read_number,read_rewards
import numpy as np

class RewardTests(unittest.TestCase):
    def test_nov1_single_digit_week_remaining(self):
        from PIL import Image
        from adapters.local_ocr import LocalOCR
        from team_instance_task import TeamInstanceTask,ASSETS
        from team_instance_rewards import read_frame
        flow=Mock();flow.ocr=LocalOCR();flow.items=[]
        path=ASSETS.parents[2]/'verification/failure-20261101-171528-6205c39f8d50-team_instance.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        self.assertEqual(read_frame(TeamInstanceTask(flow)),(9,3,5))

    def test_oct30_actual_failures_read_fifteen(self):
        from PIL import Image
        from adapters.local_ocr import LocalOCR
        from team_instance_task import TeamInstanceTask,ASSETS
        from team_instance_rewards import read_frame
        ocr=LocalOCR()
        for run in ('134435-efb5415e4e70','141933-b66cc4f84843'):
            path=ASSETS.parents[2]/f'verification/failure-20261030-{run}-team_instance.png'
            flow=Mock();flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
            flow.items=ocr.read(flow.image);flow.ocr=ocr
            self.assertEqual(read_frame(TeamInstanceTask(flow)),(15,5,5),run)

    def test_real_current_and_original_panel_counts(self):
        from PIL import Image
        from adapters.local_ocr import LocalOCR
        from team_instance_task import TeamInstanceTask,ASSETS
        from team_instance_rewards import read_frame
        ocr=LocalOCR()
        for source,want in [('rewards-panel-reference.png',(19,4,5)),('recommended-reference.png',(20,5,5)),('first-reference.png',(20,5,5))]:
            raw=Image.open(ASSETS/source).convert('RGB')
            if source=='recommended-reference.png':image=raw.crop((45,127,1965,1142))
            else:
                image=Image.new('RGB',(1920,1015));image.paste(raw,(240,80))
            flow=Mock();flow.image=np.array(image)[:,:,::-1].copy();flow.items=[];flow.ocr=ocr
            task=TeamInstanceTask(flow)
            self.assertEqual(read_frame(task),want,source)
            from team_instance_rewards import single_week_crop
            x,y,_,_=task.template(['reward_label'],(0,0,1920,1015))['box']
            self.assertIsNone(single_week_crop(flow.image,x,y),source)

    def test_number_validation(self):
        ocr=Mock();crop=np.zeros((28,32,3),dtype=np.uint8)
        def item(text,score=.99):return [{'text':text,'score':score}]
        for text,maximum,want in [('0',5,0),('19',20,19),('20',20,20),('5',5,5),('6',5,None),('21',20,None),('4a',5,None),(':5',5,None),('01',20,None)]:
            ocr.read.return_value=item(text)
            self.assertEqual(read_number(ocr,crop,maximum),want)
        ocr.read.return_value=item('4',.8);self.assertIsNone(read_number(ocr,crop,5))
        ocr.read.side_effect=[item('4'),item('5')];self.assertIsNone(read_number(ocr,crop,5))
    def test_two_frames_agree_zero_is_valid(self):
        task=Mock()
        def wait(reader):
            self.assertIsNone(reader());self.assertIsNone(reader());return reader()
        task.wait.side_effect=wait
        with patch('team_instance_rewards.read_frame',side_effect=[(19,4,5),(0,0,5),(0,0,5)]):
            self.assertEqual(read_rewards(task),(0,0,5))
    def test_unknown_breaks_stability(self):
        task=Mock()
        def wait(reader):
            for _ in range(3):self.assertIsNone(reader())
            return reader()
        task.wait.side_effect=wait
        with patch('team_instance_rewards.read_frame',side_effect=[(19,4,5),None,(19,4,5),(19,4,5)]):
            self.assertEqual(read_rewards(task),(19,4,5))
