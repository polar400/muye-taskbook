"""Visible final layout after coalesced native resize; no game operations."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import app


class ResizeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='resize-test-',dir=app.ROOT/'verification')
        self.patches=[patch.object(app,'ROOT',Path(self.temp.name)),patch.object(app,'game_windows',return_value=[]),patch.object(app.subprocess,'Popen',side_effect=AssertionError('No game process'))]
        for p in self.patches:p.start()
        self.ui=app.App()
        self.settle()
    def settle(self):
        end=time.perf_counter()+.2
        while time.perf_counter()<end:self.ui.update();time.sleep(.003)
    def tearDown(self):
        for callback in self.ui.tk.call('after','info'):self.ui.after_cancel(callback)
        self.ui.destroy()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_resize_burst_finishes_with_readable_panes_and_matching_fields(self):
        for target in ('1500x900','940x680','1280x780'):
            for i in range(12):
                self.ui.geometry(f'{1000+i*20}x{690+i*4}');self.ui.update()
            self.ui.geometry(target);self.settle()
            widths=[self.ui.nametowidget(p).winfo_width() for p in self.ui.panes.panes()]
            self.assertGreaterEqual(widths[0],236)
            self.assertGreaterEqual(widths[1],330)
            self.assertGreaterEqual(widths[2],220)
            self.assertEqual(int(float(self.ui.task_canvas.itemcget(self.ui.task_field_window,'width'))),self.ui.task_canvas.winfo_width())
    def test_task_changes_still_refresh_scroll_region_at_same_window_size(self):
        self.ui.geometry('940x680')
        for key,_ in app.TASKS:
            self.ui.show_task(key,'advanced');self.settle()
            self.assertEqual(tuple(map(int,self.ui.task_canvas.cget('scrollregion').split())),self.ui.task_canvas.bbox('all'))
            self.assertTrue(self.ui.start_button.winfo_ismapped())


if __name__=='__main__':unittest.main()
