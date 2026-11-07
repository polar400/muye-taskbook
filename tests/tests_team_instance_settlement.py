import unittest
from unittest.mock import Mock,patch
import tests_team_instance
from team_instance_settlement import Settlement,finish_challenge
from team_instance_task import ASSETS
from PIL import Image
import numpy as np

class SettlementTests(unittest.TestCase):
    def task(self,name):
        t=tests_team_instance.TeamInstanceTests().task()
        t.f.image=np.array(Image.open(ASSETS/('settlement-'+name+'.png')))[:,:,::-1].copy()
        return t

    def test_three_real_states(self):
        for name,selected in [('sealed',None),('picked',0),('revealed',0)]:
            t=self.task(name);s=Settlement(t)
            self.assertTrue(s.title())
            for row in range(2):self.assertEqual(s.row(row)['selected'],selected)
            self.assertIsNotNone(t.template(['return_game','return_game_revealed'],(1100,850,1600,990)))

    def test_existing_selection_not_clicked_again(self):
        t=self.task('revealed');s=Settlement(t)
        t.wait=lambda reader:reader()
        t.click=Mock()
        s.home=Mock(return_value=True)
        self.assertEqual(s.run(),'completed')
        self.assertEqual([c.args[0] for c in t.click.call_args_list],['返回游戏'])

    def test_shared_auto_called_then_settlement(self):
        t=Mock();t.timeout=30;t.f.cfg={'battleSeconds':900}
        with patch('team_instance_settlement.Settlement') as cls:
            cls.return_value.title.return_value=False
            cls.return_value.run.return_value='completed'
            self.assertEqual(finish_challenge(t),'completed')
            t.f.auto.assert_called_once()
            self.assertEqual(t.timeout,30)

    def test_each_row_once_then_return_and_two_home_frames(self):
        t=self.task('sealed');s=Settlement(t);chosen=[None,None];calls=[]
        s.row=lambda row:dict(selected=chosen[row],cards=[dict(box=[1,2,3,4])]*5)
        def wait(reader):
            result=reader()
            if not result:result=reader()
            self.assertTrue(result);return result
        def click(label,reader):
            self.assertTrue(reader());calls.append(label)
            if label.startswith('结算翻牌'):chosen[int(label[-1])]=2
        t.wait=wait;t.click=click;s.home=Mock(return_value=True)
        with patch('team_instance_settlement.random.randrange',return_value=2):self.assertEqual(s.run(),'completed')
        self.assertEqual(calls,['结算翻牌0','结算翻牌1','返回游戏'])
        self.assertEqual(s.home.call_count,2)
