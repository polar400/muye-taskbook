"""Offline capped battles and proposed count settings; no game input."""
import hashlib
import argparse
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
    parser.add_argument('--popups',action='store_true',help='Verify arena trial skip and victory confirmation')
    parser.add_argument('--battle-confirm',action='store_true',help='Verify battle blue-confirm recognition and return routing')
    args=parser.parse_args()
    popup_scope=args.popups or args.battle_confirm
    baseline=json.loads((ROOT/('verification/arena-battle-confirm-protected-20261025.json' if args.battle_confirm else
                              'verification/arena-popups-protected-20261023.json' if args.popups else
                              'verification/arena-count-protected-20261023.json')).read_text(encoding='utf-8'))
    integration=json.loads((ROOT/'verification/arena-count-integration-20261023.json').read_text(encoding='utf-8'))
    before={p:digest(p) for p in baseline};start=time.monotonic();stream=io.StringIO()
    names=['tests_arena','tests_arena_daily','tests_arena_tokens','tests_arena_hover','tests_arena_ui','tests_arena_count_ui']
    if popup_scope:names.append('tests_arena_popups')
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    after={p:digest(p) for p in baseline}
    from tools.prepare_arena_count_integration import UI_SOURCE
    applied=integration.get('applied',False) and integration.get('decision')=='allowed_by_user'
    same=all(after[p]==sha for p,sha in baseline.items() if not(applied and not popup_scope and p=='app.py'))
    if applied and not popup_scope:
        same=same and hashlib.sha256((ROOT/'src/app.py').read_text(encoding='utf-8').encode()).hexdigest()==integration['files']['app.py']['proposedTextSha256']
    static_same=all(after[p]==sha for p,sha in baseline.items() if p not in ('config.json','run.json')) if popup_scope else same
    user_changes={p:dict(baseline=baseline[p],beforeTests=before[p],afterTests=after[p])
                  for p in ('config.json','run.json') if after[p]!=baseline[p]}
    ui_applied=(ROOT/'src/arena_task_ui.py').read_text(encoding='utf-8')==UI_SOURCE
    files=('arena_daily.py','arena_task.py','arena_settings.py','arena_task_ui.py','arena_tokens.py',
           'tests_arena_daily.py','tests_arena_tokens.py','tests_arena_count_ui.py',
           'tools/prepare_arena_count_integration.py','app.py','tests_arena_popups.py',
           'tools/prepare_arena_popup_assets.py','resources/local/arena/popups/sources.json',
           'resources/local/arena/popups/trial_title.png','resources/local/arena/popups/trial_skip.png',
           'resources/local/arena/popups/victory_title.png','resources/local/arena/popups/victory_confirm.png',
           'resources/local/arena_popup_references/battle-victory-confirm-20261025.json',
           'resources/local/arena_popup_references/battle-victory-confirm-game.png')
    report=dict(scope='竞技场战斗内蓝色确认漏识别修复' if args.battle_confirm else
                      '竞技场试用弹窗跳过及胜利确认' if args.popups else '竞技场三模式统一场数上限、先领奖、不自动降级',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        seconds=round(time.monotonic()-start,3),gameInputs=0,liveVerified=False,
        defaultBattleLimit=3,allowedBattleLimit=[1,100],automaticLowering=False,
        sharedPatchApplied=applied,uiSettingsApplied=ui_applied,
        protectedFilesUnchangedDuringTests=before==after,sessionProtectedFilesMatch=same,protectedSha256=after,
        staticFilesMatchBaseline=static_same,observedUserFileChanges=user_changes,
        sourceSha256={p:digest(p) for p in files},
        settingsProposal='verification/arena-count-integration-20261023.patch',
        limitations=['真实竞技场匹配、自动开启反馈、胜败返回及领取后的变化尚未实机验收',
                     '战令0／1及零任务终态尚缺真实样图，已有模拟覆盖',
                     '计数仅在明确胜败结算且确认返回竞技场后增加；输入结果不确定即停',
                     '共享app.py及常规设置控件仍为待协调补丁' if not applied else '已协调接入共享app.py；未修改用户配置文件'])
    if popup_scope:
        from tests_arena_popups import ArenaPopupTests
        report.update(popupEvidence=ArenaPopupTests.evidence,sharedFilesChangedForPopups=False)
        report['limitations'].append('两种新弹窗仅用户原图及模拟路由验证；未实机跳过／确认，未验证其他皮肤')
    if args.battle_confirm:
        report.update(sharedFilesChangedForBattleConfirm=False,
            redGreen=dict(before='新增真实蓝色确认回归退出1：settlement=None',
                          after='本报告真实图及两场模拟接续检查',
                          evidence='verification/arena-battle-confirm-red-20261025.json'))
        report['limitations'].append('新蓝色确认截图为胜利；失败使用旧真实确定图及确认别名模拟，尚无新蓝色失败原图')
    path=ROOT/('verification/arena-battle-confirm-20261025' if args.battle_confirm else
               'verification/arena-popups-20261023' if args.popups else 'verification/arena-count-20261023')
    path.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    path.with_suffix('.txt').write_text(stream.getvalue(),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('tests','failures','errors','skipped','seconds',
        'sharedPatchApplied','uiSettingsApplied','protectedFilesUnchangedDuringTests','sessionProtectedFilesMatch')},ensure_ascii=True))
    return 0 if result.wasSuccessful() and before==after and static_same else 1


if __name__=='__main__':sys.exit(main())
