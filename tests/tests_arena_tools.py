"""Verify actual arena tool widgets with isolated storage; no game worker."""
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT/'verification/arena-tools-20261106'
OUT.mkdir(exist_ok=True)
BASELINE = OUT/'before-application.json'
import app
import grocery_tool_ui
grocery_tool_ui.ROOT = PROJECT
from PIL import Image


def screenshot(ui,name):
    """Render this test window through PrintWindow, without focus or pointer input."""
    ui.update()
    user=ctypes.windll.user32;gdi=ctypes.windll.gdi32
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetWindowDC.argtypes=[wintypes.HWND];user.GetWindowDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ];gdi.SelectObject.restype=wintypes.HGDIOBJ
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ];gdi.DeleteDC.argtypes=[wintypes.HDC]
    hwnd=user.GetAncestor(ui.winfo_id(),2);rect=wintypes.RECT()
    if not user.GetWindowRect(hwnd,ctypes.byref(rect)):raise RuntimeError('Cannot read test window rectangle')
    width,height=rect.right-rect.left,rect.bottom-rect.top
    dc=user.GetWindowDC(hwnd);mem=gdi.CreateCompatibleDC(dc);bitmap=gdi.CreateCompatibleBitmap(dc,width,height)
    old=gdi.SelectObject(mem,bitmap)
    try:
        if not user.PrintWindow(hwnd,mem,2):raise RuntimeError('PrintWindow failed for test app')
        header=ctypes.create_string_buffer(struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,width*height*4,0,0,0,0))
        buffer=ctypes.create_string_buffer(width*height*4)
        rows=gdi.GetDIBits(mem,bitmap,0,height,buffer,header,0)
        if rows!=height:raise RuntimeError('Incomplete test screenshot')
        image=Image.frombuffer('RGB',(width,height),buffer.raw,'raw','BGRX',0,1)
        if max(high-low for low,high in image.getextrema())<20:raise RuntimeError('Blank screenshot')
        image.save(OUT/name)
    finally:
        gdi.SelectObject(mem,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(mem);user.ReleaseDC(hwnd,dc)


class ArenaToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arena-tool-',dir=OUT)
        self.root=Path(self.temp.name)
        self.patches=[patch.object(app,'ROOT',self.root),patch.object(app,'game_windows',return_value=[])]
        for item in self.patches:item.start()
        self.ui=app.App();self.ui.update()
        self.view=self.ui.arena_view

    def tearDown(self):
        for timer in self.ui.tk.call('after','info'):self.ui.after_cancel(timer)
        self.ui.destroy()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def children(self,parent):
        for child in parent.winfo_children():
            yield child
            yield from self.children(child)

    def test_daily_queue_excludes_arena_and_tool_navigation_displays_it(self):
        self.assertNotIn('arena',self.ui.task_order)
        self.assertNotIn('arena',self.ui.task_rows)
        self.ui.select_all(True)
        self.assertNotIn('arena',self.ui.config()['tasks'])
        self.ui.notebook.select(self.ui.help_panel)
        self.ui.grocery_view.tool_buttons['arena'].invoke();self.ui.update()
        self.assertEqual(self.ui.grocery_view.selected_tool,'arena')
        self.assertTrue(self.view.winfo_ismapped())
        self.assertFalse(self.ui.grocery_view.footer.winfo_ismapped())
        for key in ('grocery','shortcuts'):
            self.ui.grocery_view.tool_buttons[key].invoke();self.ui.update()
            self.assertEqual(self.ui.grocery_view.selected_tool,key)
            self.assertTrue(self.ui.grocery_view.footer.winfo_ismapped())
        self.assertFalse((self.root/'config.json').exists())

    def test_three_modes_count_save_and_reload_still_work(self):
        self.ui.show_task('arena','common');self.ui.update()
        self.assertEqual(self.ui.notebook.select(),str(self.ui.help_panel))
        radios=[w for w in self.children(self.view.task_fields) if w.winfo_class()=='TRadiobutton']
        self.assertEqual(len(radios),3)
        for radio,mode in zip(radios,('段位战斗','休闲战斗','日常模式')):
            radio.invoke();self.ui.arena_limit.set('7');self.view.save_button.invoke()
            self.ui.arena_mode.set('休闲战斗');self.ui.arena_limit.set('1');self.ui.load()
            self.assertEqual(self.ui.arena_mode.get(),mode)
            self.assertEqual(self.ui.arena_limit.get(),'7')
            self.assertNotIn('arena',self.ui.config()['tasks'])
        for mode in ('advanced','common'):
            self.view.show_mode(mode);self.ui.update()
            self.assertEqual(self.view.mode,mode)

    def test_legacy_arena_selection_migrates_out_of_daily_without_losing_settings(self):
        (self.root/'config.json').write_text(json.dumps({'tasks':['ranked','arena'],'taskOrder':['ranked','arena'],
                                                       'arenaMode':'日常模式','arenaBattleLimit':11}),encoding='utf-8')
        self.ui.load()
        self.assertEqual(self.ui.config()['tasks'],['ranked'])
        self.assertNotIn('arena',self.ui.task_order)
        self.assertEqual(self.ui.arena_mode.get(),'日常模式')
        self.assertEqual(self.ui.arena_limit.get(),'11')

    def test_tool_start_sends_only_arena_and_keeps_tools_page(self):
        self.ui.show_task('arena');self.ui.preview.set(True)
        self.ui.arena_mode.set('日常模式');self.ui.arena_limit.set('4')
        with patch.object(app.subprocess,'Popen') as process,patch.object(app.threading,'Thread'),\
             patch.object(app.messagebox,'showerror',side_effect=AssertionError):
            self.view.start_button.invoke()
            process.assert_called_once()
        cfg=json.loads((self.root/'run.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['tasks'],['arena'])
        self.assertEqual(cfg['arenaMode'],'日常模式')
        self.assertEqual(cfg['arenaBattleLimit'],4)
        self.assertNotIn('arena',json.loads((self.root/'config.json').read_text(encoding='utf-8'))['tasks'])
        self.assertEqual(self.ui.notebook.select(),str(self.ui.help_panel))
        for command,expected in ((self.view.pause_button,'pause'),(self.view.stop_button,'stop')):
            self.view._sync_controls()
            with patch.object(self.ui,'send') as send,patch.object(app.threading,'Thread'):
                command.invoke();send.assert_called_with(expected)

    def test_invalid_tool_limit_rejected_but_daily_config_remains_usable(self):
        for bad in ('0','101','2.5','abc',''):
            self.ui.arena_limit.set(bad)
            self.assertNotIn('arena',self.ui.config()['tasks'])
            with patch.object(app.messagebox,'showerror') as error,patch.object(app.subprocess,'Popen') as process:
                self.view.save_button.invoke();self.ui.start(arena_only=True)
                self.assertGreaterEqual(error.call_count,2);process.assert_not_called()
            self.assertFalse((self.root/'run.json').exists())

    def test_tool_controls_fit_and_native_screenshots_are_saved(self):
        self.ui.geometry('1440x900');self.ui.update()
        screenshot(self.ui,'daily.png')
        self.ui.show_task('arena');self.ui.update()
        screenshot(self.ui,'arena-tools.png')
        for size in ('940x680','1060x720','1440x900'):
            self.ui.geometry(size);self.ui.update()
            self.assertTrue(self.view.start_button.winfo_ismapped())
            self.assertGreater(self.view.start_button.winfo_width(),70)
            self.assertGreater(self.view.task_canvas.winfo_height(),100)
            self.assertGreaterEqual(self.view.start_button.winfo_rootx(),self.view.winfo_rootx())
            self.assertLessEqual(self.view.start_button.winfo_rootx()+self.view.start_button.winfo_width(),
                                 self.view.winfo_rootx()+self.view.winfo_width())
        self.ui.geometry('940x680');self.ui.update()
        self.view.task_fields.event_generate('<MouseWheel>',delta=-720);self.ui.update()
        self.assertGreater(self.view.task_canvas.yview()[0],0)
        spins=[w for w in self.children(self.view.task_fields) if w.winfo_class()=='TSpinbox']
        self.assertEqual(len(spins),1)
        self.assertLess(spins[0].winfo_rooty(),self.view.task_canvas.winfo_rooty()+self.view.task_canvas.winfo_height())
        screenshot(self.ui,'arena-tools-compact.png')


if __name__=='__main__':
    protected=json.loads(BASELINE.read_text(encoding='utf-8'))
    before={p:hashlib.sha256((PROJECT/p).read_bytes()).hexdigest() for p in protected}
    output=io.StringIO();start=time.monotonic()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ArenaToolTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(['tests_arena','tests_arena_daily','tests_arena_tokens','tests_arena_hover','tests_arena_ui','tests_arena_count_ui','tests_arena_popups','tests_grocery_tool_ui']))
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    after={p:hashlib.sha256((PROJECT/p).read_bytes()).hexdigest() for p in before}
    changed=[p for p in before if before[p]!=after[p]]
    report=dict(scope='正式竞技场工具入口及独立启动',applied=True,authorizedSharedFiles=['app.py','grocery_tool_ui.py'],tests=result.testsRun,
                failures=len(result.failures),errors=len(result.errors),seconds=round(time.monotonic()-start,3),
                gameInputs=0,gameWorkersLaunched=0,protectedFiles=len(before),changedProtectedFiles=changed,
                screenshots=['daily.png','arena-tools.png','arena-tools-compact.png'],
                limitations=['使用正式源码及隔离存储验证；未运行竞技场实机业务'])
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'verification.txt').write_text(output.getvalue(),encoding='utf-8')
    print(output.getvalue());print(json.dumps(report,ensure_ascii=True))
    sys.exit(0 if result.wasSuccessful() and not changed else 1)
