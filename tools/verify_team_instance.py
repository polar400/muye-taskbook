"""Offline team-instance-only checks; never connects to a game window."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]

def main():
    protected = ['app.py','native_worker.py','local_flows.py','resources/tasks.json',
                 'adapters/local_ocr.py','adapters/background_window.py','config.json','run.json',
                 'mission_desk_ui.py','failure_archive.py','任务状态.md','技术文档.md']
    def hashes():
        return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in protected}
    before = hashes()
    stream = io.StringIO()
    start = time.monotonic()
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName('tests_team_instance'))
    after = hashes()
    report = dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                  skipped=len(result.skipped),seconds=round(time.monotonic()-start,3),
                  gameInputs=0,liveVerified=False,protectedUnchangedDuringTests=before==after,
                  protectedSha256=after,
                  limitations=['真实活动图为模板来源图，非独立留出样本',
                               '右侧组队副本标题正例由模拟OCR提供，缺少真实选中详情图',
                               '尚无副本目标界面样本，不返回opened或done',
                               '无可连接游戏窗口；未实测主页及切换限时活动',
                               '尚未接入共享任务清单和工作进程'])
    (ROOT/'verification/team-instance-entry-20261023.txt').write_text(stream.getvalue(),encoding='utf-8')
    (ROOT/'verification/team-instance-entry-20261023.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if result.wasSuccessful() and before==after else 1

if __name__=='__main__':
    sys.exit(main())
