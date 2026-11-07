import unittest
from unittest.mock import Mock,patch
from PIL import Image
import tests_team_instance
from team_instance_challenge import Challenge,LEVELS
from team_instance_task import ASSETS,validate_team_instance_config
import numpy as np

class ChallengeTests(unittest.TestCase):
    def test_real_nov6_top_is_recognized_and_not_scrolled_up(self):
        for run in ('134825-91b79294b0aa','142506-94f7203e39c5'):
            c=self.page('first')
            c.f.image=np.array(Image.open(ASSETS.parents[2]/f'verification/failure-20261106-{run}-team_instance.png').convert('RGB'))[:,:,::-1].copy()
            self.assertIsNotNone(c.target(LEVELS[0]))
            self.assertEqual(c.boundary(),'top')
            c.hold_scroll=Mock()
            self.assertIsNotNone(c.find_target(LEVELS[0]))
            c.hold_scroll.assert_not_called()
            directions=[]
            def scroll(direction,index):
                directions.append(direction)
                raise RuntimeError('navigation probe')
            c.hold_scroll=scroll
            with self.assertRaisesRegex(RuntimeError,'navigation probe'):c.find_target(LEVELS[-1])
            self.assertEqual(directions,['down'])

    def test_scrollbar_reference_boundaries(self):
        for page,want in [('first','top'),('middle',None),('last','bottom')]:
            self.assertEqual(self.page(page).boundary(),want)

    def test_bottom_live_without_ocr(self):
        c=self.page('first')
        c.f.image=np.array(Image.open(ASSETS/'bottom-live-20261023.png').convert('RGB'))[:,:,::-1].copy()
        self.assertIsNotNone(c.target(LEVELS[-1]))

    def test_bottom_stops_without_more_clicks(self):
        t=Mock();c=Challenge(t)
        c.hold_scroll=Mock();c.boundary=Mock(return_value=None)
        c.target=lambda name:dict(box=[1,2,3,4]) if name==LEVELS[-1] else None
        with self.assertRaisesRegex(RuntimeError,'到底部'):c.find_target('missing')
        self.assertEqual(c.hold_scroll.call_count,3)
        t.click.assert_not_called()

    def test_real_recommended_pages_after_participate(self):
        for run in ('184045-0d5b602b8845','184132-d35ccd0b5b03'):
            c=self.page('first')
            source=ASSETS.parents[2]/('verification/failure-20261023-'+run+'-team_instance.png')
            c.f.image=np.array(Image.open(source).convert('RGB'))[:,:,::-1].copy()
            self.assertTrue(c.panel(),run)
            self.assertIsNone(c.all_tab())

    def page(self,name):
        task=tests_team_instance.TeamInstanceTests().task()
        image=Image.new('RGB',(1920,1015))
        image.paste(Image.open(ASSETS/(name+'-reference.png')),(240,80))
        task.f.image=np.array(image)[:,:,::-1].copy()
        task.f.items=[]
        return Challenge(task)

    def test_all_nine_names_and_difficulty_from_references(self):
        for page,names in (('first',LEVELS[:4]),('middle',LEVELS[4:8]),('last',LEVELS[6:])):
            c=self.page(page)
            if page=='last':
                c.f.items=[dict(text='活动副本尚未开启',score=1,box=[1100,750,120,30])]
            self.assertTrue(c.panel())
            for name in names:
                with self.subTest(name=name):
                    card=c.target(name)
                    self.assertIsNotNone(card)
                    self.assertEqual(c.difficulty(card)[0],'简单' if name==LEVELS[8] else '困难')

    def test_unrelated_missing_card_does_not_block_target(self):
        c=self.page('first')
        c.f.image[770:820,960:1100]=0
        self.assertIsNotNone(c.target(LEVELS[0]))
        self.assertIsNone(c.target(LEVELS[3]))

    def test_confirmation_requires_warning_not_just_button(self):
        c=self.page('confirm')
        self.assertIsNotNone(c.confirm())
        c.f.image[155:195,280:820]=0
        self.assertIsNone(c.confirm())

    def test_two_difficulty_steps_then_one_confirmation(self):
        t=Mock();c=Challenge(t)
        card=dict(box=[370,460,99,29]);box=dict(box=[637,454,88,35])
        state={'difficulty':'困难'};labels=[]
        c.panel=Mock(return_value=True);c.all_tab=Mock(return_value=card)
        c.target=Mock(return_value=card);c.confirm=Mock(return_value=card)
        c.difficulty=lambda _: (state['difficulty'],box)
        def click(label,reader):
            self.assertTrue(reader());labels.append(label)
            if label.startswith('调整'):state['difficulty']='普通' if state['difficulty']=='困难' else '简单'
        t.click=click;t.wait=lambda reader:self.assertTrue(reader())
        with patch('team_instance_settlement.finish_challenge',return_value='completed') as finish:
            self.assertEqual(c.run(LEVELS[0],'简单'),'completed')
            finish.assert_called_once_with(t)
        self.assertEqual(labels,['全部副本','调整难度0','调整难度1','进入所选关卡','确认进入挑战'])

    def test_invalid_selection_rejected(self):
        with self.assertRaises(ValueError):
            validate_team_instance_config(dict(tasks=['team_instance'],teamInstanceName='不存在',teamInstanceDifficulty='简单'))

