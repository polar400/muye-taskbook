"""Grocery lifecycle integration checks using fake processes and windows only."""
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
from grocery_controller import GroceryController
from grocery_plan import load_catalog, new_state, save_state, load_state

ROOT = Path(__file__).resolve().parent


class Value:
    def __init__(self, value): self.value = value
    def get(self): return self.value


class UI:
    def __init__(self):
        self.running = False
        self.backend = Value('本地后台（免API）')
        self.window_choice = Value('game  [123]')
        self.destroyed = False
        self.jobs = []
    def after(self, delay, callback): self.jobs.append(callback); return len(self.jobs)
    def after_cancel(self, timer): pass
    def destroy(self): self.destroyed = True


class View:
    def __init__(self, quantities):
        self.values = quantities
        self.running = False
        self.message = ''
    def validated_quantities(self): return dict(self.values)
    def set_running(self, value): self.running = value
    def set_pending_state(self, value): self.pending = value
    def show_status(self, message): self.message = message
    def show_balance(self, values, at): self.balances = values
    def show_progress(self, event): self.progress = event


class Process:
    def __init__(self): self.stdin = io.StringIO(); self.stdout = io.StringIO()
    def wait(self, timeout=None): return 0
    def terminate(self): pass
    def kill(self): pass


class GroceryControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='grocery-controller-', dir=ROOT/'verification')
        self.root = Path(self.temp.name)
        self.catalog = load_catalog()
        self.values = {item['key']: 0 for item in self.catalog}
        self.values[self.catalog[0]['key']] = 2
        self.ui, self.view = UI(), View(self.values)
        self.spawned = []
        def spawn(args, **kwargs): self.spawned.append((args, kwargs)); return Process()
        self.controller = GroceryController(self.ui, self.view, root=self.root, popen=spawn,
                                             window_provider=lambda: [(123, 'game')],
                                             capability={'live_purchase_supported': True})

    def tearDown(self):
        self.controller.dispose()
        self.temp.cleanup()

    def test_production_supported_items_gate_runs_before_journal_and_spawn(self):
        self.controller.supported_item_ids=['10800057','10840089']
        self.assertFalse(self.controller.start())
        self.assertIn('尚未接入',self.view.message)
        self.assertFalse(self.spawned)
        self.assertFalse((self.root/'grocery_state.json').exists())

    def test_daily_task_blocks_grocery_without_spawning_or_state(self):
        self.ui.running = True
        self.assertFalse(self.controller.start())
        self.assertFalse(self.spawned)
        self.assertFalse((self.root/'grocery_state.json').exists())

    def test_failed_observation_exit_unlocks_and_shows_failure(self):
        process = Process()
        self.controller.process = process
        self.controller.running = True
        self.controller._request_mode = 'observe'
        self.view.set_running(True)
        self.controller._events.put({'kind': 'exit', 'code': 7, '_process': process})
        self.controller._drain()
        self.assertFalse(self.controller.running)
        self.assertFalse(self.view.running)
        self.assertIn('代码7', self.view.message)

    def test_observation_timeout_stops_only_own_worker_and_unlocks_on_exit(self):
        process = Process()
        self.controller.process = process
        self.controller.running = True
        self.controller._request_mode = 'observe'
        self.controller._observe_started = 10
        with patch('grocery_controller.time.monotonic', return_value=56):
            self.controller._drain()
        self.assertTrue(self.controller.stopping)
        self.assertEqual(process.stdin.getvalue(), 'stop\n')
        self.controller._events.put({'kind': 'exit', 'code': 1, '_process': process})
        self.controller._drain()
        self.assertFalse(self.controller.running)
        self.assertFalse(self.view.running)
        self.assertIn('超时', self.view.message)
        self.assertFalse((self.root/'grocery_balances.json').exists())

    def test_resume_keeps_original_plan_even_when_fields_changed(self):
        state = new_state(self.catalog, self.values)
        state['status'] = 'stopped'
        save_state(self.root/'grocery_state.json', state)
        self.view.values[self.catalog[0]['key']] = 9
        self.assertTrue(self.controller.start())
        current = load_state(self.root/'grocery_state.json')
        self.assertEqual(current['run_id'], state['run_id'])
        self.assertEqual(current['items'][0]['quantity'], 2)
        self.assertEqual(len(self.spawned), 1)
        self.assertIn('grocery_worker.py', self.spawned[0][0][2])
        self.assertFalse((self.root/'config.json').exists())
        self.assertFalse((self.root/'run.json').exists())

    def test_unknown_previous_transaction_cannot_resume(self):
        state = new_state(self.catalog, self.values)
        state['items'][0]['status'] = 'uncertain'
        state['status'] = 'needs_review'
        save_state(self.root/'grocery_state.json', state)
        self.assertFalse(self.controller.start())
        self.assertFalse(self.spawned)
        self.assertEqual(load_state(self.root/'grocery_state.json')['items'][0]['status'], 'uncertain')

    def test_completed_round_never_implicitly_rebuys(self):
        state = new_state(self.catalog, self.values)
        state['items'][0].update(status='done', completed=2)
        state['status'] = 'done'
        save_state(self.root/'grocery_state.json', state)
        self.assertFalse(self.controller.start())
        self.assertFalse(self.spawned)

    def test_explicit_new_round_archives_previous_and_asks_once(self):
        state = new_state(self.catalog, self.values)
        state['items'][0].update(status='done', completed=2)
        state['status'] = 'done'
        save_state(self.root/'grocery_state.json', state)
        with patch('grocery_controller.messagebox.askyesno', return_value=True) as confirm:
            self.assertTrue(self.controller.start(new_round=True))
        confirm.assert_called_once()
        current = load_state(self.root/'grocery_state.json')
        self.assertNotEqual(current['run_id'], state['run_id'])
        self.assertEqual(current['items'][0]['completed'], 0)
        self.assertTrue((self.root/'verification/grocery-runs'/state['run_id']/'state-archived.json').exists())

    def test_missing_window_refuses_before_journal_or_process(self):
        self.controller._window_provider = lambda: []
        self.assertFalse(self.controller.start())
        self.assertFalse(self.spawned)
        self.assertFalse((self.root/'grocery_state.json').exists())

    def test_unvalidated_purchase_is_blocked_but_balance_mode_has_no_purchase_journal(self):
        self.controller.purchase_available = False
        self.assertFalse(self.controller.start())
        self.assertFalse(self.spawned)
        self.assertTrue(self.controller.observe())
        self.assertFalse((self.root/'grocery_state.json').exists())
        import json
        request = json.loads(Path(self.spawned[0][0][-1]).read_text(encoding='utf-8'))
        self.assertEqual(request['mode'], 'observe')
        self.assertNotIn('state_path', request)

    def test_stop_sends_only_stop_to_own_process(self):
        self.assertTrue(self.controller.start())
        process = self.controller.process
        self.controller.stop()
        self.assertEqual(process.stdin.getvalue(), 'stop\n')
        self.controller.stop()
        self.assertEqual(process.stdin.getvalue(), 'stop\n')

    def test_grocery_blocks_daily_task_and_diagnostic_before_config(self):
        self.ui.grocery_tool = self.controller
        self.controller.running = True
        with patch('app.messagebox.showwarning') as warning:
            app.App.start(self.ui)
            app.App.start(self.ui, diagnostic=True)
        self.assertEqual(warning.call_count, 2)
        self.assertFalse(self.spawned)
        self.controller.running = False

    def test_app_close_waits_for_grocery_then_disposes(self):
        class Tool:
            running = True
            closed = False
            disposed = False
            def close(tool): tool.closed = True
            def dispose(tool): tool.disposed = True
        tool = Tool()
        self.ui.grocery_tool = tool
        self.ui.close_when_stopped = lambda: app.App.close_when_stopped(self.ui)
        app.App.close(self.ui)
        self.assertTrue(tool.closed)
        self.assertFalse(self.ui.destroyed)
        tool.running = False
        app.App.close_when_stopped(self.ui)
        self.assertTrue(tool.disposed)
        self.assertTrue(self.ui.destroyed)


if __name__ == '__main__': unittest.main()
