"""Mock-only safety checks for the unapplied cursor-hover review proposal."""
import ctypes
from ctypes import wintypes as W
from contextlib import contextmanager
from pathlib import Path
import textwrap
import unittest
from unittest.mock import Mock
from adapters.background_window import client_to_message

ROOT=Path(__file__).resolve().parents[1]


class CursorProposalTests(unittest.TestCase):
    def setup_target(self):
        api=Mock();position=[10,20];moves=[]
        def cursor(p):p._obj.x,p._obj.y=position;return True
        def move(x,y):position[:]=[x,y];moves.append((x,y));return True
        def origin(h,p):p._obj.x,p._obj.y=100,200;return True
        api.GetCursorPos.side_effect=cursor;api.SetCursorPos.side_effect=move
        api.ClientToScreen.side_effect=origin;api.SetThreadDpiAwarenessContext.return_value=55
        namespace=dict(ctypes=ctypes,W=W,u=api,client_to_message=client_to_message,contextmanager=contextmanager)
        source=(ROOT/'verification/arena-cursor-hover-proposed-method-20261020.txt').read_text(encoding='utf-8')
        exec(compile(textwrap.dedent(source),'<reviewed cursor proposal>','exec'),namespace)
        class Target:cursor_hover=namespace['cursor_hover']
        target=Target();target.target=123;target.geometry=(0,0,1920,1015,1920,1122)
        target.check=Mock();target.measure=Mock(return_value=target.geometry);target.hover=Mock()
        return target,api,position,moves

    def test_normal_exit_restores_cursor_and_dpi_without_button_messages(self):
        target,api,pos,moves=self.setup_target()
        with target.cursor_hover(271,506) as guard:
            self.assertTrue(guard());self.assertEqual(pos,[371,706])
        self.assertEqual(moves,[(371,706),(10,20)])
        self.assertEqual(api.SetThreadDpiAwarenessContext.call_args.args,(55,))
        api.SendMessageTimeoutW.assert_not_called();api.PostMessageW.assert_not_called()
        target.hover.assert_called_once_with(271,506)

    def test_capture_or_hover_error_restores_cursor(self):
        for failed_hover in (False,True):
            target,api,pos,moves=self.setup_target()
            if failed_hover:target.hover.side_effect=RuntimeError('send unknown')
            with self.assertRaises(RuntimeError):
                with target.cursor_hover(271,506):raise RuntimeError('capture failed')
            self.assertEqual(pos,[10,20]);self.assertEqual(len(moves),2)

    def test_user_movement_invalidates_guard_and_is_preserved(self):
        target,api,pos,moves=self.setup_target()
        with target.cursor_hover(271,506) as guard:
            pos[:]=[800,900];self.assertFalse(guard())
        self.assertEqual(pos,[800,900]);self.assertEqual(moves,[(371,706)])

    def test_invalid_geometry_or_position_never_moves_mouse(self):
        for reason in ('geometry','position'):
            target,api,pos,moves=self.setup_target()
            if reason=='geometry':target.measure.return_value=(1,0,1920,1015,1920,1122)
            with self.assertRaises(RuntimeError):
                with target.cursor_hover(9999 if reason=='position' else 271,506):pass
            self.assertEqual(moves,[]);target.hover.assert_not_called()


if __name__=='__main__':unittest.main()
