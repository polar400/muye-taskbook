import json
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import app
from failure_archive import FailureArchive,RunFailureTracker,import_log,exception_details,classify

ROOT=Path(__file__).resolve().parents[1]

class FailureArchiveTests(unittest.TestCase):
    def test_wrapped_power_errors_keep_specific_root_category(self):
        prefix='排位战复核剩余次数和战力连续3次识别失败：'
        self.assertEqual(classify(prefix+'我方战力包含无法复核的数字，停止'),
                         ('own_power','读取我方战力'))
        self.assertEqual(classify(prefix+'对手战力局部识别不一致，停止'),
                         ('opponent_power','读取对手战力'))
        self.assertEqual(classify(prefix+'无法可靠读取剩余次数'),
                         ('remaining_count','读取剩余次数'))

    def test_timeout_snapshot_note_does_not_mean_capture_failure(self):
        self.assertEqual(classify('排位战等待超时：等待挑战面板，已保留最后截图'),
                         ('timeout','等待界面状态'))
        self.assertEqual(classify('游戏截图为黑屏或未加载'),('capture','获取游戏画面'))
        self.assertEqual(classify('游戏窗口已最小化，停止'),('capture','获取游戏画面'))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='failures-test-',dir=ROOT/'verification')
        self.root=Path(self.temp.name);self.archive=FailureArchive(self.root)

    def tearDown(self):
        self.assertEqual(self.root.resolve().parent,(ROOT/'verification').resolve())
        self.temp.cleanup()

    def tracker(self,run='run-1',task='ranked'):
        tracker=RunFailureTracker(self.root,run,'本地后台（免API）',('private-secret',))
        tracker.observe({'kind':'task','message':'任务运行中','id':task,'status':'running'})
        return tracker

    def test_failed_error_exit_and_second_reporter_count_once(self):
        first=self.tracker();second=self.tracker()
        failed={'kind':'task','id':'ranked','status':'failed','message':'排位战：未完成'}
        error={'kind':'error','message':'排位战面板识别超时：无法可靠读取剩余次数'}
        for tracker in (first,second):
            tracker.event(failed);tracker.event(error);tracker.event({'kind':'exit','message':'1'})
        self.assertEqual(len(self.archive.records()),1)
        summary=json.loads((self.archive.folder/'统计.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['errorCount'],1)

    def test_same_symptom_matches_history_but_different_step_does_not(self):
        a=self.tracker('a').failure('排位战面板识别超时：无法可靠读取剩余次数')
        b=self.tracker('b').failure('无法可靠读取剩余次数')
        c=self.tracker('c').failure('我方战力无法可靠识别')
        self.assertEqual(b['similarIds'],[a['id']]);self.assertEqual(b['similarCount'],1)
        self.assertEqual(c['similarCount'],0)
        review=FailureArchive(self.root).review('ranked')
        self.assertIn('已有3次错误',review);self.assertIn('读取剩余次数 2次',review)

    def test_manual_stop_and_forced_exit_are_not_errors(self):
        tracker=self.tracker()
        tracker.event({'kind':'interrupted','message':'用户主动停止运行'})
        tracker.event({'kind':'error','message':'已停止','manual':True})
        tracker.event({'kind':'exit','message':'1'},manual=True)
        summary=json.loads((self.archive.folder/'统计.json').read_text(encoding='utf-8'))
        self.assertEqual((summary['errorCount'],summary['interruptionCount']),(0,1))
        self.assertIn('暂无错误记录',self.archive.review('ranked'))

    def test_unexplained_exit_captures_context_and_last_active_task(self):
        tracker=self.tracker(task='hosting')
        tracker.event({'kind':'log','message':'已确认进入托管中状态'})
        record=tracker.event({'kind':'exit','message':'17'})
        self.assertEqual(record['taskId'],'hosting')
        self.assertEqual(record['lastStep'],'已确认进入托管中状态')
        self.assertIn('17',record['error']);self.assertIsNone(record['source'])

    def test_failed_status_without_error_still_archives_on_exit_zero(self):
        tracker=self.tracker()
        tracker.event({'kind':'task','message':'排位战：未完成','id':'ranked','status':'failed'})
        self.assertIsNotNone(tracker.event({'kind':'exit','message':'0'}))

    def test_completed_tasks_and_successful_exit_do_not_create_incidents(self):
        tracker=self.tracker()
        tracker.event({'kind':'task','message':'完成','id':'ranked','status':'done'})
        self.assertIsNone(tracker.event({'kind':'exit','message':'0'}))
        self.assertEqual(self.archive.records(),[])

    def test_snapshot_is_immutable_and_traceback_has_actual_source(self):
        image=self.root/'failure.png';image.write_bytes(b'original-evidence')
        try:raise RuntimeError('我方战力无法可靠识别')
        except RuntimeError as e:metadata=exception_details(e)
        metadata.update(screenshot=str(image),evidenceNote='本任务最后捕获画面')
        record=self.tracker().failure('我方战力无法可靠识别',metadata=metadata)
        image.write_bytes(b'next-task-image')
        self.assertEqual((self.root/record['screenshot']).read_bytes(),b'original-evidence')
        self.assertGreater(record['source']['line'],0)
        self.assertEqual(record['source']['function'],'test_snapshot_is_immutable_and_traceback_has_actual_source')
        self.assertIn('RuntimeError',record['traceback'])

    def test_credentials_are_redacted_from_message_context_and_traceback(self):
        tracker=self.tracker()
        tracker.event({'kind':'log','message':'private-secret Authorization: Bearer abc.def api_key=other-token'})
        tracker.failure('private-secret',metadata={'traceback':'private-secret password=hunter2'})
        for file in self.archive.folder.rglob('*'):
            if file.suffix in ('.json','.md'):
                text=file.read_text(encoding='utf-8')
                for secret in ('private-secret','abc.def','other-token','hunter2'):self.assertNotIn(secret,text)

    def test_two_concurrent_failures_survive_export(self):
        trackers=[self.tracker('a'),self.tracker('b')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda tracker:tracker.failure('无法可靠读取剩余次数'),trackers))
        self.assertEqual(len(self.archive.records()),2)
        summary=json.loads((self.archive.folder/'统计.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['errorCount'],2)

    def test_historical_import_deduplicates_and_preserves_unknown_evidence(self):
        path=self.root/'2026-10-12.log'
        path.write_text('\n'.join([
            '[15:01:45] 游戏内托管：后台运行中','[15:01:55] 已确认进入托管中状态',
            '[15:05:12] 游戏内托管：未完成','[15:05:12] 无法唯一定位游戏面板关闭图标',
            '[15:23:45] 游戏内托管：后台运行中','[15:25:53] 游戏内托管：未完成',
            '[15:25:53] 无法唯一定位游戏面板关闭图标',
            '[15:26:14] 排位战：后台运行中','[15:26:32] 排位战：未完成',
            '[15:26:32] 已停止','[15:26:32] 执行已停止',
            '[15:30:57] 排位战：后台运行中','[15:31:02] 排位战：未完成',
            '[15:31:02] 我方战力无法可靠识别',
        ]),encoding='utf-8')
        self.assertEqual(import_log(self.root,path),4)
        self.assertEqual(import_log(self.root,path),0)
        path.write_text(path.read_text(encoding='utf-8')+'\n[17:10:04] 排位战：后台运行中\n[17:10:43] 排位战：未完成\n[17:10:43] 无法可靠读取剩余次数',encoding='utf-8')
        self.assertEqual(import_log(self.root,path),1)
        records=self.archive.records()
        self.assertEqual(sum(r['status']=='interrupted' for r in records),1)
        self.assertEqual(records[1]['similarCount'],1)
        for record in records:
            self.assertIsNone(record['source']);self.assertIsNone(record['screenshot'])
            self.assertGreater(record['logOrigin']['line'],0)

    def test_history_truncated_after_failed_status_records_unknown_cause(self):
        path=self.root/'2026-10-12.log'
        path.write_text('[17:10:04] 排位战：后台运行中\n[17:10:43] 排位战：未完成',encoding='utf-8')
        self.assertEqual(import_log(self.root,path),1)
        self.assertIn('错误详情缺失',self.archive.records()[0]['error'])

    def test_current_run_marker_import_does_not_duplicate_structured_incident(self):
        tracker=self.tracker('new-run')
        tracker.failure('无法可靠读取剩余次数')
        path=self.root/'2026-10-12.log'
        path.write_text('[17:10:02] 运行编号：new-run\n[17:10:04] 排位战：后台运行中\n[17:10:43] 排位战：未完成\n[17:10:43] 无法可靠读取剩余次数',encoding='utf-8')
        self.assertEqual(import_log(self.root,path),0)

    def test_collector_archives_before_ui_consumes_event(self):
        tracker=self.tracker()
        ui=SimpleNamespace(events=queue.Queue(),stopping=False)
        app.App.collect_failure_event(ui,{'kind':'error','message':'我方战力无法可靠识别'},tracker)
        self.assertEqual(len(self.archive.records()),1)
        self.assertEqual(ui.events.get()['kind'],'error')
        self.assertIn('错误已归档',ui.events.get()['message'])

if __name__=='__main__':unittest.main()
