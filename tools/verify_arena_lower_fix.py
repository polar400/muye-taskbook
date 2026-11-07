"""Arena-only regression for highlighted lower buttons and the reviewed input proposal."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]


def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cursor-proposal-applied',action='store_true')
    args=parser.parse_args()
    baseline=json.loads((ROOT/'verification/arena-lower-fix-protected-20261020.json').read_text(encoding='utf-8'))
    before={p:digest(p) for p in baseline}
    proposal=json.loads((ROOT/'verification/arena-cursor-hover-proposal-20261020.json').read_text(encoding='utf-8'))
    if args.cursor_proposal_applied and proposal.get('decision')!='allowed_by_user':
        raise RuntimeError('用户拒绝真实鼠标方案，不接受已应用该提案的验证模式')
    allowed={'adapters/background_window.py'} if args.cursor_proposal_applied else set()
    session_same=all(before[p]==sha for p,sha in baseline.items() if p not in allowed)
    if args.cursor_proposal_applied:
        actual=(ROOT/'src/adapters/background_window.py').read_text(encoding='utf-8')
        session_same=session_same and hashlib.sha256(actual.encode()).hexdigest()==proposal['proposedTextSha256']
    stream=io.StringIO();start=time.monotonic()
    names=['tests_arena','tests_arena_daily','tests_arena_tokens','tests_arena_hover','tests_arena_ui',
           'tests_arena_cursor_proposal','tests_arena_virtual_pointer','tests_arena_lower_probe']
    if args.cursor_proposal_applied:
        names.extend(['tests_local.LocalTests.test_dpi_conversion',
                      'tests_local.LocalTests.test_minimize_blocks_before_capture_or_input',
                      'tests_local.LocalTests.test_startup_resizes_game_without_activation',
                      'tests_local.LocalTests.test_startup_stops_if_game_refuses_resize'])
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    from tests_arena_daily import DailyVisionTests
    live_path='verification/arena-virtual-pointer-20261020-010655-494114/report.json'
    live=json.loads((ROOT/live_path).read_text(encoding='utf-8'))
    from arena_daily import board_key
    live_evidence=dict(report=live_path,reportSha256=digest(live_path),
        buttonClicks=live['buttonClicks'],moveMessages=live['moveMessages'],
        importPointersRestored=live['importPointersRestored'],
        cursorUnchanged=live['cursorBefore']==live['cursorAfter'],
        foregroundUnchanged=live['foregroundBefore']==live['foregroundAfter'],
        lowerCounts=[len(f['lower']) for f in live['frames']],
        taskIdentityUnchanged=all(f['board'] and board_key(f['board'])==board_key(live['boardBefore']) for f in live['frames']),
        actualLowerOrConfirmExecuted=False)
    lower_path='verification/arena-lower-virtual-20261020-011916-475721/report.json'
    lower=json.loads((ROOT/lower_path).read_text(encoding='utf-8'))
    lower_evidence=dict(report=lower_path,reportSha256=digest(lower_path),result=lower['result'],
        inputAttempts=lower['inputAttempts'],error=lower['error'],
        contextsUsed=len(lower['phases']),retainedBytes=sum(p['shim']['retainedBytes'] for p in lower['phases']),
        importPointersRestored=all(p['restored'] for p in lower['phases']),
        cursorUnchanged=lower['cursorUnchanged'],foregroundUnchanged=lower['foregroundUnchanged'],
        actualLowerOrConfirmExecuted=False,
        offlineReplay='verification/arena-lower-virtual-offline-20261020.json')
    after={p:digest(p) for p in baseline}
    report=dict(scope='竞技场降低难度：真实高亮按钮模板修复；后台输入状态另见实测',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        seconds=round(time.monotonic()-start,3),offlineGameInputs=0,
        cursorProposalApplied=args.cursor_proposal_applied,protectedFilesUnchangedDuringTests=before==after,
        realCursorDecision=proposal.get('decision'),virtualPointerPrototypeLiveExecuted=True,
        virtualPointerLiveEvidence=live_evidence,
        lowerConfirmationTrial=lower_evidence,
        sessionProtectedFilesMatch=session_same,protectedSha256=after,
        dailyEvidence=DailyVisionTests.evidence,
        sourceSha256={p:digest(p) for p in ('arena_daily.py','tests_arena_daily.py',
            'tests_arena_cursor_proposal.py','tests_arena_virtual_pointer.py','tests_arena_lower_probe.py',
            'arena_virtual_pointer.py','arena_lower_probe.py','tools/probe_arena_lower_virtual.py',
            'tools/audit_arena_lower_virtual.py',
            'arena_pointer_pe.py','tools/prepare_arena_daily_assets.py',
            'resources/local/arena_daily/image/lower_highlight.png','resources/local/arena_daily/sources.json')},
        redGreen=dict(before='新增真实高亮识别测试3个子例失败，board=None',
                      after='同一测试及真实未满足负例通过，阈值保持0.9'),
        limitations=['离线通过不证明后台悬停可用；实际状态以新实测记录为准',
                     '高亮源图physical-after-1，physical-after-2／4为留出图',
                     '兼容接口提案的模拟检查不代表允许或已经操作真实鼠标',
                     '单次悬停曾成功；后续单项降级验收触发1.7秒限制且两帧仍未满足，零点击，两份授权均消耗',
                     '尚未接入正式日常；正式接入须处理暂停／停止与5秒失效的临界段'])
    out=ROOT/'verification/arena-lower-fix-20261020'
    out.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    out.with_suffix('.txt').write_text(stream.getvalue(),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('tests','failures','errors','skipped','seconds',
        'cursorProposalApplied','protectedFilesUnchangedDuringTests','sessionProtectedFilesMatch')},ensure_ascii=True),flush=True)
    return 0 if result.wasSuccessful() and before==after and session_same else 1


if __name__=='__main__':sys.exit(main())
