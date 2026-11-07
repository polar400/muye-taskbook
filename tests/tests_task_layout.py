"""Task ordering, responsive layout and shared logs; never operate the game."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app


class TaskLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='layout-test-',dir=app.ROOT/'verification')
        self.root=Path(self.temp.name)
        self.patches=[patch.object(app,'ROOT',self.root),patch.object(app.App,'refresh_windows'),
                      patch.object(app.messagebox,'showerror',side_effect=AssertionError)]
        for mock in self.patches:mock.start()
        # Keep this legacy five-task fixture; the six-task UI is covered by
        # tests_wanted_ui, including queue persistence and responsive layout.
        legacy=patch.object(app,'TASKS',[(key,label) for key,label in app.TASKS if key!='wanted'])
        legacy.start();self.patches.append(legacy)
        self.ui=app.App()
        self.ui.update()

    def tearDown(self):
        for callback in self.ui.tk.call('after','info'):self.ui.after_cancel(callback)
        self.ui.destroy()
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def drag(self,key,y):
        handle=self.ui.task_handles[key]
        handle.event_generate('<ButtonPress-1>',x=10,y=12)
        handle.event_generate('<B1-Motion>',x=10,y=y-handle.winfo_rooty())
        self.ui.update_idletasks()
        self.assertTrue(self.ui.task_drop_line.winfo_ismapped())
        handle.event_generate('<ButtonRelease-1>',x=10,y=y-handle.winfo_rooty())
        self.ui.update_idletasks()

    def test_drag_up_down_persists_and_preserves_settings(self):
        self.ui.save()
        original=json.loads((self.root/'config.json').read_text(encoding='utf-8'))
        self.ui.hosting_minutes.set(37)  # Unsaved settings must stay unsaved.
        self.drag('escort',self.ui.task_list.winfo_rooty()-12)
        self.assertEqual(self.ui.task_order[0],'escort')
        self.drag('escort',self.ui.task_list.winfo_rooty()+self.ui.task_list.winfo_height()+12)
        self.assertEqual(self.ui.task_order[-1],'escort')
        self.ui.move_task('hosting',-1)
        cfg=json.loads((self.root/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['hostingMinutes'],original['hostingMinutes'])
        self.assertEqual(cfg['taskOrder'],self.ui.task_order)
        self.ui.task_order.reverse();self.ui.load()
        self.assertEqual(self.ui.task_order,cfg['taskOrder'])

    def test_selected_queue_uses_visual_order_and_disabled_rows_survive(self):
        self.ui.selection['strong'].set(False)
        self.ui.move_task('hosting',-1)
        self.assertEqual(self.ui.config()['tasks'],['survival','hosting','ranked','escort'])
        self.assertIn('strong',self.ui.config()['taskOrder'])
        self.assertFalse(self.ui.selection['strong'].get())
        self.assertEqual(list(self.ui.task_list.pack_slaves()),[self.ui.task_rows[k] for k in self.ui.task_order])

    def test_start_hands_reordered_queue_to_worker_and_keeps_daily_view(self):
        self.ui.selection['strong'].set(False)
        self.ui.move_task('hosting',-1)
        self.ui.preview.set(True)
        with patch.object(app.subprocess,'Popen') as launch,patch.object(app.threading,'Thread'):
            self.ui.start()
        launch.assert_called_once()
        cfg=json.loads((self.root/'run.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['tasks'],['survival','hosting','ranked','escort'])
        self.assertEqual(self.ui.notebook.select(),str(self.ui.task_panel))
        self.assertTrue(self.ui.running)
        self.ui.events.put({'kind':'exit','message':'0'})
        self.ui.drain()
        self.assertFalse(self.ui.running)

    def test_fast_drag_without_intermediate_motion_event(self):
        handle=self.ui.task_handles['escort']
        handle.event_generate('<ButtonPress-1>',x=10,y=10)
        handle.event_generate('<ButtonRelease-1>',x=10,y=self.ui.task_list.winfo_rooty()-handle.winfo_rooty()-10)
        self.assertEqual(self.ui.task_order[0],'escort')

    def test_click_cancel_boundaries_and_running_lock(self):
        order=list(self.ui.task_order)
        handle=self.ui.task_handles['survival']
        handle.event_generate('<ButtonPress-1>',x=10,y=10)
        handle.event_generate('<ButtonRelease-1>',x=10,y=10)
        self.ui.move_task('survival',-1)
        self.assertEqual(self.ui.task_order,order)
        handle.event_generate('<ButtonPress-1>',x=10,y=10)
        handle.event_generate('<B1-Motion>',x=10,y=120)
        self.ui.cancel_task_drag()
        self.assertEqual(self.ui.task_order,order)
        self.assertIsNone(self.ui.grab_current())
        self.ui.running=True;self.ui.update_sorting_state()
        self.ui.move_task('survival',1)
        handle.event_generate('<ButtonPress-1>',x=10,y=10)
        self.assertIsNone(self.ui.task_drag)
        self.assertEqual(self.ui.task_order,order)

    def test_load_filters_unknown_duplicate_order_and_migrates_old_config(self):
        path=self.root/'config.json'
        path.write_text(json.dumps({'tasks':['hosting','survival'],'taskOrder':['hosting','hosting',{},'unknown','survival']}),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order,['hosting','survival','strong','ranked','escort'])
        path.write_text(json.dumps({'tasks':['strong','survival']}),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.task_order[:2],['strong','survival'])

    def test_three_panes_resize_and_fixed_controls_fit(self):
        for geometry in ('940x680','1280x780','1500x900'):
            self.ui.geometry(geometry);self.ui.update()
            widths=[self.ui.nametowidget(p).winfo_width() for p in self.ui.panes.panes()]
            self.assertEqual(len(widths),3)
            self.assertGreaterEqual(widths[0],236)
            self.assertGreaterEqual(widths[1],330)
            self.assertGreaterEqual(widths[2],220)
            self.assertTrue(self.ui.log_text.winfo_ismapped())
            self.assertLess(self.ui.stop_button.winfo_rooty()+self.ui.stop_button.winfo_height(),self.ui.task_panel.winfo_rooty()+self.ui.task_panel.winfo_height())
            for task,_ in app.TASKS:
                self.ui.show_task(task,'advanced');self.ui.update()
                for frame,button in self.ui.task_tab_buttons.values():
                    self.assertTrue(button.winfo_ismapped())
            self.ui.show_task('survival')
        self.ui.panes.sashpos(0,400)
        self.ui.resizing_sash=True
        self.ui.end_pane_resize(SimpleNamespace())
        self.ui.update()
        self.assertGreater(self.ui.pane_ratios[0],0.25)

    def test_both_log_views_share_events_and_allow_reading_history(self):
        for n in range(100):self.ui.log('验证日志 '+str(n))
        self.ui.update()
        self.assertEqual(self.ui.log_views[0].get('1.0','end'),self.ui.log_views[1].get('1.0','end'))
        self.ui.follow_logs.set(False)
        self.ui.log_text.yview_moveto(0);self.ui.update()
        self.ui.log('新增事件');self.ui.update()
        self.assertEqual(self.ui.log_text.yview()[0],0)
        self.ui.follow_logs.set(True);self.ui.log('恢复跟随');self.ui.update()
        self.assertGreater(self.ui.log_text.yview()[1],0.99)
        self.assertTrue((self.root/'logs').exists())

    def test_ranked_scope_and_limit_controls_persist_and_reload(self):
        self.assertEqual((self.ui.config()['rankedServer'],self.ui.config()['rankedLimit']),('连服',0))
        self.ui.show_task('ranked','common');self.ui.update()
        self.ui.ranked_server.set('本服')
        self.ui.show_task('ranked','advanced');self.ui.update()
        self.assertEqual(str(self.ui.ranked_count_spin.cget('state')),'disabled')
        self.ui.ranked_all.set(False);self.ui.update_ranked_limit();self.ui.ranked_count.set(3)
        self.assertEqual(str(self.ui.ranked_count_spin.cget('state')),'normal')
        self.ui.save()
        self.ui.ranked_server.set('连服');self.ui.ranked_all.set(True);self.ui.load()
        self.assertEqual((self.ui.config()['rankedServer'],self.ui.config()['rankedLimit']),('本服',3))
        self.assertFalse(self.ui.ranked_all.get())

    def test_ranked_use_all_ignores_disabled_count_and_old_config_defaults(self):
        self.ui.ranked_count.set('invalid')
        self.assertEqual(self.ui.config()['rankedLimit'],0)
        (self.root/'config.json').write_text('{"tasks":["ranked"]}',encoding='utf-8')
        self.ui.load()
        self.assertEqual((self.ui.ranked_server.get(),self.ui.config()['rankedLimit']),('连服',0))
        self.ui.ranked_all.set(False);self.ui.ranked_count.set(0)
        with self.assertRaisesRegex(ValueError,'1至20'):self.ui.config()


if __name__=='__main__':unittest.main()
