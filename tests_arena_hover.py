"""Shared hover addition: virtual movement only, no real window IO."""
import ctypes
import unittest
from unittest.mock import Mock,patch
from adapters import background_window as background


class ArenaHoverTests(unittest.TestCase):
    def target(self,method):
        window=object.__new__(background.BackgroundWindow)
        window.target=123;window.geometry=(0,0,1920,1015,1920,1122);window.input_method=method
        window.check=Mock();window.measure=Mock(return_value=window.geometry)
        return window

    def test_hover_sends_only_move_and_restores_dpi_for_both_methods(self):
        for method in ('PostMessage','SendMessage'):
            with self.subTest(method=method):
                window=self.target(method);api=Mock()
                api.SetThreadDpiAwarenessContext.return_value=55
                def client(target,rect):rect._obj.right=960;rect._obj.bottom=507
                api.GetClientRect.side_effect=client
                with patch.object(background,'u',api):window.hover(1000,500)
                call=api.PostMessageW.call_args if method=='PostMessage' else api.SendMessageTimeoutW.call_args
                self.assertEqual(call.args[:3],(123,0x200,0))
                self.assertEqual(call.args[3],(249<<16)|500)
                self.assertEqual(api.SetThreadDpiAwarenessContext.call_args.args,(55,))
                self.assertEqual(api.PostMessageW.call_count+api.SendMessageTimeoutW.call_count,1)

    def test_geometry_change_and_outside_position_send_nothing(self):
        for reason in ('geometry','outside'):
            window=self.target('PostMessage');api=Mock()
            api.GetClientRect.side_effect=lambda target,rect:(setattr(rect._obj,'right',1920),setattr(rect._obj,'bottom',1015))
            if reason=='geometry':window.measure.return_value=(1,1,1920,1015,1920,1122)
            with patch.object(background,'u',api),self.assertRaises(RuntimeError):window.hover(9999 if reason=='outside' else 20,20)
            api.PostMessageW.assert_not_called();api.SendMessageTimeoutW.assert_not_called()


if __name__=='__main__':unittest.main()
