"""Offline audit of the reported lower-difficulty timeout; sends no game input."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def main():
    protected=('app.py','native_worker.py','resources/tasks.json','adapters/local_ocr.py',
               'adapters/background_window.py','local_flows.py','ranked_pipeline.py',
               'ranked_numbers.py','mission_desk_ui.py','config.json','run.json',
               'failure_archive.py','wanted_task.py','wanted_task_ui.py',
               'arena_task.py','arena_daily.py','arena_tokens.py','arena_task_ui.py')
    before={p:digest(p) for p in protected}
    names=['tests_arena','tests_arena_daily','tests_arena_tokens','tests_arena_hover','tests_arena_ui']
    stream=io.StringIO();start=time.monotonic()
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    from tests_arena_daily import DailyVisionTests
    evidence=DailyVisionTests.evidence
    sources=['verification/'+f+'/'+n for f in (
        'arena-daily-20261019-232750-23f34458','arena-daily-20261019-232831-3ebeea34')
        for n in ('report.json','last.png')]
    after={p:digest(p) for p in protected}
    report=dict(scope='降低难度失败离线排查；未修复或实机验证后台悬停',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        skipped=len(result.skipped),seconds=round(time.monotonic()-start,3),
        gameInputs=0,runtimeChanged=False,liveVerified=False,liveDeferredByUser=True,
        protectedFilesUnchanged=before==after,protectedSha256=after,
        evidenceSha256={p:digest(p) for p in sources},dailyEvidence=evidence,
        findings=['两次实际运行均进入竞技场并读取2战令、4任务，两项未满足',
                  '第一项悬停点271,506位于未满足文字内；消息返回不等于游戏响应',
                  '两张最后原图均无降低按钮，未满足匹配分数1.0及0.99967',
                  '第一次窗口几何变化；第二次等待降低按钮超时，均未发送降级或匹配'],
        limitations=['只有最后画面，不能排除中途短暂出现按钮；无逐帧悬停证据',
                     '后台消息、游戏悬停响应或瞬态识别的具体原因需实机区分',
                     '原组合图仅验证模板与解析，模拟悬停不证明真实游戏响应'])
    prefix=ROOT/'verification/arena-lower-hover-audit-20261019'
    prefix.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    prefix.with_suffix('.txt').write_text(stream.getvalue(),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('tests','failures','errors','skipped','seconds',
          'gameInputs','runtimeChanged','protectedFilesUnchanged')},ensure_ascii=True),flush=True)
    return 0 if result.wasSuccessful() and before==after else 1


if __name__=='__main__':sys.exit(main())
