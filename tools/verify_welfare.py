"""Run only welfare checks and record protected-file hashes; no game input."""
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
PROTECTED = ['app.py', 'local_flows.py', 'native_worker.py', 'adapters/background_window.py',
             'adapters/local_ocr.py', 'resources/tasks.json', 'config.json', 'run.json',
             '任务状态.md', '技术文档.md']
SOURCES = ['welfare_task.py', 'welfare_vision.py', 'welfare_tool.py', 'tests_welfare.py',
           'tools/prepare_welfare_assets.py', 'tools/verify_welfare.py', '启动福利大厅.cmd']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = {p: sha(ROOT / p) for p in PROTECTED}
    for name in SOURCES:
        if name.endswith('.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'))
    manifest = json.loads((ROOT/'resources/local/welfare/sources.json').read_text(encoding='utf-8'))
    asset_ok = all(sha(ROOT/'resources/local/welfare'/name) == entry['sha256'] for name, entry in manifest.items())
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName('tests_welfare'))
    after = {p: sha(ROOT / p) for p in PROTECTED}
    folder = ROOT/'verification'
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'seconds': round(time.monotonic()-started, 3), 'gameInputs': 0,
              'protectedUnchangedDuringVerification': before == after, 'protectedSha256': after,
              'sourceSha256': {p: sha(ROOT/p) for p in SOURCES}, 'assetProvenanceValid': asset_ok,
              'limitations': ['7份附件为模板来源；另有未用于制模板的实际主页及第二次运行反馈帧回归',
                              '当前勋章未激活，真实可领取的上中下忍礼包尚未验收；完整有奖励顺序另有模拟用例',
                              '实机结果以welfare运行目录report.json及帧序列单独记录']}
    (folder/'welfare-checks-20261027.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder/'welfare-checks-20261027.txt').write_text(stream.getvalue(), encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and before == after and asset_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
