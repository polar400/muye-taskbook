import json
import unittest
from unittest.mock import Mock, patch
import app
import native_worker
from tests_arena_ui import ArenaUITests as Fixture
from team_instance_task import validate_team_instance_config

class TeamInstanceUITests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown

    def test_visible_and_settings_work(self):
        self.assertIn('team_instance',self.ui.task_rows)
        self.assertEqual(dict(app.TASKS)['team_instance'],'组队副本')
        for mode in ('common','advanced'):
            self.ui.show_task('team_instance',mode)
            self.ui.update()
            self.assertEqual(self.ui.task_title.cget('text'),'组队副本')
            self.assertIn('达到本次设定次数',self.ui.task_hint.get())
        self.ui.select_all(False)
        self.ui.selection['team_instance'].set(True)
        self.assertEqual(self.ui.config()['tasks'],['team_instance'])
        self.ui.team_instance_daily_count.set(3)
        self.ui.save()
        self.ui.team_instance_daily_count.set(1)
        self.ui.team_instance_name.set('五影会谈')
        self.ui.team_instance_difficulty.set('困难')
        self.ui.selection['team_instance'].set(False)
        self.ui.load()
        self.assertEqual(self.ui.team_instance_name.get(),'桥上的决战')
        self.assertEqual(self.ui.team_instance_difficulty.get(),'简单')
        self.assertEqual(self.ui.team_instance_daily_count.get(),3)
        self.assertTrue(self.ui.selection['team_instance'].get())

    def test_old_config_appends_unselected(self):
        old=[k for k,_ in app.TASKS if k!='team_instance']
        (self.folder/'config.json').write_text(json.dumps(dict(tasks=['ranked'],taskOrder=old)),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order,old+['team_instance'])
        self.assertFalse(self.ui.selection['team_instance'].get())
        self.assertEqual(self.ui.team_instance_daily_count.get(),1)

    def test_reject_unsupported_backend_and_order(self):
        for cfg in (dict(tasks=['team_instance'],backend='Midscene前台'),dict(tasks=['team_instance','ranked'])):
            with self.assertRaises(ValueError):validate_team_instance_config(cfg)
        validate_team_instance_config(dict(tasks=['ranked','team_instance']))

    def test_named_challenge_can_precede_other_tasks(self):
        from arena_task import validate_arena_config
        cfg=dict(tasks=['team_instance','ranked','arena'],teamInstanceName='桥上的决战',teamInstanceDifficulty='简单')
        validate_team_instance_config(cfg)
        validate_arena_config(cfg)
        cfg['tasks']=['team_instance','team_instance']
        with self.assertRaisesRegex(ValueError,'重复'):validate_team_instance_config(cfg)

    def test_preview_and_unverified_dispatch(self):
        resources=self.folder/'resources'
        resources.mkdir()
        (resources/'tasks.json').write_bytes((app.Path(__file__).resolve().parents[1]/'resources/tasks.json').read_bytes())
        path=self.folder/'run.json'
        cfg=dict(tasks=['team_instance'],gameHwnd=1,preview=True)
        path.write_text(json.dumps(cfg),encoding='utf-8')
        flow=Mock()
        with patch.object(native_worker,'ROOT',self.folder),patch.object(native_worker,'tracker',None), \
             patch.object(native_worker,'window',None),patch.object(native_worker,'flow',None), \
             patch.object(native_worker.sys,'argv',['native_worker.py',str(path)]), \
             patch.object(native_worker,'RunFailureTracker'),patch.object(native_worker,'BackgroundWindow') as window, \
             patch.object(native_worker,'LocalOCR'),patch.object(native_worker,'LocalFlows',return_value=flow), \
             patch.object(native_worker,'run_team_instance',return_value='participated_unverified') as run, \
             patch.object(native_worker,'emit') as emit:
            native_worker.main()
            window.assert_not_called()
            run.assert_not_called()
            cfg['preview']=False
            path.write_text(json.dumps(cfg),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'尚未验证'):native_worker.main()
            run.assert_called_once_with(flow)
            flow.run.assert_not_called()
            self.assertFalse(any(c.kwargs.get('id')=='team_instance' and c.kwargs.get('status')=='done' for c in emit.call_args_list))

            cfg.update(tasks=['team_instance','escort'],teamInstanceName='桥上的决战',teamInstanceDifficulty='简单')
            path.write_text(json.dumps(cfg),encoding='utf-8')
            for result in ('daily_completed','closed'):
                flow.reset_mock();run.return_value=result
                native_worker.main()
                flow.run.assert_called_once_with('escort')
            flow.reset_mock();run.side_effect=RuntimeError('未确认主页')
            with self.assertRaisesRegex(RuntimeError,'未确认主页'):native_worker.main()
            flow.run.assert_not_called()

del Fixture

if __name__=='__main__':unittest.main()
