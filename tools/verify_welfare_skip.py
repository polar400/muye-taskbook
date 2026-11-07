"""Verify non-claim skipping without changing any shared service or live game state."""
import ast
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT/'verification/welfare-skip-nonclaim-20261027'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((FOLDER/'protected-before.json').read_text(encoding='utf-8'))
    before = {name: sha(ROOT/name) for name in baseline}
    sources = ('welfare_vision.py', 'welfare_task.py', 'welfare_task_ui.py', 'tests_welfare.py',
               'tests_welfare_skip.py', 'tools/verify_welfare_skip.py')
    for name in sources:
        ast.parse((ROOT/name).read_text(encoding='utf-8'))
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames([
            'tests_welfare_skip', 'tests_welfare', 'tests_welfare_entry', 'tests_welfare_ui']))
    after = {name: sha(ROOT/name) for name in baseline}
    from tests_welfare_skip import RUNS
    evidence = []
    for run in RUNS:
        path = sorted((ROOT/'verification'/run).glob('*.png'))[-1]
        evidence.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path)})
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'seconds': round(time.monotonic()-started, 3), 'gameInputs': 0, 'liveVerified': False,
              'protectedUnchanged': baseline == before == after, 'protectedSha256': after,
              'sourceSha256': {name: sha(ROOT/name) for name in sources},
              'rechargeEvidence': evidence, 'policy': '已确认福利页面，只有原色领取模板才点击，其他按钮全部跳过',
              'receiptPolicy': '点击后仅有明确已领取模板才登记claimed_confirmed，否则仅claim_sent',
              'limitations': ['本轮未操作游戏，真实接续由用户实测',
                              '按钮歧义、界面无法确认、点击后仍为领取按钮未变化时仍停止且不重发',
                              '其他任务付费提示、公共识别／输入／UI布局／日志及配置未改']}
    (FOLDER/'tests.txt').write_text(stream.getvalue(), encoding='utf-8')
    (FOLDER/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps({key: value for key, value in report.items() if key not in ('protectedSha256', 'sourceSha256')}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and baseline == before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
