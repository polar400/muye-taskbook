import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from adapters.background_window import client_to_message,BackgroundWindow
from local_flows import remaining,select_opponent,normalized,LocalFlows

class LocalTests(unittest.TestCase):
    def test_dpi_conversion(self):
        self.assertEqual(client_to_message(1030,146,(1894,990),(1263,660)),(686,97))
        self.assertEqual(client_to_message(1858,42,(1894,990),(1263,660)),(1238,28))
        for x,y in [(-1,0),(1894,0),(0,990)]:
            with self.assertRaises(RuntimeError):client_to_message(x,y,(1894,990),(1263,660))
    def test_minimize_blocks_before_capture_or_input(self):
        w=object.__new__(BackgroundWindow);w.root=42
        with patch('adapters.background_window.u.IsWindow',return_value=True),patch('adapters.background_window.u.IsIconic',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'最小化'):w.capture()
            with self.assertRaisesRegex(RuntimeError,'最小化'):w.click(10,10)

    def test_startup_resizes_game_without_activation(self):
        import numpy as np
        w=object.__new__(BackgroundWindow);w.root=42;w.check=Mock()
        w.calibration_bounds=Mock(return_value=(0,0,2560,1440))
        w.measure=Mock(side_effect=[(0,106,1869,964,1894,1098),(0,107,1920,1015,1920,1122),(0,107,1920,1015,1920,1122)])
        w.capture=Mock(return_value=np.zeros((1015,1920,3),dtype=np.uint8))
        def rect(hwnd,p):p._obj.left=10;p._obj.top=20;return True
        with patch('adapters.background_window.u.IsZoomed',return_value=False),patch('adapters.background_window.u.GetWindowRect',side_effect=rect),patch('adapters.background_window.u.SetWindowPos',return_value=True) as resize,patch('adapters.background_window.time.sleep'):
            image=w.calibrate()
        resize.assert_called_once_with(42,None,320,146,1920,1147,0x14)
        self.assertEqual(image.shape[:2],(1015,1920))

    def test_startup_stops_if_game_refuses_resize(self):
        w=object.__new__(BackgroundWindow);w.root=42;w.check=Mock()
        w.calibration_bounds=Mock(return_value=(0,0,2560,1440))
        w.measure=Mock(return_value=(0,106,1869,964,1894,1098));w.capture=Mock()
        with patch('adapters.background_window.u.IsZoomed',return_value=False),patch('adapters.background_window.u.GetWindowRect',return_value=True),patch('adapters.background_window.u.SetWindowPos',return_value=True),patch('adapters.background_window.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'停止后续任务'):w.calibrate()
        w.capture.assert_not_called()
    def test_center_handles_secondary_monitor_taskbar_and_oversize(self):
        from adapters.background_window import centered_window_position
        self.assertEqual(centered_window_position((-2560,40,0,1440),(1920,1122)),(-2240,179))
        self.assertEqual(centered_window_position((0,0,1920,1080),(1946,1147)),(-13,-34))

    def test_logged_1894_canvas_is_corrected_and_centered(self):
        import numpy as np
        w=object.__new__(BackgroundWindow);w.root=42;w.check=Mock()
        w.calibration_bounds=Mock(return_value=(0,0,2560,1440))
        w.measure=Mock(side_effect=[(13,132,1894,990,1920,1122),
                                   (13,132,1920,1015,1946,1147),(13,132,1920,1015,1946,1147)])
        w.capture=Mock(return_value=np.zeros((1015,1920,3),dtype=np.uint8))
        with patch('adapters.background_window.u.IsZoomed',return_value=False),patch('adapters.background_window.u.SetWindowPos',return_value=True) as resize,patch('adapters.background_window.time.sleep'):
            w.calibrate()
        resize.assert_called_once_with(42,None,320,146,1920,1147,0x14)

    def test_responsive_border_jump_converges_without_repeating_outer_sizes(self):
        import numpy as np
        w=object.__new__(BackgroundWindow);w.root=42;w.target=43;w.check=Mock()
        w.calibration_bounds=Mock(return_value=(0,0,2560,1528))
        outer=[1922,1122];client=[1896,990];requests=[]
        def measure():return (0,106,*client,*outer)
        def resize(hwnd,z,x,y,width,height,flags):
            self.assertEqual(hwnd,42)  # No child-window clipping workaround.
            requests.append((width,height))
            outer[:]=[(width+1)//2*2,height]
            if (width,height)==(1920,1147):
                client[:]=[1920,1015];return True
            if height<=1122:bw,bh=26,132
            elif outer[0]>=1946:bw,bh=1,106
            else:bw,bh=2,132  # independent axes allow the narrow/tall viewport
            client[:]=[outer[0]-bw,outer[1]-bh]
            return True
        w.measure=measure;w.capture=Mock(return_value=np.zeros((1015,1920,3),dtype=np.uint8))
        with patch('adapters.background_window.u.IsZoomed',return_value=False),patch('adapters.background_window.u.SetWindowPos',side_effect=resize),patch('adapters.background_window.time.sleep'):
            w.calibrate()
        self.assertEqual(measure()[2:4],(1920,1015))
        self.assertEqual(len(requests),len(set(requests)))
        self.assertLessEqual(len(requests),12)

    def test_counts_require_consistent_ocr(self):
        self.assertEqual(remaining([{'text':'今日剩余完成次数；3/3'}],r'今日剩余完成次数:?(\d+)/3'),3)
        with self.assertRaises(RuntimeError):remaining([{'text':'剩余挑战次数:1'},{'text':'剩余挑战次数:2'}],r'剩余挑战次数:?(\d+)')
        with self.assertRaises(RuntimeError):remaining([],r'(\d+)')
    def test_nearest_matching_power(self):
        self.assertEqual(select_opponent(100,[{'power':105},{'power':150}],20)['power'],105)
        with self.assertRaises(RuntimeError):select_opponent(0,[],20)

    def reset_flow(self,text,templates=()):
        flow=LocalFlows(Mock(),Mock(),{'reset':True},lambda:None,Mock())
        flow.image=SimpleNamespace(shape=(990,1894,3))
        flow.items=[{'text':text,'box':[974,910,170,27]}]
        flow.ocr.match.side_effect=lambda image,name,**kwargs:list(templates) if name=='survival_reset1' else []
        return flow

    def test_reset_digit_misread_uses_verified_button(self):
        button={'box':[962,901,188,43]}
        flow=self.reset_flow('重置（剩余]次)',[button])
        self.assertEqual(flow.survival_reset_state(),(1,button))

    def test_reset_zero_and_unknown_are_distinct(self):
        self.assertEqual(self.reset_flow('重置（剩余0次)').survival_reset_state()[0],0)
        self.assertEqual(self.reset_flow('重置（余0次)').survival_reset_state()[0],0)
        with self.assertRaisesRegex(RuntimeError,'重置次数'):
            self.reset_flow('重置（剩余]次)').survival_reset_state()
        with self.assertRaises(RuntimeError):
            self.reset_flow('重置（剩余0次)',[{'box':[962,901,188,43]}]).survival_reset_state()

    def test_reset_requires_zero_after_click(self):
        flow=self.reset_flow('重置（剩余1次)')
        flow.click_item=Mock();flow.observe=Mock()
        def wait(predicate):
            self.assertFalse(predicate())
            flow.items=[{'text':'重置（剩余0次)','box':[974,910,170,27]}]
            self.assertTrue(predicate())
        flow.wait=wait;flow.survival_reset()
        flow.click_item.assert_called_once()

    def test_full_points_do_not_bypass_reset_check(self):
        flow=self.reset_flow('演习积分:220/220')
        flow.observe=Mock();flow.enter=Mock();flow.wait_text=Mock()
        flow.wait_survival_ready=Mock()
        flow.survival_reset=Mock(side_effect=RuntimeError('reset checked first'))
        with self.assertRaisesRegex(RuntimeError,'reset checked first'):flow.survival()
        self.assertFalse(any(call.args[1]=='claimed' for call in flow.ocr.match.call_args_list))

    def test_survival_resumes_from_settlement_before_reset_check(self):
        flow=self.reset_flow('')
        flow.observe=Mock();flow.enter=Mock();flow.battle_settlement=Mock(return_value=True)
        flow.wait_survival_ready=Mock()
        flow.confirm=Mock();flow.wait_text=Mock()
        flow.survival_reset=Mock(side_effect=RuntimeError('reset checked'))
        with self.assertRaisesRegex(RuntimeError,'reset checked'):flow.survival()
        flow.confirm.assert_called_once();flow.wait_text.assert_called_once_with('演习积分')
        flow.enter.assert_not_called()

    def test_entry_waits_through_cached_zero_until_reset_one(self):
        flow=self.reset_flow('')
        flow.survival_points=Mock(return_value=(220,220))
        flow.survival_reset_state=Mock(side_effect=[(0,{}),(0,{}),(1,{}),(1,{})])
        def wait(predicate,seconds):
            for expected in (False,False,False,True):self.assertEqual(predicate(),expected)
        flow.wait=wait
        with patch('local_flows.time.monotonic',side_effect=[0,1,2,3]):flow.wait_survival_ready()
        flow.window.click.assert_not_called()

    def test_zero_reset_must_remain_stable_before_proceeding(self):
        flow=self.reset_flow('');flow.survival_points=Mock(return_value=(220,220))
        flow.survival_reset_state=Mock(return_value=(0,{}))
        def wait(predicate,seconds):
            for expected in (False,False,False,True):self.assertEqual(predicate(),expected)
        flow.wait=wait
        with patch('local_flows.time.monotonic',side_effect=[0,1,2,3]):flow.wait_survival_ready()

    def test_incomplete_panel_is_retried_before_reset_decision(self):
        flow=self.reset_flow('');flow.survival_points=Mock(return_value=(220,220))
        flow.survival_reset_state=Mock(side_effect=[RuntimeError('not loaded'),(1,{}),(1,{})])
        def wait(predicate,seconds):
            for expected in (False,False,True):self.assertEqual(predicate(),expected)
        flow.wait=wait
        with patch('local_flows.time.monotonic',side_effect=[0,1]):flow.wait_survival_ready()

    def test_full_points_rechecks_reset_before_reporting_done(self):
        flow=self.reset_flow('演习积分:220/220')
        flow.observe=Mock();flow.wait_survival_ready=Mock()
        flow.survival_points=Mock(return_value=(220,220))
        flow.survival_reset_state=Mock(return_value=(1,{}))
        flow.survival_reset=Mock(side_effect=[None,RuntimeError('late reset path')])
        with self.assertRaisesRegex(RuntimeError,'late reset path'):flow.survival()
        self.assertEqual(flow.survival_reset.call_count,2)
        self.assertFalse(any(call.args[1]=='claimed' for call in flow.ocr.match.call_args_list))

    def test_survival_prioritizes_ss_without_reading_lower_tiers(self):
        import numpy as np
        flow=self.reset_flow('')
        flow.image=np.zeros((990,1894,3),dtype=np.uint8)
        flow.ocr.read.side_effect=[[{'text':'1'}],RuntimeError('lower tier should not be read')]
        self.assertEqual(flow.survival_candidate()[0],'SS')
        flow.ocr.read.assert_called_once()

    def test_survival_uses_s_when_ss_is_exhausted(self):
        import numpy as np
        flow=self.reset_flow('')
        flow.image=np.zeros((990,1894,3),dtype=np.uint8)
        flow.ocr.read.side_effect=[[{'text':'0'}],[{'text':'2'}]]
        self.assertEqual(flow.survival_candidate()[0],'S')

    def battle_flow(self,states):
        import numpy as np
        flow=self.reset_flow('');frame=np.zeros((990,1894,3),dtype=np.uint8)
        state={'index':-1}
        def capture():state['index']+=1;return frame
        def match(image,name,**kwargs):
            box=[1620,120,30,30] if name=='speed1' else [1500,100,80,80]
            return [{'box':box}] if name in states[state['index']] else []
        flow.window.capture.side_effect=capture
        flow.ocr.match.side_effect=match;flow.ocr.read.return_value=[]
        return flow

    def test_auto_waits_for_loading_then_enables_once(self):
        flow=self.battle_flow([set(),{'auto_off'},{'auto_off'},{'auto_on','speed2'}])
        with patch('local_flows.time.sleep'),patch('local_flows.time.monotonic',side_effect=range(100)):
            flow.auto()
        self.assertEqual(flow.window.capture.call_count,4)
        flow.window.click.assert_called_once_with(1540,783)

    def test_auto_already_enabled_does_not_toggle_it_off(self):
        flow=self.battle_flow([{'auto_on','speed2'}])
        flow.auto()
        flow.window.click.assert_not_called()

    def test_auto_and_speed_click_in_same_frame(self):
        flow=self.battle_flow([{'auto_off','speed1'},{'auto_on','speed2'}])
        flow.auto()
        names=[call[0] for call in flow.window.method_calls]
        self.assertEqual(names[:4],['capture','click','click','capture'])
        self.assertEqual(flow.window.click.call_count,2)

    def test_real_settlement_skips_controls_and_confirms(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        frame=np.array(Image.open(Path(__file__).resolve().parents[1]/'resources/local/battle-settlement-calibration.png').convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),LocalOCR(),{},lambda:None,Mock())
        flow.window.capture.return_value=frame;flow.confirm=Mock()
        self.assertTrue(flow.battle())
        flow.confirm.assert_called_once();flow.window.click.assert_not_called()

    def test_actual_claim_dialog_recovers_missing_yes(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        frame=np.array(Image.open(Path(__file__).resolve().parents[1]/'resources/local/survival-claim-confirm-calibration.png').convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),LocalOCR(),{},lambda:None,Mock())
        flow.window.capture.return_value=frame
        with patch('local_flows.time.sleep'):flow.confirm()
        x,y=flow.window.click.call_args.args
        self.assertTrue(760<x<905 and 525<y<575)

    def test_paid_prompt_blocks_confirmation(self):
        flow=self.reset_flow('支付100元宝')
        flow.observe=Mock()
        with self.assertRaisesRegex(RuntimeError,'付费'):flow.confirm()
        flow.window.click.assert_not_called()

    def test_survival_resumes_pending_claim_without_claiming_twice(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        base=Path(__file__).resolve().parents[1]/'resources/local'
        frames=[np.array(Image.open(base/name).convert('RGB'))[:,:,::-1].copy()
                for name in ('survival-claim-confirm-calibration.png','survival-calibration.png')]
        flow=LocalFlows(Mock(),LocalOCR(),{'reset':False},lambda:None,Mock())
        state={'confirmed':False}
        flow.window.capture.side_effect=lambda:frames[int(state['confirmed'])]
        flow.window.click.side_effect=lambda x,y:state.update(confirmed=True)
        flow.close_panel=Mock()
        with patch('local_flows.time.sleep'):flow.survival()
        flow.window.click.assert_called_once();flow.close_panel.assert_called_once()

    def test_reward_overlay_is_confirmed_before_completion(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        base=Path(__file__).resolve().parents[1]/'resources/local'
        frames=[np.array(Image.open(base/name).convert('RGB'))[:,:,::-1].copy()
                for name in ('survival-reward-popup-calibration.png','survival-calibration.png')]
        flow=LocalFlows(Mock(),LocalOCR(),{'reset':False},lambda:None,Mock())
        state={'confirmed':False}
        flow.window.capture.side_effect=lambda:frames[int(state['confirmed'])]
        flow.window.click.side_effect=lambda x,y:state.update(confirmed=True)
        flow.close_panel=Mock()
        with patch('local_flows.time.sleep'):flow.survival()
        flow.window.click.assert_called_once()
        x,y=flow.window.click.call_args.args
        self.assertTrue(870<x<1020 and 660<y<715)
        flow.close_panel.assert_called_once()

    def test_auto_enables_double_speed_after_confirming_active(self):
        flow=self.battle_flow([{'auto_on'},{'auto_on','speed2'}])
        flow.ocr.read.return_value=[{'text':'×1','box':[1620,120,30,30]}]
        flow.auto()
        flow.window.click.assert_called_once_with(1635,778)

    def test_saved_1920_panel_reads_points_and_selects_s(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        ocr=LocalOCR();flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock())
        for name in ('survival-1920-calibration.png','survival-1920-shifted-calibration.png'):
            with self.subTest(screenshot=name):
                image=Path(__file__).resolve().parents[1]/'resources/local'/name
                flow.image=np.array(Image.open(image).convert('RGB'))[:,:,::-1].copy()
                flow.items=ocr.read(flow.image)
                self.assertEqual(flow.survival_points(),(140,220))
                self.assertEqual(flow.survival_reset_state()[0],0)
                self.assertEqual(flow.survival_candidate(),('S',2,1390,248))
        flow.window.click.assert_not_called()

    def test_latest_elite_points_do_not_truncate_malformed_goal(self):
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from adapters.local_ocr import LocalOCR
        ocr=LocalOCR();flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock())
        path=Path(__file__).resolve().parents[1]/'verification/failure-20261018-234702-3aa6ed0d9603-survival.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=ocr.read(flow.image)
        self.assertTrue(any('80/2]0' in i['text'] for i in flow.items))
        self.assertEqual(flow.survival_points(),(80,210))
        self.assertEqual(flow.survival_reset_state()[0],0)
        def stable(predicate,seconds):
            self.assertEqual(seconds,30)
            for expected in (False,False,False,True):self.assertEqual(predicate(),expected)
        flow.wait=stable
        with patch('local_flows.time.monotonic',side_effect=[0,1,2,3]):flow.wait_survival_ready()
        # The saved SS is already zero; the next available tier is S with two.
        self.assertEqual(flow.survival_candidate(),('S',2,1390,248))
        # A selected SS-only plan must not fabricate a chance or fall to S.
        flow.cfg={'survivalGrades':['SS'],'survivalCounts':{'SS':1}}
        with self.assertRaisesRegex(RuntimeError,'所选等级.*已耗尽'):flow.survival_candidate()
        flow.window.click.assert_not_called()

    def test_malformed_points_require_two_matching_local_views(self):
        import numpy as np
        flow=self.reset_flow('演习积分:80/2]0')
        flow.image=np.zeros((1015,1920,3),dtype=np.uint8)
        flow.ocr.read.side_effect=[[{'text':'80/210','score':.99}],[{'text':'80/210','score':.98}]]
        self.assertEqual(flow.survival_points(),(80,210))
        self.assertEqual(flow.ocr.read.call_count,2)
        flow.window.click.assert_not_called()

    def test_local_points_reject_conflict_low_score_bad_text_and_invalid_ratio(self):
        import numpy as np
        for pair in [(('80/210',.99),('80/220',.99)),(('80/210',.84),('80/210',.99)),
                     (('80/2]0',.99),('80/2]0',.99)),(('220/210',.99),('220/210',.99)),
                     (('0/0',.99),('0/0',.99))]:
            with self.subTest(pair=pair):
                flow=self.reset_flow('演习积分:80/2]0');flow.image=np.zeros((1015,1920,3),dtype=np.uint8)
                flow.ocr.read.side_effect=[[{'text':text,'score':score}] for text,score in pair]
                with self.assertRaisesRegex(RuntimeError,'积分'):flow.survival_points()
                flow.window.click.assert_not_called()

    def test_numeric_points_still_reject_impossible_goal_and_missing_anchor(self):
        for text in ('演习积分:80/2','演习积分:0/0','其他积分:80/210'):
            with self.subTest(text=text):
                flow=self.reset_flow(text)
                with self.assertRaisesRegex(RuntimeError,'积分'):flow.survival_points()
                flow.window.click.assert_not_called()

if __name__=='__main__':unittest.main()
