"""Isolated Tk settings and native worker integration; never connect a game."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import app
import native_worker
from local_flows import LocalFlows
from failure_archive import LABELS

PROJECT=Path(__file__).resolve().parent


class WantedUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wanted-ui-',dir=PROJECT/'verification')
        self.folder=Path(self.temp.name)
        self.patches=[patch.object(app,'ROOT',self.folder),patch.object(app,'game_windows',return_value=[])]
        for p in self.patches:p.start()
        self.ui=app.App();self.ui.withdraw();self.ui.update()

    def tearDown(self):
        for timer in self.ui.tk.call('after','info'):self.ui.after_cancel(timer)
        self.ui.destroy()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def labels(self,widget):
        result=[]
        for child in widget.winfo_children():
            if child.winfo_class()=='TLabel':result.append(child.cget('text'))
            result+=self.labels(child)
        return result

    def test_task_is_selectable_and_common_and_advanced_render(self):
        self.assertEqual(dict(app.TASKS)['wanted'],'通缉任务')
        self.assertIn('wanted',self.ui.task_rows)
        self.ui.select_all(False);self.ui.selection['wanted'].set(True)
        self.assertEqual(self.ui.config()['tasks'],['wanted'])
        for mode in ('common','advanced'):
            self.ui.show_task('wanted',mode);self.ui.update()
            text=' '.join(self.labels(self.ui.task_fields))
            self.assertIn('日常活动',text)
            self.assertIn('本地后台',text)
            self.assertIn('今日余下次数0',self.ui.task_hint.get())
        self.assertIn('30分钟',text)

    def test_saved_selection_order_and_existing_settings_survive_reload(self):
        self.ui.select_all(False);self.ui.selection['wanted'].set(True)
        self.ui.difficulty.set('天级');self.ui.move_task('wanted',-1);self.ui.save()
        saved=json.loads((self.folder/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['tasks'],['wanted'])
        self.ui.selection['wanted'].set(False);self.ui.difficulty.set('夜叉级');self.ui.load()
        self.assertTrue(self.ui.selection['wanted'].get())
        self.assertEqual(self.ui.difficulty.get(),'天级')
        self.assertEqual(self.ui.task_order,saved['taskOrder'])

    def test_six_task_rows_fit_at_supported_sizes(self):
        self.ui.deiconify()
        for geometry in ('940x680','1280x780','1500x900'):
            self.ui.geometry(geometry);self.ui.update()
            self.assertEqual(len(self.ui.task_rows),6)
            self.assertLess(self.ui.preview_button.winfo_rooty()+self.ui.preview_button.winfo_height(),
                            self.ui.winfo_rooty()+self.ui.winfo_height())
            for key,row in self.ui.task_rows.items():
                check=next(child for child in row.winfo_children() if child.winfo_class()=='TCheckbutton')
                self.assertGreaterEqual(check.winfo_width(),check.winfo_reqwidth())
                self.assertLessEqual(check.winfo_x()+check.winfo_width(),self.ui.gears[key].winfo_x())

    def test_old_config_keeps_selection_and_appends_new_option(self):
        old=['survival','strong','hosting','ranked','escort']
        p=self.folder/'config.json'
        p.write_text(json.dumps({'tasks':['ranked'],'taskOrder':old}),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order,old+['wanted'])
        self.assertEqual(self.ui.config()['tasks'],['ranked'])
        self.assertFalse(self.ui.selection['wanted'].get())

    def test_frontend_backend_is_rejected_before_process_or_game_access(self):
        self.ui.select_all(False);self.ui.selection['wanted'].set(True)
        self.ui.backend.set('Midscene前台');self.ui.preview.set(True)
        with patch.object(app.subprocess,'Popen') as process,patch.object(app.messagebox,'showerror') as error:
            self.ui.start()
            process.assert_not_called()
            self.assertIn('本地后台',error.call_args.args[1])
        self.assertFalse((self.folder/'run.json').exists())

    def test_native_preview_knows_task_without_constructing_window(self):
        cfg=self.folder/'preview.json';cfg.write_text(json.dumps({'tasks':['wanted'],'preview':True}),encoding='utf-8')
        resources=self.folder/'resources';resources.mkdir()
        (resources/'tasks.json').write_bytes((PROJECT/'resources/tasks.json').read_bytes())
        stream=io.StringIO()
        with patch.object(native_worker,'ROOT',self.folder),patch.object(native_worker.sys,'argv',['native_worker.py',str(cfg)]),patch.object(native_worker,'tracker',None),patch.object(native_worker,'RunFailureTracker',return_value=Mock()),patch.object(native_worker,'BackgroundWindow') as window,patch.object(native_worker.ctypes.windll.shcore,'SetProcessDpiAwareness'),contextlib.redirect_stdout(stream):
            native_worker.main()
            window.assert_not_called()
        events=[json.loads(line[10:]) for line in stream.getvalue().splitlines() if line.startswith('APP_EVENT ')]
        self.assertTrue(any(e.get('id')=='wanted' and e.get('status')=='preview' for e in events))
        self.assertEqual(LABELS['wanted'],'通缉任务')
        flow=object.__new__(LocalFlows)
        with patch('local_flows.run_wanted',return_value='verified') as run:
            self.assertEqual(flow.run('wanted'),'verified')
            run.assert_called_once_with(flow)


if __name__=='__main__':unittest.main()
