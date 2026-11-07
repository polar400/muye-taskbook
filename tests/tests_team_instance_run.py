from datetime import datetime
import unittest
from unittest.mock import Mock,patch
from team_instance_task import TeamInstanceTask
import numpy as np
from team_instance_daily import BEIJING,daily_limit,is_open,run_daily

def at(hour,day=25):return datetime(2026,10,day,hour,tzinfo=BEIJING)

class RunTests(unittest.TestCase):
    def setUp(self):
        self.flow=Mock();self.flow.cfg={'teamInstanceDailyCount':3}
        self.flow.image=np.zeros((1015,1920,3),dtype=np.uint8)
        self.flow.ocr.match.return_value=[]
        self.tasks=[]
        def factory(flow):
            task=Mock();task.run.return_value='completed';self.tasks.append(task);return task
        self.factory=factory
        self.p=patch('team_instance_settlement.Settlement');self.settlement=self.p.start().return_value
        self.settlement.title.return_value=False
    def tearDown(self):self.p.stop()
    def run_flow(self,rewards=(19,4,5),clock=lambda:at(10)):
        return run_daily(self.flow,clock,self.factory,lambda task:rewards)
    def count(self):return sum(t.run.call_count for t in self.tasks)
    def test_each_start_uses_settings_again(self):
        self.assertEqual(self.run_flow(),'daily_completed');self.assertEqual(self.count(),3)
        self.tasks=[];self.run_flow();self.assertEqual(self.count(),3)
    def test_daily_weekly_limits_and_friendship_not_gate(self):
        for rewards,expected in [((19,2,5),2),((1,4,5),1),((19,4,0),3),((0,4,5),0),((19,0,5),0)]:
            self.tasks=[];self.run_flow(rewards);self.assertEqual(self.count(),expected)
            self.tasks[-1].return_home.assert_called_once()
    def test_five_requested_four_left(self):
        self.flow.cfg['teamInstanceDailyCount']=5
        self.run_flow((19,4,5));self.assertEqual(self.count(),4)
    def test_rewards_rechecked_before_next_challenge(self):
        reader=Mock(side_effect=[(19,4,5),(18,0,5)])
        run_daily(self.flow,lambda:at(10),self.factory,reader)
        self.assertEqual(self.count(),1);self.assertEqual(reader.call_count,2)
    def test_battle_requires_unique_auto_and_speed_controls(self):
        from team_instance_daily import battle_visible
        self.flow.ocr.match.side_effect=lambda image,name:[{}] if name in ('auto_on','speed2') else []
        self.assertTrue(battle_visible(self.flow))
        self.flow.ocr.match.side_effect=lambda image,name:[{}] if name=='auto_on' else []
        self.assertFalse(battle_visible(self.flow))
    def test_settlement_counts_one(self):
        self.settlement.title.return_value=True
        self.run_flow();self.assertEqual(self.count(),2);self.settlement.run.assert_called_once()
    def test_battle_counts_one(self):
        with patch('team_instance_daily.battle_visible',return_value=True),patch('team_instance_settlement.finish_challenge') as finish:
            self.run_flow();self.assertEqual(self.count(),2);finish.assert_called_once()
    def test_closed_no_entry(self):
        self.assertEqual(self.run_flow(clock=lambda:at(7)),'closed')
        self.assertEqual(self.count(),0);self.tasks[0].open_panel.assert_not_called()
    def test_closed_can_finish_existing(self):
        self.settlement.title.return_value=True
        self.assertEqual(self.run_flow(clock=lambda:at(0)),'closed')
        self.assertEqual(self.count(),0);self.tasks[0].return_home.assert_called_once()
    def test_failed_challenge_stops(self):
        def factory(flow):
            task=self.factory(flow);task.run.side_effect=RuntimeError('unknown');return task
        with self.assertRaisesRegex(RuntimeError,'unknown'):
            run_daily(self.flow,lambda:at(10),factory,lambda t:(19,4,5))
        self.assertEqual(self.count(),1)
    def test_unknown_rewards_no_challenge(self):
        with self.assertRaisesRegex(RuntimeError,'unreadable'):
            run_daily(self.flow,lambda:at(10),self.factory,Mock(side_effect=RuntimeError('unreadable')))
        self.assertEqual(self.count(),0)
    def test_boundaries_and_invalid_setting(self):
        self.assertFalse(is_open(at(7)));self.assertTrue(is_open(at(8)));self.assertTrue(is_open(at(23)));self.assertFalse(is_open(at(0)))
        for value in (0,6,True,'3'):
            with self.assertRaises(ValueError):daily_limit({'teamInstanceDailyCount':value})
