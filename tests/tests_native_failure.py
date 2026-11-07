"""Exercise the native worker with mocked capture and input, without a GUI."""
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import native_worker as worker
from failure_archive import FailureArchive,RunFailureTracker

ROOT=Path(__file__).resolve().parents[1]

class NativeFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='native-failure-test-',dir=ROOT/'verification')
        self.root=Path(self.temp.name)
        (self.root/'verification').mkdir();(self.root/'resources').mkdir()
        (self.root/'resources/tasks.json').write_text(json.dumps({'tasks':[{'id':'ranked','label':'排位战'}]}),encoding='utf-8')
        self.stack=ExitStack()
        self.dpi=self.stack.enter_context(patch.object(worker.ctypes.windll.shcore,'SetProcessDpiAwareness'))
        for name,value in [('ROOT',self.root),('tracker',None),('window',None),('flow',None)]:self.stack.enter_context(patch.object(worker,name,value))
        worker.stopped.clear()

    def tearDown(self):
        self.stack.close();worker.stopped.clear()
        self.assertEqual(self.root.resolve().parent,(ROOT/'verification').resolve())
        self.temp.cleanup()

    def test_worker_runs_without_history_and_archives_before_exit(self):
        previous=RunFailureTracker(self.root,'previous')
        previous.observe({'kind':'task','message':'排位战：运行中','id':'ranked','status':'running'})
        previous.failure('我方战力无法可靠识别')
        cfg=self.root/'run.json';cfg.write_text(json.dumps({'tasks':['ranked'],'gameHwnd':42,'runId':'native-test'}),encoding='utf-8')
        window=Mock();window.calibrate.return_value=object()
        window.save.side_effect=lambda image,path:Path(path).write_bytes(b'captured-frame')
        def run(task):
            print('TEST_OPERATION')
            raise RuntimeError('我方战力无法可靠识别')
        flow=SimpleNamespace(image=object(),run=run)
        output=io.StringIO()
        with patch.object(worker.sys,'argv',['native_worker.py',str(cfg)]),patch.object(worker,'BackgroundWindow',return_value=window),patch.object(worker,'LocalOCR'),patch.object(worker,'LocalFlows',return_value=flow),patch.object(worker,'run_ranked_pipeline',side_effect=lambda flow:flow.run('ranked')) as pipeline,redirect_stdout(output):
            try:worker.main()
            except RuntimeError as e:worker.report_error(e)
        text=output.getvalue()
        self.dpi.assert_called_once_with(2)
        pipeline.assert_called_once_with(flow)
        self.assertNotIn('历史复盘',text)
        self.assertIn('TEST_OPERATION',text)
        records=FailureArchive(self.root).records()
        self.assertEqual(len(records),2)
        incident=records[-1]
        self.assertEqual(incident['similarCount'],1)
        self.assertEqual(incident['taskId'],'ranked')
        self.assertEqual((self.root/incident['screenshot']).read_bytes(),b'captured-frame')
        self.assertEqual(incident['source']['function'],'run')
        window.click.assert_not_called()

    def test_native_manual_stop_only_records_interruption(self):
        worker.tracker=RunFailureTracker(self.root,'native-stop')
        worker.tracker.observe({'kind':'task','message':'排位战：运行中','id':'ranked','status':'running'})
        worker.stopped.set()
        with redirect_stdout(io.StringIO()):worker.report_error(RuntimeError('已停止'))
        record=FailureArchive(self.root).records()[0]
        self.assertEqual(record['status'],'interrupted')
        self.assertIsNone(record['screenshot'])

if __name__=='__main__':unittest.main()
