"""Offline grocery integration evidence, with the pre-change UI baseline retained."""
from __future__ import annotations
import ast
import difflib
import hashlib
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grocery_plan import now
from grocery_driver import capability_summary
from PIL import Image

OUT = ROOT/'verification/grocery-tool-20261026'
GROCERY_TESTS = ('tests_grocery_recognition', 'tests_grocery_plan', 'tests_grocery_controller',
                 'tests_grocery_worker', 'tests_grocery_tool_ui', 'tests_grocery_vision')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite(names, filename):
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (OUT/filename).write_text(stream.getvalue(), encoding='utf-8')
    return {'run': result.testsRun, 'successful': result.wasSuccessful(), 'skipped': len(result.skipped),
            'failures': [{'test': str(test), 'traceback': detail} for test, detail in result.failures],
            'errors': [{'test': str(test), 'traceback': detail} for test, detail in result.errors]}


def masked_ast(source, allowed):
    tree = ast.parse(source)
    class Mask(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name in allowed:
                node.body = [ast.Pass()]
            return self.generic_visit(node)
    return ast.dump(Mask().visit(tree), include_attributes=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'verified_at': now(), 'errors': [], 'shared': [], 'sourceIntegrity': [], 'runtimeIntegrity': [],
              'capability': capability_summary(), 'actualGameInput': False}
    baseline = json.loads((OUT/'shared-baseline.json').read_text(encoding='utf-8-sig'))
    approved = {'app.py': ('app-before.py', {'start', 'close', 'close_when_stopped'}),
                'mission_desk_ui.py': ('mission-desk-before.py', {'build'})}
    for record in baseline:
        path = ROOT/record['path']
        current = sha(path)
        item = {**record, 'current_sha256': current, 'unchanged': current == record['sha256']}
        if record['path'] in approved:
            backup, functions = approved[record['path']]
            before = (OUT/backup).read_text(encoding='utf-8')
            after = path.read_text(encoding='utf-8')
            allowed = masked_ast(before, functions) == masked_ast(after, functions)
            item.update(approved_functions=sorted(functions), outside_approved_functions_unchanged=allowed)
            if not allowed: report['errors'].append('Shared code changed outside approval: '+record['path'])
            difference = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                               fromfile=record['path']+' (before)', tofile=record['path']+' (after)'))
            (OUT/(path.stem+'-integration.patch')).write_text(difference, encoding='utf-8')
        elif not item['unchanged']:
            report['errors'].append('Protected shared file changed: '+record['path'])
        report['shared'].append(item)
    asset_root = ROOT/'resources/local/grocery'
    manifest = json.loads((asset_root/'manifest.json').read_text(encoding='utf-8'))
    for key, asset in manifest['assets'].items():
        good = sha(asset_root/asset['path']) == asset['sha256']
        report['sourceIntegrity'].append({'key': key, 'unchanged': good})
        if not good: report['errors'].append('Original icon changed: '+key)
    runtime = json.loads((asset_root/'runtime-sources.json').read_text(encoding='utf-8'))
    for asset in runtime['assets']:
        path = asset_root/asset['path']
        x,y,w,h = asset['source_box']
        with Image.open(asset_root/asset['source']) as source, Image.open(path) as template:
            original = source.convert('RGBA').crop((x,y,x+w,y+h))
            actual = template.convert('RGBA')
            good = (sha(path) == asset['sha256'] and actual.size == (w,h)
                    and hashlib.sha256(actual.tobytes()).hexdigest() == asset['pixel_sha256']
                    and original.tobytes() == actual.tobytes())
        report['runtimeIntegrity'].append({'key': asset['key'], 'original_pixels': good})
        if not good: report['errors'].append('Runtime source pixels differ: '+asset['key'])
    code_files = ('grocery_recognition.py','grocery_plan.py','grocery_controller.py','grocery_worker.py',
                  'grocery_driver.py','grocery_vision.py','grocery_tool_ui.py',
                  'tests_grocery_recognition.py','tests_grocery_plan.py','tests_grocery_controller.py',
                  'tests_grocery_worker.py','tests_grocery_vision.py','tests_grocery_tool_ui.py')
    for name in code_files: ast.parse((ROOT/name).read_text(encoding='utf-8'))
    report['syntax_files'] = list(code_files)
    report['groceryTests'] = run_suite(GROCERY_TESTS, 'grocery-tests.txt')
    report['sharedUiTests'] = run_suite(('tests_mission_desk_ui',), 'shared-ui-tests.txt')

    # Reproduce existing failure against the exact backed-up App and old build.
    import app, mission_desk_ui
    old_app = types.ModuleType('grocery_baseline_app')
    old_app.__file__ = str(ROOT/'app.py')
    sys.modules[old_app.__name__] = old_app
    exec(compile((OUT/'app-before.py').read_text(encoding='utf-8'), old_app.__file__, 'exec'), old_app.__dict__)
    old_ui = types.ModuleType('grocery_baseline_mission')
    old_ui.__file__ = str(ROOT/'mission_desk_ui.py')
    exec(compile((OUT/'mission-desk-before.py').read_text(encoding='utf-8'), old_ui.__file__, 'exec'), old_ui.__dict__)
    def baseline_app():
        old_app.ROOT = app.ROOT  # The original test patches this to temporary storage.
        return old_app.App()
    with patch.object(app, 'App', side_effect=baseline_app), patch.object(mission_desk_ui, 'build', old_ui.build):
        report['sharedUiBeforeChanges'] = run_suite(('tests_mission_desk_ui',), 'shared-ui-baseline-tests.txt')
    old_failures = {item['test'] for item in report['sharedUiBeforeChanges']['failures']}
    current_failures = {item['test'] for item in report['sharedUiTests']['failures']}
    report['knownSharedUiFailures'] = sorted(current_failures & old_failures)
    unexpected = current_failures-old_failures
    if unexpected or report['sharedUiTests']['errors']:
        report['errors'].append('New shared UI regression detected')
    report['sharedUiLimitation'] = ('Existing test expects 6 daily tasks but the current task catalogue contains 8; '
                                   'same failure reproduced against backed-up App and UI. The test was not edited.')
    report['liveEvidence'] = json.loads((OUT/'live-initial.json').read_text(encoding='utf-8'))
    report['limitations'] = [
        'Automatic live purchase remains disabled; quantity editing, confirmations and transaction-result evidence are pending.',
        'Actual screenshot at verification time showed village home, not grocery; no game inputs or purchases were sent.',
        'Four balances and 12 visible sun-store cards were verified using the supplied grocery screenshot.',
        'Simulated purchase/continue tests are not real-game purchase acceptance.',
        'Shared UI suite retains its independently reproduced pre-existing 6-versus-8 task count failure.'
    ]
    report['focusedPassed'] = report['groceryTests']['successful'] and not report['errors']
    report['allSuitesPassed'] = report['focusedPassed'] and report['sharedUiTests']['successful']
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'focusedPassed':report['focusedPassed'], 'allSuitesPassed':report['allSuitesPassed'],
                      'groceryTests':report['groceryTests']['run'],
                      'groceryFailures':len(report['groceryTests']['failures']),
                      'groceryErrors':len(report['groceryTests']['errors']),
                      'originalIcons':len(report['sourceIntegrity']), 'runtimeReferences':len(report['runtimeIntegrity']),
                      'knownSharedUiFailures':len(report['knownSharedUiFailures']),
                      'livePurchaseEnabled':report['capability']['live_purchase_supported'], 'errors':report['errors']}, ensure_ascii=False))
    return 0 if report['focusedPassed'] else 1


if __name__ == '__main__': raise SystemExit(main())
