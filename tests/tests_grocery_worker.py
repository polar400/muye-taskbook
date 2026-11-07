"""Explicit worker requests, isolated journals, and no native window/input calls."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
import sys
from unittest.mock import patch

import grocery_worker
from grocery_plan import load_catalog, load_state, new_state, save_state

ROOT = Path(__file__).resolve().parents[1]


class OpenInput:
    def __init__(self): self.closed = threading.Event()
    def __iter__(self):
        self.closed.wait(10)
        return iter(())


class GroceryWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='grocery-worker-', dir=ROOT/'verification')
        self.root = Path(self.temp.name)
        self.stdin = OpenInput()
        self.request = {'schema_version': 1, 'hwnd': 123, 'mode': 'observe',
                        'evidence_dir': str(self.root/'evidence'), 'balance_path': str(self.root/'grocery_balances.json')}

    def tearDown(self):
        self.stdin.closed.set()
        self.temp.cleanup()

    def run_request(self, driver, capability=False):
        path = self.root/'request.json'
        path.write_text(json.dumps(self.request), encoding='utf-8')
        with patch.object(grocery_worker, 'init_dpi'), patch.object(grocery_worker.sys, 'stdin', self.stdin), \
             patch.object(grocery_worker.sys, 'stdout', io.StringIO()), \
             patch('grocery_driver.GroceryDriver', return_value=driver) as factory, \
             patch('grocery_driver.capability_summary', return_value={'live_purchase_supported': capability, 'reason': 'unvalidated'}):
            result = grocery_worker.main(path)
        return result, factory

    def test_balance_request_only_reads_and_persists_real_driver_values(self):
        class ReadOnly:
            def begin(self): return {'sun': 10, 'moon': 20, 'sign': 30, 'mystery': 40}
            def inspect(self, item): raise AssertionError('No purchase inspection in observe mode')
            def purchase(self, *args): raise AssertionError('No purchase in observe mode')
        result, factory = self.run_request(ReadOnly())
        self.assertEqual(result, 0)
        self.assertEqual(factory.call_count, 1)
        record = json.loads((self.root/'grocery_balances.json').read_text(encoding='utf-8'))
        self.assertEqual(record['balances'], {'sun': 10, 'moon': 20, 'sign': 30, 'mystery': 40})
        self.assertFalse((self.root/'grocery_state.json').exists())

    def test_purchase_capability_is_checked_before_constructing_native_driver(self):
        self.request['mode'] = 'purchase'
        with self.assertRaisesRegex(ValueError, 'unvalidated'):
            self.run_request(object())
        self.assertFalse((self.root/'evidence').exists())
        self.assertFalse((self.root/'grocery_state.json').exists())

    def test_fresh_worker_imports_native_module_before_blocking_stdin_reader(self):
        # A fresh interpreter is essential: the normal test process already has
        # NumPy loaded. Keep stdin open, exactly as the GUI does.
        (self.root/'grocery_driver.py').write_text(
            "import numpy\nclass GroceryDriver:\n"
            " def __init__(self,*args,**kwargs): pass\n"
            " def begin(self): return dict(sun=10,moon=20,sign=30,mystery=40)\n", encoding='utf-8')
        request_path = self.root/'request.json'
        request_path.write_text(json.dumps(self.request), encoding='utf-8')
        code = (f"import sys; sys.path.insert(0,{str(self.root)!r}); "
                f"sys.path.insert(1,{str(ROOT/'vendor')!r}); "
                f"sys.path.insert(2,{str(ROOT/'src')!r}); import grocery_worker; grocery_worker.main({str(request_path)!r})")
        process = subprocess.Popen([sys.executable, '-u', '-c', code], cwd=ROOT,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=12)
            self.assertEqual(process.returncode, 0, process.stderr.read())
            record = json.loads((self.root/'grocery_balances.json').read_text(encoding='utf-8'))
            self.assertEqual(record['balances']['moon'], 20)
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            for stream in (process.stdin, process.stdout, process.stderr): stream.close()

    def test_validated_purchase_request_uses_fixed_journal_and_archives_result(self):
        catalog = load_catalog()
        state = new_state(catalog, {catalog[0]['key']: 2})
        state_path = self.root/'grocery_state.json'
        save_state(state_path, state)
        self.request.update(mode='purchase', run_id=state['run_id'], state_path=str(state_path))
        test = self
        class Driver:
            def begin(self): return {'sun': 200, 'moon': 20, 'sign': 30, 'mystery': 40}
            def inspect(self, item):
                return {'verified': True, 'unit_price': 50, 'stock': 50, 'balances': self.begin()}
            def purchase(self, item, quantity, inspection):
                test.assertEqual(load_state(state_path)['items'][0]['status'], 'uncertain')
                test.assertEqual(quantity, 2)
                return {'verified': True, 'quantity': 2, 'stock': 48,
                        'balances': {'sun': 100, 'moon': 20, 'sign': 30, 'mystery': 40}}
        result, _ = self.run_request(Driver(), capability=True)
        self.assertEqual(result, 0)
        balance_record = json.loads((self.root/'grocery_balances.json').read_text(encoding='utf-8'))
        self.assertEqual(balance_record['balances'], load_state(state_path)['balances_latest'])
        final = load_state(state_path)
        self.assertEqual(final['status'], 'done')
        self.assertEqual(final['items'][0]['completed'], 2)
        self.assertEqual(load_state(self.root/'evidence/state-final.json')['run_id'], state['run_id'])


if __name__ == '__main__': unittest.main()
