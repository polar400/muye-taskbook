import io
import json
from datetime import date
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app
from failure_archive import FailureArchive
from log_retention import maintain_logs

class ReleaseTests(unittest.TestCase):
    def test_fifteen_calendar_days_with_multiple_logs_and_incidents(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'verification') as temporary:
            root=Path(temporary);logs=root/'logs';logs.mkdir()
            for name in ('2026-10-23.log','2026-10-24.log','2026-10-24.backup.log','2026-11-07.log'):
                (logs/name).write_text('run',encoding='utf-8')
            archive=FailureArchive(root)
            for ident,day in [('old','2026-10-23'),('edge','2026-10-24'),('current','2026-11-07')]:
                image=root/(ident+'.png');image.write_bytes(b'evidence')
                archive.record({'id':ident,'taskId':'ranked','runId':ident,'status':'error',
                                'error':'我方战力识别失败','occurredAt':day+'T12:00:00+08:00'},image)
            deleted=maintain_logs(root,date(2026,11,7))
            self.assertFalse((logs/'2026-10-23.log').exists())
            self.assertEqual(len(list(logs.iterdir())),3)
            self.assertEqual([r['id'] for r in archive.records()],['edge','current'])
            self.assertEqual([r['similarCount'] for r in archive.records()],[0,1])
            self.assertFalse((root/'出错任务/排位战/证据/old.png').exists())
            self.assertFalse((root/'出错任务/排位战/记录/old.md').exists())
            self.assertEqual(json.loads((root/'出错任务/统计.json').read_text(encoding='utf-8'))['errorCount'],2)
            self.assertEqual(maintain_logs(root,date(2026,11,7)),[])
            self.assertTrue(deleted)

    def test_runtime_error_message_has_no_historical_count(self):
        ui=SimpleNamespace(events=queue.Queue(),stopping=False)
        tracker=Mock();tracker.secrets=()
        tracker.event.return_value={'status':'error','taskName':'排位战','step':'读取战力','similarCount':99}
        app.App.collect_failure_event(ui,{'kind':'error','message':'本次读取失败'},tracker)
        self.assertEqual(ui.events.get()['message'],'本次读取失败')
        message=ui.events.get()['message']
        self.assertIn('错误已归档',message)
        self.assertNotIn('历史',message);self.assertNotIn('99',message)

    def test_log_cleanup_is_triggered_again_after_midnight(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'verification') as temporary:
            root=Path(temporary)
            ui=SimpleNamespace(api_key=Mock(get=lambda:''),failure_tracker=None,log_views=[])
            with patch.object(app,'ROOT',root),patch.object(app,'local_day',side_effect=[date(2026,11,7),date(2026,11,7),date(2026,11,8)]),patch.object(app,'maintain_logs') as cleanup:
                for _ in range(3):app.App.log(ui,'当前运行步骤')
            self.assertEqual(cleanup.call_count,2)
            self.assertTrue((root/'logs/2026-11-08.log').exists())

    def test_node_worker_has_no_history_output(self):
        source=(Path(__file__).resolve().parents[1]/'src/worker.mjs').read_text(encoding='utf-8')
        self.assertNotIn('reviewHistory',source)
        self.assertNotIn('历史复盘',source)

if __name__=='__main__':unittest.main()
