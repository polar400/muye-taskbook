"""Mission Desk presentation integration; isolated storage and no game access."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

import app
import mission_desk_ui


class MissionDeskUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mission-ui-', dir=app.ROOT/'verification')
        self.folder = Path(self.temp.name)
        self.patches = [patch.object(app, 'ROOT', self.folder),
                        patch.object(app, 'game_windows', return_value=[]),
                        patch.object(app.subprocess, 'Popen', side_effect=AssertionError('No game worker allowed'))]
        for item in self.patches:
            item.start()
        self.ui = app.App()
        self.ui.update()

    def tearDown(self):
        for timer in self.ui.tk.call('after', 'info'):
            self.ui.after_cancel(timer)
        self.ui.destroy()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_editing_and_navigation_leave_saved_configuration_untouched(self):
        before = self.ui.config()
        for task, _ in app.TASKS:
            self.ui.gears[task].invoke()
            self.assertEqual(self.ui.selected.get(), task)
            self.assertEqual(self.ui.gears[task].cget('text'), '编辑中')
            for mode in ('common', 'advanced'):
                self.ui.show_task(task, mode)
                self.ui.update()
        for panel, button, _ in self.ui.nav_buttons:
            button.invoke()
            self.ui.update()
            self.assertEqual(self.ui.notebook.select(), str(panel))
            self.assertEqual(button.cget('bg'), mission_desk_ui.INK)
        self.assertEqual(self.ui.config(), before)
        self.assertFalse((self.folder/'config.json').exists())
        self.assertFalse((self.folder/'run.json').exists())

    def test_real_event_status_is_visible_without_promoting_partial_work(self):
        ui = self.ui
        ui.running = True
        ui.events.put({'kind': 'task', 'id': 'escort', 'status': 'accepted',
                       'message': '已接取，待交付'})
        ui.events.put({'kind': 'node', 'message': '排位战 · 正在识别挑战面板'})
        ui.events.put({'kind': 'error', 'message': '识别不确定，停止队列'})
        ui.drain()
        self.assertEqual(ui.statuses['escort'].get(), '已接取，待交付')
        self.assertEqual(str(ui.task_state_labels['escort'].cget('textvariable')), str(ui.statuses['escort']))
        self.assertEqual(ui.queue_summary.get(), '01 / 06')
        self.assertTrue(ui.status.get().startswith('失败：'))
        self.assertEqual(ui.step_status.get(), '排位战 · 正在识别挑战面板')
        self.assertIn('识别不确定', ui.log_text.get('1.0', 'end'))
        ui.events.put({'kind': 'exit', 'message': '1'})
        ui.drain()
        self.assertFalse(ui.running)
        self.assertEqual(str(ui.start_button.cget('state')), 'normal')

    def test_hidden_scrollbars_keep_independent_mousewheel_and_log_follow(self):
        ui = self.ui
        ui.geometry('940x680')
        ui.show_task('survival', 'advanced')
        ui.update()
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        self.assertFalse(any(isinstance(widget, (tk.Scrollbar, ttk.Scrollbar)) for widget in children(ui)))
        ui.task_canvas.yview_moveto(0)
        ui.task_fields.winfo_children()[0].event_generate('<MouseWheel>', delta=-120)
        ui.update()
        self.assertGreater(ui.task_canvas.yview()[0], 0)
        for index in range(100):
            ui.log(f'隔离测试日志 {index}')
        ui.follow_logs.set(False)
        ui.log_text.yview_moveto(0)
        position = ui.task_canvas.yview()
        ui.log_text.event_generate('<MouseWheel>', delta=-120)
        ui.update()
        self.assertGreater(ui.log_text.yview()[0], 0)
        self.assertEqual(ui.task_canvas.yview(), position)
        ui.follow_logs.set(True)
        ui.log('恢复日志跟随')
        ui.update()
        self.assertGreater(ui.log_text.yview()[1], .99)


if __name__ == '__main__':
    unittest.main()
