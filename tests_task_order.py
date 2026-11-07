"""Task sorting integration checks using Tk events; no game operations."""
import json
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import app


class TaskOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=app.ROOT/'verification')
        self.root = Path(self.temp.name)
        self.patches = [patch.object(app, 'ROOT', self.root), patch.object(app, 'game_windows', return_value=[])]
        for item in self.patches:item.start()
        self.ui = app.App()
        self.ui.update()

    def tearDown(self):
        for timer in self.ui.tk.call('after', 'info'):self.ui.after_cancel(timer)
        self.ui.destroy()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def drag(self, key, y):
        handle = self.ui.task_handles[key]
        handle.event_generate('<ButtonPress-1>', x=10, y=14)
        handle.event_generate('<B1-Motion>', x=10, y=y)
        self.ui.update()
        handle.event_generate('<ButtonRelease-1>', x=10, y=y)
        self.ui.update()

    def test_drag_both_directions_keeps_settings_and_execution_order(self):
        ui = self.ui
        original = list(ui.task_order)
        ui.selection['strong'].set(False)
        ui.difficulty.set('天级')
        ui.show_task('escort')
        self.drag('escort', -500)
        self.assertEqual(ui.task_order, ['escort']+original[:-1])
        self.assertEqual(ui.config()['tasks'], [key for key in ui.task_order if key!='strong'])
        self.assertEqual(ui.selected.get(), 'escort')
        self.assertEqual(ui.difficulty.get(), '天级')
        self.assertFalse(ui.selection['strong'].get())
        self.assertEqual(list(ui.task_list.pack_slaves()), [ui.task_rows[key] for key in ui.task_order])
        self.drag('escort', 1000)
        self.assertEqual(ui.task_order, original)
        self.assertIsNone(ui.task_drag)
        self.assertEqual(ui.task_drop_line.winfo_manager(), '')
        self.assertIsNone(ui.grab_current())

    def test_small_click_and_escape_do_not_reorder(self):
        ui = self.ui
        original = list(ui.task_order)
        self.drag('survival', 16)
        self.assertEqual(ui.task_order, original)
        handle = ui.task_handles['survival']
        handle.event_generate('<ButtonPress-1>', x=10, y=14)
        handle.event_generate('<B1-Motion>', x=10, y=1000)
        self.assertTrue(ui.task_drag['moved'])
        ui.cancel_task_drag()
        handle.event_generate('<ButtonRelease-1>', x=10, y=1000)
        self.assertEqual(ui.task_order, original)
        self.assertIsNone(ui.grab_current())

    def test_persistence_preserves_saved_settings_and_unchecked_positions(self):
        ui = self.ui
        path = self.root/'config.json'
        path.write_text(json.dumps({'tasks':['hosting'], 'difficulty':'夜叉级', 'custom':42}), encoding='utf-8')
        ui.difficulty.set('天级')
        ui.move_task('escort', -1)
        saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(saved['difficulty'], '夜叉级')
        self.assertEqual(saved['custom'], 42)
        order = list(ui.task_order)
        ui.task_order.reverse()
        ui.load()
        self.assertEqual(ui.task_order, order)
        self.assertEqual(ui.config()['tasks'], ['hosting'])
        ui.save()
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['taskOrder'], order)

    def test_old_and_stale_config_orders(self):
        path = self.root/'config.json'
        path.write_text(json.dumps({'tasks':['hosting','strong']}), encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order[:2], ['hosting','strong'])
        path.write_text(json.dumps({'taskOrder':['escort','escort','missing',None,{}]}), encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order[0], 'escort')
        self.assertEqual(set(self.ui.task_order), set(dict(app.TASKS)))
        self.assertEqual(len(self.ui.task_order), len(app.TASKS))

    def test_running_lock_and_boundary_moves(self):
        ui = self.ui
        original = list(ui.task_order)
        ui.move_task(original[0], -1)
        ui.move_task(original[-1], 1)
        self.assertEqual(ui.task_order, original)
        ui.running = True
        ui.update_task_order_controls()
        self.drag('escort', -500)
        ui.move_task('escort', -1)
        self.assertEqual(ui.task_order, original)
        self.assertEqual(ui.task_handles['escort'].cget('cursor'), 'arrow')
        ui.running = False
        ui.move_task('escort', -1)
        self.assertNotEqual(ui.task_order, original)

    def test_minimum_window_layout(self):
        ui = self.ui
        ui.geometry('940x680')
        ui.update()
        for key, row in ui.task_rows.items():
            self.assertGreater(row.winfo_width(), 0)
            check = next(widget for widget in row.winfo_children() if widget.winfo_class()=='TCheckbutton')
            self.assertGreaterEqual(check.winfo_width(), check.winfo_reqwidth())
            self.assertLessEqual(check.winfo_x()+check.winfo_width(), ui.gears[key].winfo_x())
        self.assertLess(ui.preview_button.winfo_rooty()+ui.preview_button.winfo_height(), ui.winfo_rooty()+ui.winfo_height())

    def test_both_worker_previews_follow_sorted_checked_tasks(self):
        ui = self.ui
        ui.move_task('hosting', -1)
        ui.selection['survival'].set(False)
        ui.selection['ranked'].set(False)
        ui.preview.set(True)
        cfg = ui.config()
        path = self.root/'preview.json'
        path.write_text(json.dumps(cfg), encoding='utf-8')
        project = Path(app.__file__).resolve().parent
        commands = [[sys.executable, str(project/'native_worker.py'), str(path)],
                    [shutil.which('node'), str(project/'worker.mjs'), str(path)]]
        for command in commands:
            with self.subTest(worker=command[1]):
                result = subprocess.run(command, cwd=project, capture_output=True, text=True,
                                        encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=30,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                events = [json.loads(line[10:]) for line in result.stdout.splitlines() if line.startswith('APP_EVENT ')]
                ids = [event['id'] for event in events if event['kind']=='task' and event.get('status')=='preview' and event['id']!='startup']
                self.assertEqual(ids, cfg['tasks'])


if __name__=='__main__':unittest.main()
