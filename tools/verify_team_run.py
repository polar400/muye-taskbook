"""Offline daily policy, UI, entry, battle handoff and settlement checks."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    protected=['config.json','run.json','local_flows.py','adapters/background_window.py','adapters/local_ocr.py','mission_desk_ui.py']
    def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in protected}
    before=hashes()
    names=['tests_team_instance','tests_team_instance_ui','tests_team_instance_challenge',
           'tests_team_instance_settlement','tests_team_instance_daily','tests_team_instance_hold','tests_team_instance_run','tests_team_instance_rewards']
    names += ['tests_local.LocalTests.'+name for name in (
        'test_auto_waits_for_loading_then_enables_once','test_auto_already_enabled_does_not_toggle_it_off',
        'test_auto_and_speed_click_in_same_frame','test_auto_enables_double_speed_after_confirming_active')]
    stream=io.StringIO();start=time.monotonic()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    after=hashes()
    report=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                seconds=round(time.monotonic()-start,3),protectedUnchangedDuringTests=before==after,
                protectedSha256=after,gameInputs=0,liveVerified=False,
                limitations=['每次启动重新计数，旧本地账本保留但不再读取；本次重启接续场计入1场',
                             '灰色入口依据北京时间规则跳过，尚无灰色图独立视觉测试',
                             '新次数规则及重启接续为模拟验证，未实机挑战',
                             '返回叉号为来源图验证，未知皮肤仍可能停止'])
    (ROOT/'verification/team-instance-run-tests-20261025.txt').write_text(stream.getvalue(),encoding='utf-8')
    (ROOT/'verification/team-instance-run-20261025.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(stream.getvalue());print(json.dumps(report,ensure_ascii=True))
    return 0 if result.wasSuccessful() and before==after else 1

if __name__=='__main__':sys.exit(main())
