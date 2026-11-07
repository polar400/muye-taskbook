"""Virtual-clock/message tests; no desktop handles or game inputs."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

import grocery_scroll as scroll
from tools import grocery_potion_live_test as probe
from grocery_recognition import np

ROOT=Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):self.value=0.0
    def now(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class Window:
    geometry=(0,107,1920,1015,1920,1122)
    def check(self):pass
    def measure(self):return self.geometry


class Messages:
    def __init__(self,clock,window,fail=None,changed=False):
        self.clock=clock;self.window=window;self.fail=fail;self.changed=changed
        self.events=[];self.point=None;self.restored=False
    @contextmanager
    def transport(self,window,point):
        self.point=point
        def send(message,value):
            self.events.append((message,value,self.clock.now()))
            return message!=self.fail
        def measure():
            if self.changed and self.clock.now()>=.4:return (1,107,1920,1015,1920,1122)
            return self.window.geometry
        try:yield send,measure
        finally:self.restored=True


class GroceryScrollTests(unittest.TestCase):
    def run_hold(self,direction='down',cancelled=lambda:False,fail=None,changed=False):
        clock=Clock();window=Window();messages=Messages(clock,window,fail,changed)
        result=scroll.scroll_once(window,direction,cancelled=cancelled,
                                 _transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
        return result,clock,messages

    def test_up_and_down_are_one_continuous_1_6_second_hold(self):
        for direction in ('up','down'):
            with self.subTest(direction=direction):
                result,clock,messages=self.run_hold(direction)
                self.assertTrue(result)
                self.assertEqual(messages.point,scroll.ARROW_POINTS[direction])
                self.assertEqual([row[0] for row in messages.events],[0x200,0x201,0x202])
                self.assertAlmostEqual(messages.events[-1][2]-messages.events[1][2],1.6,places=9)
                self.assertTrue(messages.restored)

    def test_thumb_drag_holds_exactly_1_6_seconds_and_releases(self):
        clock=Clock();window=Window();messages=Messages(clock,window)
        self.assertTrue(scroll.drag_thumb(window,660,560,_transport=messages.transport,_clock=clock.now,_sleep=clock.sleep))
        self.assertEqual(sum(row[0]==0x201 for row in messages.events),1)
        self.assertEqual(messages.events[-1][0],0x202)
        self.assertEqual(messages.point,(1567,560))
        self.assertAlmostEqual(messages.events[-1][2]-messages.events[1][2],1.6,places=9)

    def test_thumb_drag_cancellation_and_geometry_failure_always_release(self):
        for changing in (False,True):
            clock=Clock();window=Window();messages=Messages(clock,window,changed=changing)
            kwargs=dict(_transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
            if changing:
                with self.assertRaisesRegex(RuntimeError,'窗口变化'):
                    scroll.drag_thumb(window,660,560,**kwargs)
            else:
                self.assertFalse(scroll.drag_thumb(window,660,560,cancelled=lambda:clock.now()>=.4,**kwargs))
            self.assertEqual(messages.events[-1][0],0x202)

    def test_cancel_before_press_sends_nothing(self):
        result,clock,messages=self.run_hold(cancelled=lambda:True)
        self.assertFalse(result);self.assertEqual(messages.events,[])

    def test_cancel_during_hold_still_releases(self):
        clock=Clock();window=Window();messages=Messages(clock,window)
        result=scroll.scroll_once(window,'up',cancelled=lambda:clock.now()>=.4,
                                 _transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
        self.assertFalse(result)
        self.assertEqual(messages.events[-1][0],0x202)
        self.assertLess(messages.events[-1][2],1.6)
        self.assertTrue(messages.restored)

    def test_window_change_releases_before_reporting_error(self):
        clock=Clock();window=Window();messages=Messages(clock,window,changed=True)
        with self.assertRaisesRegex(RuntimeError,'窗口变化'):
            scroll.scroll_once(window,'down',_transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
        self.assertEqual(messages.events[-1][0],0x202);self.assertTrue(messages.restored)

    def test_unknown_press_result_always_attempts_release(self):
        clock=Clock();window=Window();messages=Messages(clock,window,fail=0x201)
        with self.assertRaisesRegex(RuntimeError,'按下结果不确定'):
            scroll.scroll_once(window,'down',_transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
        self.assertEqual([e[0] for e in messages.events],[0x200,0x201,0x202])
        self.assertTrue(messages.restored)

    def test_release_failure_is_not_reported_as_success(self):
        clock=Clock();window=Window();messages=Messages(clock,window,fail=0x202)
        with self.assertRaisesRegex(RuntimeError,'释放消息失败'):
            scroll.scroll_once(window,'up',_transport=messages.transport,_clock=clock.now,_sleep=clock.sleep)
        self.assertTrue(messages.restored)

    def test_invalid_direction_and_changed_initial_geometry_do_not_press(self):
        with self.assertRaises(ValueError):scroll.scroll_once(Window(),'left')
        window=Window();window.measure=lambda:(0,107,1600,900,1600,1000)
        with self.assertRaisesRegex(RuntimeError,'滚动前窗口'):
            scroll.scroll_once(window,'up')

    def test_probe_routes_both_directions_to_dedicated_hold_and_records_duration(self):
        source=ROOT/'verification/grocery-potion-live-20261031/02-current.png'
        with Image.open(source) as im:image=im.convert('RGB')
        class CaptureOnly:
            def capture(self):return np.asarray(image)[:,:,::-1].copy()
            def click(self,*args):raise AssertionError('Scroll must not become a click')
            def hold(self,*args,**kwargs):raise AssertionError('Shared one-second hold must not be used')
        for direction in ('up','down'):
            with self.subTest(direction=direction),tempfile.TemporaryDirectory(dir=ROOT/'verification') as temp:
                folder=Path(temp);window=CaptureOnly()
                with patch.object(probe,'FOLDER',folder),patch.object(probe.common,'active_worker_check'), \
                     patch.object(probe,'scroll_once',return_value=True) as hold,patch.object(probe.time,'sleep'):
                    probe.send(window,f'scroll-{direction}-1600ms-test',source,
                               [scroll.ARROW_BOXES[direction]],scroll.ARROW_POINTS[direction],1.6)
                hold.assert_called_once_with(window,direction)
                record=json.loads((folder/'input-journal.json').read_text(encoding='utf-8'))['actions'][0]
                self.assertEqual(record['duration_seconds'],1.6)
                self.assertEqual(record['direction'],direction)
                self.assertFalse(record['consuming'])


if __name__=='__main__':unittest.main()
