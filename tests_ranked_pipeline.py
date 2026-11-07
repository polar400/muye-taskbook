"""Real MaaFramework execution against simulated game frames and input only."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ranked_pipeline import BUNDLE, RankedSession, RankedWindow, run_ranked_pipeline
import numpy as np

NODES = json.loads((BUNDLE/'pipeline/ranked.json').read_text(encoding='utf-8'))
FAST = {name:{'rate_limit':1,'pre_delay':0,'post_delay':0} for name in NODES}
PAGES = {'home':1,'panel':2,'battle':3,'settlement':4,'closing':5,'cooldown':6}


class FakeOCR:
    def read(self, image):
        page = int(image[0, 0, 0])
        text = '剩余挑战次数' if page == PAGES['panel'] else '冷却30秒' if page == PAGES['cooldown'] else '确定' if page == PAGES['settlement'] else ''
        items = [{'text':text,'box':[0,0,1,1]}] if text else []
        if page == PAGES['cooldown']:
            items.append({'text':'确定','box':[0,0,1,1]})
        return items

    def match(self, image, name):
        return [{'box':[0,0,1,1]}] if int(image[0,0,0]) == PAGES['home'] and name.startswith('entry_') else []


class Game:
    def __init__(self, count=2, results=('victory',), limit=1, page='panel'):
        self.cfg = {'rankedServer':'本服','rankedLimit':limit,'battleSeconds':30,'tolerance':20}
        self.count = count
        self.page = page
        self.server = '本服'
        self.results = list(results)
        self.result_index = 0
        self.powers = [105,150,180,200,300]
        self.ocr = FakeOCR()
        self.window = Mock()
        self.log = Mock()
        self.events = []
        self.emit = lambda kind, message, **kw:self.events.append(dict(kind=kind,message=message,**kw))
        self.inputs = []
        self.settlement_delay = 0
        self.ending_frames = 0
        self.return_delay = 0
        self.returning_frames = 0
        self.image = self.capture_ready()
        self.items = self.ocr.read(self.image)
        self.read_failures = 0
        self.count_change = 1
        self.cooldown = False
        self.stuck_dialog = False
        self.paid_refresh = False
        self.unknown_result = False
        self.uncertain_challenge = False
        self.capture_error = None
        self.stop_after_challenge = False
        self.change_before_confirm = False
        self.closing_frames = 2
        self.can_return_home = True

    def checkpoint(self):
        if self.stop_after_challenge and 'challenge' in self.inputs:
            raise RuntimeError('已停止')

    def capture_ready(self):
        if getattr(self,'capture_error',None) and 'challenge' in self.inputs:
            raise RuntimeError(self.capture_error)
        if self.ending_frames:
            self.ending_frames -= 1
            if not self.ending_frames:
                self.page = 'settlement'
        if self.returning_frames:
            self.returning_frames -= 1
            if not self.returning_frames:
                self.page = 'panel'
        if self.page == 'closing' and self.can_return_home:
            self.closing_frames -= 1
            if self.closing_frames <= 0:
                self.page = 'home'
        return np.full((16, 20, 3), PAGES[self.page], dtype=np.uint8)

    def observe(self):
        self.checkpoint()
        self.image = self.capture_ready()
        self.items = self.ocr.read(self.image)
        return self.items

    def hits(self, pattern):
        items = self.items + ([{'text':'购买需要元宝','box':[0,0,1,1]}] if self.paid_refresh and self.page=='cooldown' else [])
        return [m for m in items if re.search(pattern,m['text'])]

    def ranked_panel_visible(self):
        return bool(self.hits('剩余挑战次数'))

    def ranked_state(self):
        if self.read_failures:
            self.read_failures -= 1
            raise RuntimeError('我方战力无法可靠识别')
        return self.count, 100 if self.count else None, [dict(power=p,button={'box':[0,0,1,1],'type':'challenge'}) for p in self.powers] if self.count else []

    def ranked_server_state(self):
        return self.server

    def ranked_server_button(self, server):
        return {'box':[0,0,1,1],'type':'scope','server':server}

    def ranked_end_battle_button(self):
        return {'box':[0,0,1,1],'type':'end'} if self.page == 'battle' else None

    def battle_settlement(self):
        return self.page == 'settlement'

    def ranked_battle_result(self):
        if self.unknown_result:
            raise RuntimeError('排位战胜负无法可靠识别，已保留结算')
        return self.results[min(self.result_index,len(self.results)-1)]

    def ranked_refresh_state(self):
        return ('cooldown',None) if self.cooldown else ('ready',{'box':[0,0,1,1],'type':'refresh'})

    def enter(self, label):
        if self.page != 'home':
            raise RuntimeError('当前页面无法可靠识别')
        self.inputs.append('enter')
        self.page = 'panel'

    def click_item(self, button):
        self.checkpoint()
        name = button['type']
        self.inputs.append(name)
        if name == 'challenge':
            self.page = 'battle'
            if self.uncertain_challenge:
                raise RuntimeError('后台消息发送超时，是否点击未知')
        elif name == 'end':
            # The game keeps battle controls visible during its ending animation.
            self.ending_frames = self.settlement_delay
            if not self.ending_frames:
                self.page = 'settlement'
        elif name == 'scope':
            self.server = button['server']
        elif name == 'refresh':
            if self.stuck_dialog or self.paid_refresh:
                self.page = 'cooldown'
            else:
                self.powers = [110,160,190,210,310]

    def confirm(self,guard=None):
        if self.change_before_confirm:
            self.page = 'home'
        self.observe()
        if guard is not None and not guard():
            raise RuntimeError('弹窗状态已变化，停止确认')
        if self.page == 'settlement':
            self.inputs.append('confirm')
            self.count -= self.count_change
            self.result_index += 1
            self.returning_frames = self.return_delay
            if not self.returning_frames:
                self.page = 'panel'
        elif self.page == 'cooldown':
            self.inputs.append('notice')
        else:
            raise RuntimeError('没有可确认的弹窗')

    def close_panel(self, check_home=True):
        assert check_home is False
        self.inputs.append('close')
        self.page = 'closing'


class RankedPipelineTests(unittest.TestCase):
    def run_game(self, game, overrides=None):
        original = game.checkpoint
        try:
            return run_ranked_pipeline(game, pipeline_override=overrides or FAST)
        finally:
            self.assertEqual(game.checkpoint, original)
            game.window.click.assert_not_called()  # Only simulated game input is used.

    def test_real_tasker_one_round_stops_after_limit_and_returns_home(self):
        game = Game()
        self.assertIsNone(self.run_game(game))
        self.assertEqual(game.inputs,['challenge','end','confirm','close'])
        self.assertEqual(game.page,'home')
        self.assertEqual(game.count,1)
        self.assertTrue(any(e.get('status')=='done' and e['completed']==1 for e in game.events))

    def test_zero_count_skips_without_challenge(self):
        game = Game(count=0)
        self.assertEqual(self.run_game(game),'skipped')
        self.assertEqual(game.inputs,['close'])

    def test_home_entry_and_scope_switch_are_verified(self):
        game = Game(page='home')
        game.server = '连服'
        self.run_game(game)
        self.assertEqual(game.inputs[:2],['enter','scope'])
        self.assertEqual(game.server,'本服')

    def test_defeat_refresh_then_victory_exhausts_count(self):
        game = Game(results=('defeat','victory'),limit=0)
        self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end','confirm','refresh','challenge','end','confirm','close'])
        self.assertEqual(game.count,0)

    def test_cooldown_continues_without_refresh_input(self):
        game = Game(results=('defeat','victory'),limit=0)
        game.cooldown = True
        self.run_game(game)
        self.assertNotIn('refresh',game.inputs)
        self.assertEqual(game.inputs.count('challenge'),2)

    def test_defeat_at_limit_does_not_refresh(self):
        game = Game(results=('defeat',))
        self.run_game(game)
        self.assertNotIn('refresh',game.inputs)

    def test_unknown_outcome_never_confirms_or_refreshes(self):
        game = Game()
        game.unknown_result = True
        with self.assertRaisesRegex(RuntimeError,'胜负无法'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end'])
        self.assertEqual(game.page,'settlement')

    def test_new_frame_before_confirm_must_still_be_same_settlement(self):
        game = Game()
        game.change_before_confirm = True
        with self.assertRaisesRegex(RuntimeError,'弹窗状态已变化'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end'])

    def test_pause_between_recognition_and_click_rejects_stale_target(self):
        game = Game()
        session = RankedSession(game)
        backend = Mock()
        window = RankedWindow(session,backend)
        session.pause_epoch = 1
        with self.assertRaisesRegex(RuntimeError,'点击依据已过期'):
            window.click(10,20)
        backend.click.assert_not_called()
        session.qualified_epoch = 1
        window.click(10,20)
        backend.click.assert_called_once_with(10,20)

    def test_count_unchanged_or_double_spent_stops_before_next_challenge(self):
        for delta in (0,2):
            game = Game(count=3,limit=0)
            game.count_change = delta
            with self.subTest(delta=delta),self.assertRaisesRegex(RuntimeError,'次数未按一场减少'):
                self.run_game(game)
            self.assertEqual(game.inputs.count('challenge'),1)
            self.assertNotIn('close',game.inputs)
            self.assertFalse(any(e.get('completed',0)>0 for e in game.events))

    def test_read_errors_retry_without_input_and_stop_after_three(self):
        game = Game()
        game.read_failures = 3
        with self.assertRaisesRegex(RuntimeError,'连续3次识别失败'):
            self.run_game(game)
        self.assertEqual(game.inputs,[])

    def test_two_transient_read_errors_can_recover(self):
        game = Game()
        game.read_failures = 2
        self.run_game(game)
        self.assertEqual(game.inputs.count('challenge'),1)

    def test_end_button_missed_on_fresh_frame_waits_then_clicks_once(self):
        game=Game()
        original=game.ranked_end_battle_button
        calls=[0]
        def button():
            if game.page=='battle':
                calls[0]+=1
                if calls[0]==2:return None
            return original()
        game.ranked_end_battle_button=button
        self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end','confirm','close'])
        self.assertGreaterEqual(calls[0],4)

    def miss_fresh_end_frame(self, game):
        original = game.ranked_end_battle_button
        calls = {}
        def button():
            if game.page == 'battle':
                match = game.inputs.count('challenge')
                calls[match] = calls.get(match, 0) + 1
                if calls[match] == 2:
                    return None
            return original()
        game.ranked_end_battle_button = button

    def test_retry_then_delayed_victory_or_defeat_confirms_once(self):
        for result in ('victory', 'defeat'):
            with self.subTest(result=result):
                game = Game(results=(result,))
                game.settlement_delay = 8
                game.return_delay = 6
                self.miss_fresh_end_frame(game)
                self.run_game(game)
                self.assertEqual(game.inputs, ['challenge','end','confirm','close'])
                self.assertEqual((game.page, game.count), ('home', 1))
                self.assertEqual(sum(e.get('node') == 'end_battle' for e in game.events), 2)

    def test_retry_routes_do_not_leak_across_two_delayed_matches(self):
        game = Game(results=('defeat','victory'), limit=0)
        game.settlement_delay = 8
        game.return_delay = 6
        self.miss_fresh_end_frame(game)
        self.run_game(game)
        self.assertEqual(game.inputs,
                         ['challenge','end','confirm','refresh','challenge','end','confirm','close'])
        self.assertEqual((game.page, game.count), ('home', 0))
        self.assertEqual(sum(e.get('node') == 'end_battle' for e in game.events), 4)

    def test_sent_end_waits_for_settlement_with_finite_deadline(self):
        game = Game()
        game.settlement_delay = 1000
        self.miss_fresh_end_frame(game)
        with self.timed_game(game, 'battle', 5), self.assertRaisesRegex(TimeoutError, '等待结算'):
            self.run_game(game)
        self.assertEqual(game.inputs, ['challenge','end'])
        self.assertFalse(any(e.get('status') == 'done' for e in game.events))

    def test_flickering_end_button_keeps_original_finite_deadline(self):
        game=Game()
        original=game.ranked_end_battle_button
        calls=[0]
        def button():
            if game.page=='battle':
                calls[0]+=1
                return original() if calls[0]%2 else None
            return original()
        game.ranked_end_battle_button=button
        with self.timed_game(game,'battle',20),self.assertRaisesRegex(TimeoutError,'等待超时'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge'])

    def test_uncertain_end_click_is_never_replayed(self):
        game=Game()
        click=game.click_item
        def uncertain(button):
            click(button)
            if button['type']=='end':raise RuntimeError('结束战斗发送结果未知')
        game.click_item=uncertain
        with self.assertRaisesRegex(RuntimeError,'发送结果未知'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end'])

    def test_uncertain_settlement_confirm_is_never_replayed(self):
        game = Game()
        confirm = game.confirm
        def uncertain(guard=None):
            confirm(guard=guard)
            raise RuntimeError('结算确认发送结果未知')
        game.confirm = uncertain
        with self.assertRaisesRegex(RuntimeError, '确认发送结果未知'):
            self.run_game(game)
        self.assertEqual(game.inputs, ['challenge','end','confirm'])
        self.assertFalse(any(e.get('status') == 'done' for e in game.events))

    def test_uncertain_input_is_not_replayed(self):
        game = Game()
        game.uncertain_challenge = True
        with self.assertRaisesRegex(RuntimeError,'发送超时'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge'])

    def test_window_failure_and_stop_during_battle_never_send_end(self):
        for stopping in (False,True):
            game = Game()
            if stopping:
                game.stop_after_challenge = True
            else:
                game.capture_error = '游戏已最小化'
            with self.subTest(stopping=stopping),self.assertRaisesRegex(RuntimeError,'已停止|最小化'):
                self.run_game(game)
            self.assertEqual(game.inputs,['challenge'])

    def test_existing_settlement_is_confirmed_without_new_challenge(self):
        game = Game(page='settlement')
        self.run_game(game)
        self.assertEqual(game.inputs,['confirm','close'])

    def test_native_success_without_home_terminal_is_rejected(self):
        overrides = dict(FAST)
        overrides['RankedStart'] = dict(FAST['RankedStart'],next=[])
        # Start dynamically routes next, so stop at Decide instead.
        overrides['RankedRead'] = dict(FAST['RankedRead'],action='DoNothing',next=[])
        game = Game()
        with self.assertRaisesRegex(RuntimeError,'流水线未完成'):
            self.run_game(game,overrides)
        self.assertEqual(game.inputs,[])

    def timed_game(self, game, page, increment):
        capture = game.capture_ready
        game.test_clock = 0
        def frame():
            if game.page == page:
                game.test_clock += increment
            return capture()
        game.capture_ready = frame
        return patch('ranked_pipeline.time.monotonic',side_effect=lambda:game.test_clock)

    def test_stuck_refresh_notice_is_confirmed_once_then_times_out(self):
        game = Game(count=3,results=('defeat','victory'),limit=0)
        game.stuck_dialog = True
        with self.timed_game(game,'cooldown',10),self.assertRaisesRegex(TimeoutError,'等待超时'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end','confirm','refresh','notice'])

    def test_paid_refresh_prompt_stops_without_confirmation(self):
        game = Game(count=3,results=('defeat','victory'),limit=0)
        game.paid_refresh = True
        with self.assertRaisesRegex(ValueError,'付费提示'):
            self.run_game(game)
        self.assertEqual(game.inputs,['challenge','end','confirm','refresh'])

    def test_home_missing_times_out_without_marking_done(self):
        game = Game()
        game.can_return_home = False
        with self.timed_game(game,'closing',20),self.assertRaisesRegex(TimeoutError,'木叶村'):
            self.run_game(game)
        self.assertEqual(game.inputs.count('close'),1)
        self.assertFalse(any(e.get('status')=='done' for e in game.events))

    def test_pause_time_is_excluded_and_active_timeout_is_finite(self):
        game = Game()
        now = [0.0]
        game.checkpoint = lambda:now.__setitem__(0,now[0]+60)
        session = RankedSession(game)
        session.clock = lambda:now[0]
        session.wait_for('home',5)
        session.frame_seq = 1
        self.assertFalse(session.recognize('home',game.image))
        self.assertEqual(session.active_time(),0)
        now[0] += 6
        with self.assertRaisesRegex(TimeoutError,'等待超时'):
            session.recognize('home',game.image)


if __name__ == '__main__':
    unittest.main()
