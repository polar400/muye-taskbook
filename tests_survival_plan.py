import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import tests_local
from survival_plan import survival_plan, estimate, GRADES


class PlanTests(unittest.TestCase):
    def test_estimates_full_partial_and_overflow(self):
        self.assertEqual(estimate({'survivalGrades':['SS','A'], 'survivalCounts':{'SS':1,'A':2}}), (160,220,0))
        self.assertEqual(estimate({'survivalGrades':['S'], 'survivalCounts':{'S':2}}), (120,180,40))
        self.assertEqual(estimate({'survivalGrades':['SS','S'], 'survivalCounts':{'SS':1,'S':2}}), (200,220,0))

    def test_invalid_plan_rejected_and_legacy_keeps_all_grades(self):
        self.assertEqual(survival_plan({}), (list(GRADES),None))
        for cfg in [{'survivalGrades':[]}, {'survivalGrades':['D']}, {'survivalGrades':['S','S']},
                    {'survivalGrades':['SS'],'survivalCounts':{'SS':2}},
                    {'survivalGrades':['S'],'survivalCounts':{'S':0}},
                    {'survivalGrades':['S'],'survivalCounts':{'S':True}}]:
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):survival_plan(cfg)

    def test_only_selected_s_is_read_even_if_ss_is_available(self):
        import numpy as np
        flow=tests_local.LocalTests().reset_flow('')
        flow.cfg={'survivalGrades':['S'], 'survivalCounts':{'S':2}}
        flow.image=np.zeros((990,1894,3),dtype=np.uint8)
        flow.ocr.read.return_value=[{'text':'2'}]
        self.assertEqual(flow.survival_candidate(), ('S',2,1370,227))
        flow.ocr.read.assert_called_once()

    def test_reached_limit_skips_ss_and_exhausted_plan_stops(self):
        import numpy as np
        flow=tests_local.LocalTests().reset_flow('')
        flow.cfg={'survivalGrades':['SS','A'], 'survivalCounts':{'SS':1,'A':2}}
        flow._survival_used={'SS':1}
        flow.image=np.zeros((990,1894,3),dtype=np.uint8)
        flow.ocr.read.return_value=[{'text':'2'}]
        self.assertEqual(flow.survival_candidate()[0], 'A')
        flow._survival_used['A']=2
        with self.assertRaisesRegex(RuntimeError,'所选等级.*积分未满'):flow.survival_candidate()


class TaskSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='settings-test-',dir=Path(__file__).resolve().parent/'verification')
        self.root_patch=patch.object(app,'ROOT',Path(self.temp.name));self.root_patch.start()
        self.refresh_patch=patch.object(app.App,'refresh_windows');self.refresh_patch.start()
        self.error_patch=patch.object(app.messagebox,'showerror',side_effect=lambda title,message:(_ for _ in ()).throw(AssertionError(title+': '+message)));self.error_patch.start()
        self.ui=app.App();self.ui.withdraw()

    def tearDown(self):
        for callback in self.ui.tk.call('after','info'):self.ui.after_cancel(callback)
        assert Path(self.temp.name).resolve().parent == (Path(__file__).resolve().parent/'verification').resolve()
        self.ui.destroy();self.error_patch.stop();self.refresh_patch.stop();self.root_patch.stop();self.temp.cleanup()

    def test_advanced_stays_in_task_and_preserves_choices_across_tabs(self):
        for key,_ in app.TASKS:
            self.ui.show_task(key,'advanced');self.ui.update_idletasks()
            self.assertEqual(self.ui.notebook.select(),str(self.ui.task_panel))
            self.assertEqual(self.ui.selected.get(),key)
        self.ui.show_task('survival','advanced')
        self.ui.survival_grades['SS'].set(False)
        self.ui.survival_counts['S'].set(1)
        self.ui.show_task('survival','common');self.ui.show_task('survival','advanced')
        self.assertFalse(self.ui.survival_grades['SS'].get())
        self.assertEqual(self.ui.survival_counts['S'].get(),1)
        self.assertIn('S → A',self.ui.survival_summary.get())
        self.assertEqual(self.ui.task_tab_buttons['advanced'][1].cget('fg'),app.BLUE)

    def test_selected_plan_saved_reloaded_and_summary_updates(self):
        for g in GRADES:self.ui.survival_grades[g].set(g in ('SS','A'))
        self.ui.survival_counts['A'].set(2)
        self.ui.save()
        cfg=json.loads((Path(self.temp.name)/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['survivalGrades'],['SS','A'])
        self.assertEqual(cfg['survivalCounts'],{'SS':1,'A':2})
        self.assertIn('220/220',self.ui.survival_summary.get())
        self.ui.survival_grades['SS'].set(False)
        self.ui.load()
        self.assertTrue(self.ui.survival_grades['SS'].get())
        self.assertEqual(self.ui.config()['survivalCounts'],{'SS':1,'A':2})

    def test_empty_survival_plan_can_be_saved_when_only_other_task_is_selected(self):
        for key,var in self.ui.selection.items():var.set(key=='strong')
        for var in self.ui.survival_grades.values():var.set(False)
        self.ui.difficulty.set('夜叉级');self.ui.save()
        self.ui.difficulty.set('天级');self.ui.load()
        self.assertEqual(self.ui.difficulty.get(),'夜叉级')
        self.assertEqual(self.ui.config()['tasks'],['strong'])
        self.assertEqual(self.ui.config()['survivalGrades'],[])


if __name__=='__main__':unittest.main()
