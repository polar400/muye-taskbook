"""Arena tool integration, isolated storage, no game input."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import app
import native_worker

PROJECT=Path(__file__).resolve().parent


class ArenaUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arena-ui-',dir=PROJECT/'verification')
        self.folder=Path(self.temp.name)
        self.patches=[patch.object(app,'ROOT',self.folder),patch.object(app,'game_windows',return_value=[])]
        for item in self.patches:item.start()
        self.ui=app.App();self.ui.update()

    def tearDown(self):
        for timer in self.ui.tk.call('after','info'):self.ui.after_cancel(timer)
        self.ui.destroy()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def labels(self,parent):
        text=[]
        for child in parent.winfo_children():
            if child.winfo_class()=='TLabel':text.append(child.cget('text'))
            text+=self.labels(child)
        return text

    def test_arena_is_selectable_once_and_has_both_settings_tabs(self):
        self.assertEqual(sum(key=='arena' for key,label in app.TASKS),1)
        self.assertEqual(dict(app.TASKS)['arena'],'竞技场')
        self.ui.select_all(False);self.ui.selection['arena'].set(True)
        self.assertEqual(self.ui.config()['tasks'],[])
        self.assertNotIn('arena',self.ui.task_rows)
        for mode in ('common','advanced'):
            self.ui.show_task('arena',mode);self.ui.update()
            self.assertEqual(self.ui.notebook.select(),str(self.ui.help_panel))
            text=' '.join(self.labels(self.ui.arena_view.task_fields))
            for word in ('主界面','竞技场图标','停留','战斗','本地后台'):self.assertIn(word,text)
            for removed in ('苦无','日常活动','参加'):self.assertNotIn(removed,text)
        self.assertFalse((self.folder/'config.json').exists())

    def test_seven_rows_and_start_controls_fit_supported_sizes(self):
        for geometry in ('1060x720','1240x820','1500x960'):
            with self.subTest(geometry=geometry):
                self.ui.geometry(geometry);self.ui.update()
                for key,row in self.ui.task_rows.items():
                    check=self.ui.task_checks[key]
                    self.assertGreaterEqual(check.winfo_width(),check.winfo_reqwidth())
                    self.assertLessEqual(check.winfo_x()+check.winfo_width(),self.ui.gears[key].winfo_x())
                self.assertLessEqual(self.ui.preview_button.winfo_rooty()+self.ui.preview_button.winfo_height(),
                                     self.ui.winfo_rooty()+self.ui.winfo_height())

    def test_old_config_appends_arena_without_selecting_it(self):
        old=[key for key,_ in app.TASKS if key!='arena']
        (self.folder/'config.json').write_text(json.dumps(dict(tasks=['ranked'],taskOrder=old)),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order,old)
        self.assertEqual(self.ui.config()['tasks'],['ranked'])
        self.assertFalse(self.ui.selection['arena'].get())

    def test_mode_selection_is_mutually_exclusive_and_persists(self):
        self.ui.select_all(False);self.ui.selection['arena'].set(True)
        self.ui.show_task('arena','common');self.ui.update()
        radios=[child for child in self.ui.arena_view.task_fields.winfo_children() if child.winfo_class()=='TRadiobutton']
        self.assertEqual(len(radios),3)
        self.assertEqual(self.ui.config()['arenaMode'],'休闲战斗')
        radios[0].invoke();self.assertEqual(self.ui.config()['arenaMode'],'段位战斗')
        self.ui.save();self.ui.arena_mode.set('休闲战斗');self.ui.load()
        self.assertEqual(self.ui.arena_mode.get(),'段位战斗')
        radios[1].invoke();self.assertEqual(self.ui.config()['arenaMode'],'休闲战斗')
        radios[2].invoke();self.assertEqual(self.ui.config()['arenaMode'],'日常模式')
        self.ui.save();self.ui.arena_mode.set('休闲战斗');self.ui.load()
        self.assertEqual(self.ui.arena_mode.get(),'日常模式')
        self.assertEqual(radios[2].cget('text'),'日常模式（战令用完转休闲）')

    def test_backend_and_invalid_arena_mode_rejected_before_launch(self):
        self.ui.select_all(False);self.ui.selection['arena'].set(True)
        self.ui.preview.set(True)
        for invalid in ('backend','mode'):
            with self.subTest(invalid=invalid):
                self.ui.backend.set('Midscene前台' if invalid=='backend' else '本地后台（免API）')
                self.ui.arena_mode.set('未知模式' if invalid=='mode' else '休闲战斗')
                with patch.object(app.subprocess,'Popen') as process,patch.object(app.messagebox,'showerror') as error:
                    self.ui.start(arena_only=True);process.assert_not_called();error.assert_called_once()
                self.assertFalse((self.folder/'run.json').exists())

    def test_native_preview_and_real_dispatch_report_opened(self):
        resources=self.folder/'resources';resources.mkdir()
        (resources/'tasks.json').write_bytes((PROJECT/'resources/tasks.json').read_bytes())
        path=self.folder/'run.json'
        cfg={'tasks':['arena'],'gameHwnd':1,'preview':True}
        path.write_text(json.dumps(cfg),encoding='utf-8')
        flow=Mock();window=Mock();tracker=Mock();tracker.archive.review.return_value='test'
        with patch.object(native_worker,'ROOT',self.folder),patch.object(native_worker,'tracker',None),\
             patch.object(native_worker,'window',None),patch.object(native_worker,'flow',None),\
             patch.object(native_worker.sys,'argv',['native_worker.py',str(path)]),\
             patch.object(native_worker,'RunFailureTracker',return_value=tracker),\
             patch.object(native_worker,'BackgroundWindow',return_value=window) as construct,\
             patch.object(native_worker,'LocalOCR'),patch.object(native_worker,'LocalFlows',return_value=flow),\
             patch.object(native_worker,'run_arena',return_value='opened') as arena,\
             patch.object(native_worker,'run_ranked_pipeline') as ranked,\
             patch.object(native_worker,'emit') as emit,contextlib.redirect_stdout(io.StringIO()):
            native_worker.main();construct.assert_not_called();arena.assert_not_called()
            cfg['preview']=False;path.write_text(json.dumps(cfg),encoding='utf-8')
            native_worker.main();arena.assert_called_once_with(flow)
            flow.run.assert_not_called();ranked.assert_not_called()
            self.assertTrue(any('界面已打开' in item.args[1] for item in emit.call_args_list))


if __name__=='__main__':unittest.main()
