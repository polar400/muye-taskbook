"""Actual arena tool settings with isolated storage; no game input."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app

ROOT=Path(__file__).resolve().parents[1]


class ArenaCountUITests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='arena-count-ui-',dir=ROOT/'verification')
        self.root=Path(self.folder.name)
        module=app
        self.module=module;self.patches=[patch.object(module,'ROOT',self.root),patch.object(module,'game_windows',return_value=[])]
        for item in self.patches:item.start()
        self.app=module.App();self.app.select_all(False);self.app.selection['arena'].set(True)
        self.app.show_task('arena','common');self.app.update()

    def tearDown(self):
        for timer in self.app.tk.call('after','info'):self.app.after_cancel(timer)
        self.app.destroy()
        for item in reversed(self.patches):item.stop()
        self.folder.cleanup()

    def children(self,parent):
        for child in parent.winfo_children():
            yield child
            yield from self.children(child)

    def test_three_modes_share_one_labeled_count_and_save_reload(self):
        radios=[w for w in self.children(self.app.arena_view.task_fields) if w.winfo_class()=='TRadiobutton']
        self.assertEqual(len(radios),3);self.assertEqual(self.app.config()['arenaBattleLimit'],3)
        for radio,mode in zip(radios,('段位战斗','休闲战斗','日常模式')):
            radio.invoke();self.app.arena_limit.set(7);self.app.save()
            self.app.arena_limit.set(1);self.app.load()
            self.assertEqual(self.app.config()['arenaMode'],mode)
            self.assertEqual(self.app.config()['arenaBattleLimit'],7)
        labels=' '.join(str(w.cget('text')) for w in self.children(self.app.arena_view.task_fields) if w.winfo_class()=='TLabel')
        self.assertIn('战斗场数上限',labels);self.assertIn('人工处理',labels)
        self.assertNotIn('先降低',labels)

    def test_old_config_defaults_to_three_and_invalid_count_cannot_launch_or_save(self):
        (self.root/'config.json').write_text(json.dumps(dict(tasks=['arena'],arenaMode='日常模式')),encoding='utf-8')
        self.app.arena_limit.set(9);self.app.load()
        self.assertEqual(self.app.config()['arenaBattleLimit'],3)
        previous=(self.root/'config.json').read_bytes()
        for value in (0,101,'','2.5','abc'):
            self.app.arena_limit.set(value)
            with patch.object(self.module.messagebox,'showerror') as error,patch.object(self.module.subprocess,'Popen') as process:
                self.app.arena_view.save();self.assertTrue(error.called)
                self.app.start(arena_only=True);process.assert_not_called()
            self.assertEqual((self.root/'config.json').read_bytes(),previous)
            self.assertFalse((self.root/'run.json').exists())

    def test_invalid_arena_count_does_not_block_another_task(self):
        self.app.selection['arena'].set(False);self.app.selection['ranked'].set(True)
        self.app.arena_limit.set('invalid')
        self.assertEqual(self.app.config()['tasks'],['ranked'])
        self.assertEqual(self.app.config()['arenaBattleLimit'],3)

    def test_count_control_fits_supported_widths(self):
        for size in ('1060x720','1240x820','1500x960'):
            self.app.geometry(size);self.app.update()
            spins=[w for w in self.children(self.app.arena_view.task_fields) if w.winfo_class()=='TSpinbox']
            self.assertEqual(len(spins),1)
            spin=spins[0]
            self.assertGreaterEqual(spin.winfo_width(),60)
            self.assertLessEqual(spin.winfo_rootx()+spin.winfo_width(),
                                 self.app.arena_view.task_canvas.winfo_rootx()+self.app.arena_view.task_canvas.winfo_width())


if __name__=='__main__':unittest.main()
