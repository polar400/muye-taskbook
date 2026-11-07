"""Isolated UI feedback for the ranked pilot, no game or user config access."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import app
from failure_archive import RunFailureTracker


class PipelineFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pipeline-ui-',dir=app.ROOT/'verification')
        self.root = Path(self.temp.name)
        self.patches = [patch.object(app,'ROOT',self.root),patch.object(app.App,'refresh_windows')]
        for p in self.patches:
            p.start()
        self.ui = app.App()
        self.ui.update()

    def tearDown(self):
        for callback in self.ui.tk.call('after','info'):
            self.ui.after_cancel(callback)
        self.ui.destroy()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_current_step_progress_and_failure_remain_visible(self):
        message = '排位战 · 等待结算 · 已完成1场，剩余2次'
        self.ui.events.put({'kind':'node','message':message,'id':'ranked','status':'running'})
        self.ui.drain()
        self.assertEqual(self.ui.step_status.get(),message)
        self.ui.events.put({'kind':'task','message':'排位战：未完成','id':'ranked','status':'failed'})
        self.ui.events.put({'kind':'error','message':'胜负无法可靠识别'})
        self.ui.drain()
        self.assertEqual(self.ui.statuses['ranked'].get(),'未完成')
        self.assertIn('胜负无法',self.ui.status.get())
        self.assertEqual(self.ui.step_status.get(),message)

    def test_skip_is_terminal_in_ui_and_failure_tracker(self):
        event = {'kind':'task','message':'排位战：次数为0，已跳过并返回主页','id':'ranked','status':'skipped'}
        self.ui.events.put(event)
        self.ui.drain()
        self.assertEqual(self.ui.statuses['ranked'].get(),'已跳过')
        tracker = RunFailureTracker(self.root,'pipeline-skip')
        tracker.observe({'kind':'task','message':'排位战：运行中','id':'ranked','status':'running'})
        tracker.observe(event)
        self.assertTrue(tracker.finished)
        self.assertIsNone(tracker.event({'kind':'exit','message':'0'}))


if __name__ == '__main__':
    unittest.main()
