import unittest
from unittest.mock import Mock,patch
import adapters.background_window as module

class HoldTests(unittest.TestCase):
    def run_hold(self,mode):
        window=object.__new__(module.BackgroundWindow)
        window.check=Mock();window.target=1;window.input_method='SendMessage'
        window.geometry=(0,0,1920,1015,1920,1122)
        window.measure=Mock(return_value=window.geometry)
        if mode=='geometry':window.measure.side_effect=[window.geometry,(0,0,1000,1000,1000,1000)]
        messages=[]
        def send(target,message,*args):
            messages.append(message)
            return 0 if mode=='down_error' and message==0x201 else 1
        cancelled=Mock(side_effect=[False,True]) if mode=='cancel' else lambda:False
        with patch.object(module,'u') as u,patch.object(module,'client_to_message',return_value=(10,20)):
            u.SendMessageTimeoutW.side_effect=send
            if mode=='exception':window.check.side_effect=[None,RuntimeError('changed')]
            if mode in ('exception','down_error','geometry'):
                with self.assertRaises(RuntimeError):window.hold(10,20,.1,cancelled)
            else:self.assertEqual(window.hold(10,20,.1,cancelled),mode!='cancel')
            self.assertEqual(messages,[0x200,0x201,0x202])
            self.assertGreaterEqual(u.SetThreadDpiAwarenessContext.call_count,2)

    def test_geometry_compared_in_capture_dpi_context(self):
        window=object.__new__(module.BackgroundWindow)
        window.check=Mock();window.target=1;window.input_method='SendMessage'
        window.geometry=(0,0,1920,1015,1920,1122)
        state={'dpi':'capture'};messages=[]
        def context(value):
            old=state['dpi'];state['dpi']=value;return old
        def measure():
            return window.geometry if state['dpi']=='capture' else (0,0,1280,677,1280,748)
        window.measure=measure
        with patch.object(module,'u') as u,patch.object(module,'client_to_message',return_value=(10,20)):
            u.GetWindowDpiAwarenessContext.return_value='message'
            u.SetThreadDpiAwarenessContext.side_effect=context
            u.SendMessageTimeoutW.side_effect=lambda target,message,*args:messages.append(message) or 1
            self.assertTrue(window.hold(10,20,.1))
        self.assertEqual(state['dpi'],'capture')
        self.assertEqual(messages,[0x200,0x201,0x202])

    def test_normal_release(self):self.run_hold('normal')
    def test_cancel_release(self):self.run_hold('cancel')
    def test_exception_release(self):self.run_hold('exception')
    def test_real_geometry_change_releases_and_stops(self):self.run_hold('geometry')
    def test_uncertain_down_release(self):self.run_hold('down_error')
    def test_invalid_duration(self):
        window=object.__new__(module.BackgroundWindow)
        for value in (0,2,float('nan'),True):
            with self.assertRaises(ValueError):window.hold(1,2,value)
