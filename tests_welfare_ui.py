"""Daily-task UI and worker integration with isolated files, no game access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import app
import native_worker
import welfare_task

PROJECT = Path(__file__).resolve().parent


class WelfareUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='welfare-ui-', dir=PROJECT/'verification')
        self.folder = Path(self.temp.name)
        self.patches = [patch.object(app, 'ROOT', self.folder), patch.object(app, 'game_windows', return_value=[])]
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

    def labels(self, widget):
        text = []
        for child in widget.winfo_children():
            if child.winfo_class() == 'TLabel':
                text.append(str(child.cget('text')))
            text.extend(self.labels(child))
        return text

    def test_task_card_and_both_settings_tabs(self):
        self.assertEqual(sum(key == 'welfare' for key, _ in app.TASKS), 1)
        self.ui.gears['welfare'].invoke()
        for mode in ('common', 'advanced'):
            self.ui.show_task('welfare', mode)
            self.ui.update()
            text = ' '.join(self.labels(self.ui.task_fields))
            for expected in ('月卡', '大月卡', '上忍', '中忍', '下忍', '在线', '关闭', '本地后台'):
                self.assertIn(expected, text)
            self.assertEqual(self.ui.task_title.cget('text'), '福利大厅')
            self.assertFalse(self.ui.plan_summary_label.winfo_ismapped())
        self.assertFalse((self.folder/'config.json').exists())

    def test_selection_order_and_save_reload(self):
        ui = self.ui
        ui.select_all(False)
        ui.selection['welfare'].set(True)
        ui.move_task('welfare', -1)
        order = list(ui.task_order)
        ui.save()
        ui.selection['welfare'].set(False)
        ui.load()
        self.assertEqual(ui.config()['tasks'], ['welfare'])
        self.assertEqual(ui.task_order, order)

    def test_drag_welfare_to_top_and_back_keeps_other_task_order(self):
        ui = self.ui
        original = list(ui.task_order)
        handle = ui.task_handles['welfare']
        for y, expected in ((-1000, ['welfare']+[key for key in original if key != 'welfare']),
                            (1500, original)):
            handle.event_generate('<ButtonPress-1>', x=10, y=14)
            handle.event_generate('<B1-Motion>', x=10, y=y)
            ui.update()
            handle.event_generate('<ButtonRelease-1>', x=10, y=y)
            ui.update()
            self.assertEqual(ui.task_order, expected)

    def test_old_config_adds_unselected_task_without_changing_saved_file(self):
        path = self.folder/'config.json'
        path.write_text(json.dumps({'tasks': ['hosting'], 'taskOrder': ['hosting', 'survival']}), encoding='utf-8')
        before = path.read_bytes()
        self.ui.load()
        self.assertIn('welfare', self.ui.task_order)
        self.assertFalse(self.ui.selection['welfare'].get())
        self.assertEqual(self.ui.config()['tasks'], ['hosting'])
        self.assertEqual(path.read_bytes(), before)

    def test_native_preview_includes_welfare_without_window_access(self):
        self.ui.select_all(False)
        self.ui.selection['welfare'].set(True)
        cfg = self.ui.config()
        cfg['preview'] = True
        path = self.folder/'preview.json'
        path.write_text(json.dumps(cfg), encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(PROJECT/'native_worker.py'), str(path)],
                                cwd=PROJECT, capture_output=True, text=True, encoding='utf-8',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        events = [json.loads(line[10:]) for line in result.stdout.splitlines() if line.startswith('APP_EVENT ')]
        self.assertTrue(any(e.get('id') == 'welfare' and e.get('status') == 'preview' for e in events))

    def test_unsupported_frontend_blocked_before_writes_or_launch(self):
        self.ui.select_all(False)
        self.ui.selection['welfare'].set(True)
        self.ui.backend.set('Midscene（前台）')
        with patch.object(app.messagebox, 'showerror') as error, patch.object(app.subprocess, 'Popen') as launch:
            self.ui.start()
        launch.assert_not_called()
        self.assertIn('福利大厅', error.call_args.args[1])
        self.assertFalse((self.folder/'run.json').exists())
        self.assertFalse((self.folder/'config.json').exists())




class WorkerIntegrationTests(unittest.TestCase):
    def run_worker(self, result='completed', error=None):
        with tempfile.TemporaryDirectory(prefix='welfare-worker-', dir=PROJECT/'verification') as folder:
            path = Path(folder)/'request.json'
            path.write_text(json.dumps({'tasks': ['welfare', 'hosting'], 'gameHwnd': 123}), encoding='utf-8')
            flow, window = Mock(), Mock()
            events = []
            def emit(kind, message, **extra):
                events.append(dict(kind=kind, message=message, **extra))
            with patch.object(sys, 'argv', ['native_worker.py', str(path)]), \
                 patch.object(native_worker, 'RunFailureTracker'), \
                 patch.object(native_worker, 'BackgroundWindow', return_value=window), \
                 patch.object(native_worker, 'LocalOCR'), \
                 patch.object(native_worker, 'LocalFlows', return_value=flow), \
                 patch.object(native_worker, 'checkpoint'), \
                 patch.object(native_worker, 'emit', side_effect=emit), \
                 patch.object(native_worker, 'run_welfare', return_value=result, side_effect=error) as welfare, \
                 patch.multiple(native_worker, tracker=None, window=None, flow=None):
                if error or result != 'completed':
                    with self.assertRaises(RuntimeError):
                        native_worker.main()
                    flow.run.assert_not_called()
                    self.assertFalse(any(e.get('id') == 'welfare' and e.get('status') == 'done' for e in events))
                else:
                    native_worker.main()
                    welfare.assert_called_once_with(flow)
                    flow.run.assert_called_once_with('hosting')
                    self.assertEqual([e['id'] for e in events if e.get('status') == 'done'], ['startup', 'welfare', 'hosting'])
                return events

    def test_completed_welfare_continues_queue(self):
        self.run_worker()

    def test_unknown_result_blocks_queue(self):
        self.run_worker(result='opened')

    def test_failed_welfare_blocks_queue(self):
        events = self.run_worker(error=RuntimeError('未知领奖结果'))
        self.assertTrue(any(e.get('id') == 'welfare' and e.get('status') == 'failed' for e in events))

    def test_bridge_preserves_latest_failure_frame_and_pause_time(self):
        flow = Mock()
        task = Mock(report={'status': 'stopped'}, last_image=object())
        def run():
            task.check()
            self.assertEqual(task.clock(), 20)
            raise RuntimeError('未确认反馈')
        def factory(window, ocr, folder, checkpoint, emit):
            task.check = checkpoint
            return task
        task.run.side_effect = run
        with patch.object(welfare_task, 'WelfareTask', side_effect=factory), \
             patch.object(welfare_task.time, 'monotonic', side_effect=[10, 40, 50]):
            with self.assertRaisesRegex(RuntimeError, '未确认反馈'):
                welfare_task.run_welfare(flow)
        flow.checkpoint.assert_called_once()
        self.assertIs(flow.image, task.last_image)
        self.assertEqual(flow.welfare_report['status'], 'stopped')


if __name__ == '__main__':
    unittest.main(verbosity=2)
