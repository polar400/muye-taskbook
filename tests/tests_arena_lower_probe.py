"""No native process access: bounded lower acceptance and authorization checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from arena_daily import board_key
from arena_lower_probe import LowerOnceProbe
from arena_virtual_pointer import PointerTransaction
from tests_arena_virtual_pointer import Memory
from tools import probe_arena_lower_virtual as tool


class Clock:
    def __init__(self):self.value=0
    def now(self):return self.value
    def sleep(self,delay):self.value+=delay


class Fixture:
    def __init__(self):
        self.clock=Clock();self.stage='before';self.hovered=False;self.clicks=[];self.moves=[]
        self.hover_works=True;self.paid=False;self.ambiguous=False;self.uncertain=False
        self.change=True;self.change_other=False;self.slow=False;self.moved=False
        self.board_before=dict(remaining=4,cards=[
            dict(index=0,description='condition A',state='unmet',progress=0,hovered=False,
                 button=dict(box=[220,490,100,30])),
            dict(index=1,description='condition B',state='unmet',progress=0,hovered=False,
                 button=dict(box=[220,680,100,30]))])
        self.confirm=dict(box=[900,620,100,40])
        self.window=Mock(capture=self.capture,hover=self.hover,click=self.click)
        flow=Mock(window=self.window,ocr=Mock(read=lambda image:[]),image=None,items=[])
        self.runner=Mock(f=flow,board=self.board,fresh_card=self.fresh,lower_dialog=self.dialog)
        self.pointers=[]
        for _ in range(2):
            memory=Memory();entries=[(100,b'old1',b'new1'),(200,b'old2',b'new2')]
            pointer=Mock(memory=memory,transaction=PointerTransaction(memory,entries),
                         evidence=dict(entries=[dict(address=a,original=o.hex()) for a,o,r in entries]))
            self.pointers.append(pointer)
        self.snapshots=[]
        self.probe=LowerOnceProbe(self.runner,self.pointers,
            lambda label,report:self.snapshots.append((label,deepcopy(report))),
            clock=self.clock.now,sleep=self.clock.sleep)

    def capture(self):
        active=any(p.prepare.called for p in self.pointers)
        self.clock.sleep(2 if self.slow and active else .02);return 'frame'
    def hover(self,*point):self.moves.append(point);self.hovered=self.hover_works
    def click(self,*point):
        self.clicks.append(point)
        self.stage='dialog' if len(self.clicks)==1 else 'after'
        if self.uncertain:raise RuntimeError('uncertain input')
    def board(self):
        if self.stage=='dialog':return None
        board=deepcopy(self.board_before);board['cards'][0]['hovered']=self.hovered
        if self.stage=='after' and self.change:
            board['cards'][0].update(state='eligible',description='easier A')
            if self.change_other:board['cards'][1]['description']='unexpected B'
        return board
    def fresh(self,expected,index,state,hovered=False):
        board=self.board()
        if board_key(board)!=board_key(expected):raise RuntimeError('changed before click')
        if hovered and not self.hovered:return None
        button=deepcopy(board['cards'][index]['button'])
        if self.moved:button['box'][0]+=300
        return button
    def dialog(self):
        if self.paid:raise RuntimeError('出现消耗提示')
        if self.ambiguous:raise RuntimeError('确认按钮不唯一')
        return self.confirm if self.stage=='dialog' else None


class LowerProbeTests(unittest.TestCase):
    def assert_restored(self,fixture):
        self.assertTrue(all(p.memory.values=={100:b'old1',200:b'old2'} for p in fixture.pointers))

    def test_one_task_changes_after_exactly_two_clicks(self):
        f=Fixture();report=f.probe.run()
        self.assertEqual(report['result'],'lower-change-confirmed')
        self.assertEqual(len(f.clicks),2);self.assertEqual(len(f.moves),2)
        self.assertEqual([e['status'] for e in report['inputs']],['sent','sent'])
        self.assertTrue(all(p['restored'] for p in report['phases']));self.assert_restored(f)

    def test_no_hover_feedback_stops_without_any_click(self):
        f=Fixture();f.hover_works=False
        with self.assertRaises(TimeoutError):f.probe.run()
        self.assertEqual(f.clicks,[]);self.assert_restored(f)

    def test_paid_and_ambiguous_dialogs_never_confirm(self):
        for flag in ('paid','ambiguous'):
            with self.subTest(flag=flag):
                f=Fixture();setattr(f,flag,True)
                with self.assertRaises(RuntimeError):f.probe.run()
                self.assertEqual(len(f.clicks),1);self.assert_restored(f)

    def test_slow_fresh_read_cannot_click_near_expiry(self):
        f=Fixture();f.slow=True
        with self.assertRaises(TimeoutError):f.probe.run()
        self.assertEqual(f.clicks,[]);self.assert_restored(f)

    def test_new_button_outside_virtual_point_never_clicks(self):
        f=Fixture();f.moved=True
        with self.assertRaisesRegex(RuntimeError,'位置不一致'):f.probe.run()
        self.assertEqual(f.clicks,[]);self.assert_restored(f)

    def test_uncertain_first_click_is_not_replayed_or_confirmed(self):
        f=Fixture();f.uncertain=True
        with self.assertRaisesRegex(RuntimeError,'uncertain'):f.probe.run()
        self.assertEqual(len(f.clicks),1)
        self.assertEqual(f.probe.report['inputs'][0]['status'],'sending');self.assert_restored(f)

    def test_no_change_after_confirmation_does_not_report_success(self):
        f=Fixture();f.change=False
        with self.assertRaises(TimeoutError):f.probe.run()
        self.assertEqual(len(f.clicks),2)
        self.assertEqual(f.probe.report['result'],'failed');self.assert_restored(f)

    def test_change_to_unselected_task_does_not_report_success(self):
        f=Fixture();f.change_other=True
        with self.assertRaisesRegex(RuntimeError,'未操作的任务'):f.probe.run()
        self.assertEqual(len(f.clicks),2);self.assert_restored(f)

    def test_consumed_hover_authorization_is_not_a_lower_authorization(self):
        with tempfile.TemporaryDirectory(prefix='arena-lower-auth-',dir=Path(__file__).resolve().parents[1]/'verification') as folder:
            root=Path(folder);(root/'verification').mkdir()
            (root/'verification/arena-virtual-pointer-authorization-20261020.json').write_text(
                '{"decision":"allowed_by_user","remaining":1}',encoding='utf-8')
            with patch.object(tool,'ROOT',root):
                with self.assertRaisesRegex(RuntimeError,'旧悬停授权已用完'):tool.read_authorization()

    def test_pending_current_authorization_blocks_before_native_calls(self):
        with tempfile.TemporaryDirectory(prefix='arena-lower-auth-',dir=Path(__file__).resolve().parents[1]/'verification') as folder:
            root=Path(folder);(root/'verification').mkdir()
            (root/'verification/arena-lower-virtual-authorization-20261020.json').write_text(
                '{"decision":"pending","remaining":0,"scopeCode":"arena-lower-confirm-once"}',encoding='utf-8')
            with patch.object(tool,'ROOT',root):
                with self.assertRaisesRegex(RuntimeError,'尚未获准'):tool.read_authorization()

    def test_phase_timing_is_recorded_without_changing_click_limit(self):
        f=Fixture();report=f.probe.run()
        self.assertEqual(len(f.clicks),2)
        for phase in report['phases']:
            self.assertIn('prepareSeconds',phase);self.assertIn('totalSeconds',phase)
            self.assertTrue(phase['reads'][0]['found'])
            self.assertGreater(phase['observations'][0]['captureSeconds'],0)
            self.assertIn('ocrSeconds',phase['observations'][0])
            self.assertIn('saveSeconds',phase['observations'][0])

    def test_slow_input_evidence_save_does_not_send_click(self):
        f=Fixture();save=f.probe.save
        def slow(label,report):
            save(label,report)
            if label.endswith('-input'):f.clock.sleep(2)
        f.probe.save=slow
        with self.assertRaises(TimeoutError):f.probe.run()
        self.assertEqual(f.clicks,[])
        self.assertEqual(f.probe.report['inputs'][0]['status'],'not-sent');self.assert_restored(f)

    def test_restore_failure_after_first_click_blocks_confirmation(self):
        f=Fixture();click=f.window.click
        def conflict(*point):
            click(*point);f.pointers[0].memory.values[200]=b'else'
        f.window.click=conflict
        with self.assertRaisesRegex(RuntimeError,'恢复未确认'):f.probe.run()
        self.assertEqual(len(f.clicks),1)
        self.assertEqual(f.pointers[0].memory.values,{100:b'old1',200:b'else'})
        self.assertFalse(f.probe.report['phases'][0]['restored'])


if __name__=='__main__':unittest.main()
