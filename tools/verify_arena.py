"""Offline arena daily verification, plus the affected window interface checks."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
import app


def main():
    protected=['app.py','native_worker.py','resources/tasks.json','adapters/local_ocr.py','adapters/background_window.py','local_flows.py',
               'ranked_pipeline.py','ranked_numbers.py','mission_desk_ui.py',
               'config.json','run.json','failure_archive.py','wanted_task.py','wanted_task_ui.py']
    before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in protected}
    outputs=[];reports=[]
    def run(label,names):
        stream=io.StringIO();start=time.monotonic()
        suite=unittest.defaultTestLoader.loadTestsFromNames(names)
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        outputs.append(label+'\n'+stream.getvalue())
        reports.append(dict(label=label,tests=result.testsRun,failures=len(result.failures),
                            errors=len(result.errors),skipped=len(result.skipped),seconds=round(time.monotonic()-start,3)))
        print(label,reports[-1],flush=True)
    run('arena entry, daily loop, hover and seven-task UI',[
        'tests_arena','tests_arena_daily','tests_arena_tokens','tests_arena_hover','tests_arena_ui'])
    run('affected common window checks only',[
        'tests_local.LocalTests.test_dpi_conversion',
        'tests_local.LocalTests.test_minimize_blocks_before_capture_or_input',
        'tests_local.LocalTests.test_startup_resizes_game_without_activation',
        'tests_local.LocalTests.test_startup_stops_if_game_refuses_resize'])
    after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in protected}
    from tests_arena import ArenaTests
    from tests_arena_daily import DailyVisionTests
    from tests_arena_tokens import TokenReaderTests
    session_baseline=json.loads((ROOT/'verification/arena-tokens-protected-20261019.json').read_text(encoding='utf-8'))
    session_same=all(after[p]==digest for p,digest in session_baseline.items())
    report=dict(scope='日常模式：实际战令段位优先，耗尽锁定休闲，60活动分钟上限',suites=reports,
                protectedFilesUnchanged=before==after,protectedSha256=after,gameInputs=0,
                sessionProtectedFilesUnchanged=session_same,
                liveVerified=False,liveDeferredByUser=True,route='home-icon',
                recognitionEvidence=ArenaTests.recognition_evidence,dailyEvidence=DailyVisionTests.evidence,
                tokenEvidence=TokenReaderTests.evidence,
                limitations=['战令0／1尚缺真实样图；只有模拟OCR与策略覆盖',
                             '降低难度确认弹窗与零任务终态尚缺实图','公共战斗皮肤验证不代表竞技场实机'],
                sourceFiles={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
                    'arena_task.py','arena_daily.py','arena_tokens.py','arena_task_ui.py','tests_arena.py','tests_arena_daily.py','tests_arena_tokens.py',
                    'tests_arena_hover.py','tests_arena_ui.py','app.py','adapters/background_window.py',
                    'native_worker.py','resources/tasks.json')})
    (ROOT/'verification/arena-tokens-tests-20261019.txt').write_text('\n'.join(outputs),encoding='utf-8')
    (ROOT/'verification/arena-tokens-20261019.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if before!=after or not session_same or any(r['errors'] or r['failures'] for r in reports):return 1
    return 0


if __name__=='__main__':sys.exit(main())
