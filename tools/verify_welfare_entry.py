"""Welfare scan repair and existing-UI reentry checks; zero live game inputs."""
import ast
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
FOLDER = ROOT/'verification/welfare-reentry-20261027'
SOURCES = ('welfare_vision.py', 'welfare_task.py', 'welfare_task_ui.py', 'app.py', 'native_worker.py',
           'resources/tasks.json', 'tests_welfare_entry.py', 'tests_welfare_ui.py',
           'tools/prepare_welfare_assets.py', 'tools/verify_welfare_entry.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((FOLDER/'protected-before.json').read_text(encoding='utf-8'))
    before = {name: sha(ROOT/name) for name in baseline}
    for name in SOURCES:
        if name.endswith('.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'))
    manifest = json.loads((ROOT/'resources/local/welfare/sources.json').read_text(encoding='utf-8'))
    assets_ok = all(sha(ROOT/'resources/local/welfare'/name) == item['sha256'] for name, item in manifest.items())
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(['tests_welfare_entry', 'tests_welfare', 'tests_welfare_ui']))
    from tests_welfare_entry import RUNS, frame
    from adapters.local_ocr import LocalOCR
    from welfare_vision import WelfareVision
    vision = WelfareVision(LocalOCR())
    holdouts = []
    for run in RUNS:
        for name in ('001.png', '002.png'):
            matches = vision.matches(frame(run, name), 'entry')
            holdouts.append({'path': f'verification/{run}/{name}', 'sha256': sha(ROOT/'verification'/run/name),
                             'matches': matches})
    after = {name: sha(ROOT/name) for name in baseline}
    no_redraw = not (ROOT/'ui_redraw.py').exists() and 'window_paint' not in (ROOT/'src/app.py').read_text(encoding='utf-8')
    no_queue_change = 'task_queue_canvas' not in (ROOT/'src/mission_desk_ui.py').read_text(encoding='utf-8')
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'seconds': round(time.monotonic()-started, 3), 'gameInputs': 0, 'liveVerified': False,
              'protectedMatchStageStart': baseline == before == after, 'protectedSha256': after,
              'sourceSha256': {name: sha(ROOT/name) for name in SOURCES}, 'assetProvenanceValid': assets_ok,
              'holdoutFrames': holdouts, 'entryTemplateSource': 'resources/local/welfare/reference-1.png',
              'entryThreshold': .92, 'entryPairTolerancePixels': 3,
              'redrawStillWithdrawn': no_redraw, 'queueLayoutUnchanged': no_queue_change,
              'limitations': ['本轮仅离线原图、模拟点击和Tk界面验证，未操作真实游戏',
                              '入口模板只取原附件，12张失败帧均为独立留出验证',
                              '真实未激活勋章领取、在线未满等原限制保留',
                              '保留原队列布局；最小窗口裁切及显示性能不在本轮修复范围']}
    (FOLDER/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (FOLDER/'tests.txt').write_text(stream.getvalue(), encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps({key: value for key, value in report.items() if key not in ('holdoutFrames', 'sourceSha256', 'protectedSha256')}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and baseline == before == after and assets_ok and no_redraw and no_queue_change else 1


if __name__ == '__main__':
    raise SystemExit(main())
