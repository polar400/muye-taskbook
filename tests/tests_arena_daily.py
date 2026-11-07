"""Daily priority and battle loop with real task pixels and simulated game IO."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import arena_daily
import numpy as np
from PIL import Image
from arena_daily import DailyVision,ArenaDaily,next_action
from arena_task import ArenaTask,run_arena,validate_arena_config
from adapters.local_ocr import LocalOCR

ROOT=Path(__file__).resolve().parents[1]


class DailyVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.vision=DailyVision(LocalOCR());cls.evidence=[]

    def image(self,path):return np.array(Image.open(ROOT/path).convert('RGB'))[:,:,::-1].copy()

    def test_real_eligible_claimable_and_unmet_boards(self):
        sources=[('resources/local/catalog/arena/20261016-973-team-ready/game.png','eligible',6),
                 ('resources/local/arena/references/reward-ready-user.png','claim',6),
                 ('resources/local/arena/references/reward-unmet-user.png','unmet',4)]
        for source,state,count in sources:
            with self.subTest(state=state):
                image=self.image(source)
                if image.shape[1]==1920:image=image[350:790,90:342].copy()
                board=self.vision.read(image)
                self.assertIsNotNone(board);self.assertEqual(board['remaining'],count)
                self.assertEqual([c['state'] for c in board['cards']],[state,state])
                self.assertTrue(all(c['description'] for c in board['cards']))
                self.evidence.append(dict(source=source,board=board))

    def test_missing_or_conflicting_progress_never_authorizes_input(self):
        image=self.image('resources/local/arena/references/reward-ready-user.png')
        image[413:441,130:242]=0
        board=self.vision.read(image)
        # An unpaired visible action is not a complete board.
        self.assertIsNone(board)

    def test_templates_are_original_pixels(self):
        records=json.loads((ROOT/'resources/local/arena_daily/sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(records),10)
        for r in records:
            image=Image.open(ROOT/r['source']).convert('RGB')
            if r['box']:image=image.crop(r['box'])
            self.assertEqual(image.tobytes(),Image.open(ROOT/r['path']).convert('RGB').tobytes())

    def test_zero_ocr_does_not_finish_a_board_with_tasks(self):
        image=self.image('resources/local/arena/references/reward-ready-user.png')
        actual=self.vision.ocr.read
        def read(view,only_rec=False):
            if only_rec:return [{'text':'剩余0个任务可挑战','score':.99,'box':[0,0,50,20]}]
            return actual(view)
        with patch.object(self.vision.ocr,'read',side_effect=read):board=self.vision.read(image)
        self.assertIsNone(board['remaining']);self.assertEqual(next_action(board)[0],'claim')

    def test_hover_button_on_composed_card_is_unmet_until_lowered(self):
        image=self.image('resources/local/arena/references/reward-unmet-user.png')
        image[424:453,119:220]=0
        patch_image=self.image('resources/local/arena_daily/image/lower.png')
        h,w=patch_image.shape[:2];image[419:419+h,119:119+w]=patch_image
        board=self.vision.read(image)
        self.assertIsNotNone(board);self.assertTrue(board['cards'][0]['hovered'])
        self.assertEqual(next_action(board)[0],'battle')

    def test_real_lower_timeouts_still_show_unmet_not_a_lower_button(self):
        for folder in ('arena-daily-20261019-232750-23f34458',
                       'arena-daily-20261019-232831-3ebeea34'):
            with self.subTest(folder=folder):
                source='verification/'+folder+'/last.png'
                image=self.image(source)[350:790,90:342].copy()
                board=self.vision.read(image,(90,350))
                self.assertIsNotNone(board);self.assertEqual(board['remaining'],4)
                self.assertEqual([(c['state'],c['progress'],c['hovered']) for c in board['cards']],
                                 [('unmet',0,False),('unmet',0,False)])
                self.assertEqual(self.vision.match(image,'lower'),[])
                self.assertEqual(board['cards'][0]['button']['box'],[221,492,101,29])
                report=json.loads((ROOT/'verification'/folder/'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['battles'],0)
                self.assertEqual(report['events'][-1]['stage'],'悬停未满足任务，未发送按键')
                self.evidence.append(dict(source=source,board=board,
                    interpretation='最后画面仍为未满足；不能仅据此断言整个等待期间都未出现降低按钮'))

    def test_real_normal_and_highlighted_lower_buttons_preserve_task_identity(self):
        folder='verification/arena-hover-live-20261020-000058-120721/'
        baseline=self.vision.read(self.image(folder+'outside-before.png')[350:790,90:342].copy(),(90,350))
        # after-1 is the training source; other full frames are held out.
        for name in ('manual-2.png','physical-after-1.png','physical-after-2.png','physical-after-4.png'):
            with self.subTest(name=name):
                board=self.vision.read(self.image(folder+name)[350:790,90:342].copy(),(90,350))
                self.assertIsNotNone(board)
                self.assertEqual(arena_daily.board_key(board),arena_daily.board_key(baseline))
                self.assertEqual([c['hovered'] for c in board['cards']],[True,False])
                self.assertEqual(next_action(board)[0],'battle')
                self.evidence.append(dict(source=folder+name,board=board,heldOut=name!='physical-after-1.png'))

    def test_real_shared_battle_sprites_are_recognized_without_input(self):
        # These are historical common battle skins, not arena live evidence.
        from local_flows import LocalFlows
        for source,result in [('resources/local/battle-settlement-calibration.png','victory'),
                              ('resources/local/ranked-defeat-1920.png','defeat')]:
            flow=LocalFlows(Mock(),self.vision.ocr,{},lambda:None,Mock())
            flow.image=self.image(source);runner=ArenaDaily(ArenaTask(flow),'休闲战斗')
            state=runner.settlement();self.assertIsNotNone(state)
            self.assertEqual(state['result'],result)
            self.assertTrue(870<state['button']['box'][0]<1060)
            flow.window.click.assert_not_called()
        flow.image=self.image('resources/local/ranked-battle-1920.png')
        self.assertIsNone(runner.settlement())
        self.assertTrue(runner.auto())

    def test_virtual_pointer_trial_frames_preserve_both_task_identities(self):
        folder='verification/arena-virtual-pointer-20261020-010655-494114/'
        report=json.loads((ROOT/folder/'report.json').read_text(encoding='utf-8'))
        baseline=self.vision.read(self.image(folder+'before.png')[350:790,90:342].copy(),(90,350))
        self.assertIsNotNone(baseline)
        for index in range(5):
            with self.subTest(frame=index):
                source=folder+f'after-{index}.png'
                board=self.vision.read(self.image(source)[350:790,90:342].copy(),(90,350))
                self.assertIsNotNone(board)
                self.assertEqual(arena_daily.board_key(board),arena_daily.board_key(baseline))
                self.assertEqual([c['hovered'] for c in board['cards']],[index>0,False])
                self.evidence.append(dict(source=source,board=board,heldOut=True,
                                          interpretation='单次虚拟指针悬停实图；不代表降级已完成'))
        self.assertTrue(report['importPointersRestored'])
        self.assertEqual(report['cursorBefore'],report['cursorAfter'])
        self.assertEqual(report['foregroundBefore'],report['foregroundAfter'])
        self.assertEqual(report['buttonClicks'],0)

    def test_lower_confirmation_trial_stopped_with_unmet_tasks_and_zero_clicks(self):
        folder='verification/arena-lower-virtual-20261020-011916-475721/'
        report=json.loads((ROOT/folder/'report.json').read_text(encoding='utf-8'))
        for name in ('00-before.png','01-before.png','02-open-lower.png','03-open-lower.png'):
            with self.subTest(frame=name):
                source=folder+name
                board=self.vision.read(self.image(source)[350:790,90:342].copy(),(90,350))
                self.assertIsNotNone(board)
                self.assertEqual(arena_daily.board_key(board),arena_daily.board_key(report['boardBefore']))
                self.assertEqual([c['hovered'] for c in board['cards']],[False,False])
                self.evidence.append(dict(source=source,board=board,heldOut=True,
                    interpretation='新单项验收超时，未复现悬停反馈；不能仅归因OCR耗时'))
        self.assertEqual(report['result'],'failed');self.assertEqual(report['inputAttempts'],0)
        self.assertEqual(report['inputs'],[]);self.assertEqual(len(report['phases']),1)
        self.assertTrue(report['phases'][0]['restored'])
        self.assertTrue(report['cursorUnchanged']);self.assertTrue(report['foregroundUnchanged'])


class Game:
    def __init__(self,mode):
        self.mode=mode;self.phase='board';self.time=0;self.auto_enabled=False;self.ticks=0
        self.tasks=[dict(description=key,state='eligible' if i<2 else 'unmet',progress=0,hovered=False)
                    for i,key in enumerate('ABCDEF')]
        self.results=iter(['victory','defeat','victory','victory']);self.result=None;self.inputs=[]
        self.ignore_claim=False
        self.tokens=2;self.last_mode=None

    def board(self):
        if self.phase!='board':return None
        cards=[]
        for i,task in enumerate(self.tasks[:2]):
            cards.append(dict(deepcopy(task),index=i,button=dict(box=[220,490+i*186,100,30],score=1)))
        return dict(remaining=len(self.tasks),cards=cards)

    def observe(self):
        self.time+=.1
        if self.phase=='battle' and self.auto_enabled:
            self.ticks+=1
            if self.ticks>=2:self.phase='settlement'

    def click(self,x,y):
        self.inputs.append((self.phase,x,y))
        if self.phase=='board':
            if y>850:
                if self.mode=='日常模式':
                    if x not in (500,800) or (x==500 and self.tokens<=0):raise AssertionError('unprotected ranked')
                elif x!=(500 if self.mode=='段位战斗' else 800):raise AssertionError('wrong mode')
                if any(t['state']=='claim' for t in self.tasks[:2]):raise AssertionError('unclaimed reward')
                self.last_mode='段位战斗' if x==500 else '休闲战斗'
                self.phase='battle';self.auto_enabled=False;self.ticks=0;self.result=next(self.results)
            else:
                index=0 if y<600 else 1;task=self.tasks[index]
                if task['state']=='claim':
                    if not self.ignore_claim:self.tasks.pop(index)
                elif task['state']=='unmet' and task['hovered']:
                    self.lowered=index;self.phase='lower_dialog'
                else:raise AssertionError('clicked ineligible task')
        elif self.phase=='lower_dialog':
            self.tasks[self.lowered].update(state='eligible',hovered=False);self.phase='board'
        elif self.phase=='battle':self.auto_enabled=True
        elif self.phase=='settlement':
            if self.last_mode=='段位战斗' and self.result=='defeat':self.tokens-=1
            if self.result=='victory':
                for task in self.tasks[:2]:
                    if task['state']=='eligible':task.update(state='claim',progress=1)
            self.phase='board'

    def hover(self,x,y):
        self.inputs.append(('hover',x,y));index=0 if y<600 else 1
        self.tasks[index]['hovered']=True


class DailyLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arena-daily-test-',dir=ROOT/'verification')
        self.p=patch.object(arena_daily,'ROOT',Path(self.temp.name));self.p.start()

    def tearDown(self):self.p.stop();self.temp.cleanup()

    def runner(self,mode='休闲战斗',limit=3):
        game=Game(mode);flow=Mock();flow.cfg={'arenaMode':mode,'battleSeconds':30}
        if limit is not None:flow.cfg['arenaBattleLimit']=limit
        flow.image=np.zeros((1015,1920,3),dtype=np.uint8);flow.checkpoint=lambda:None
        flow.observe=game.observe
        flow.click_item=lambda item:game.click(item['box'][0]+item['box'][2]//2,item['box'][1]+item['box'][3]//2)
        flow.window.hover=game.hover
        a=ArenaTask(flow);a.clock=lambda:game.time;a.sleep=lambda s:setattr(game,'time',game.time+s)
        a.popup=lambda:None
        a.panel=lambda:dict(controls={'ranked_battle':{'box':[450,900,100,40]},
                                     'casual_battle':{'box':[750,900,100,40]}}) if game.phase=='board' else None
        a.stable_panel=lambda:a.wait('返回竞技场',a.panel)
        runner=ArenaDaily(a,mode);runner.board=game.board
        runner.read_tokens=lambda:game.tokens
        confirm={'box':[920,630,80,40]}
        runner.lower_dialog=lambda:confirm if game.phase=='lower_dialog' else None
        runner.settlement=lambda:dict(result=game.result,button=confirm) if game.phase=='settlement' else None
        runner.auto=lambda:{'on' if game.auto_enabled else 'off':{'box':[1750,920,100,50]}} if game.phase=='battle' else {}
        return runner,game

    def test_both_modes_obey_cap_and_skip_unmet_tasks(self):
        for mode in ('段位战斗','休闲战斗'):
            with self.subTest(mode=mode):
                runner,game=self.runner(mode)
                self.assertEqual(runner.run(),'battle_limit_done')
                self.assertEqual(len(game.tasks),4);self.assertEqual(runner.battles,3)
                self.assertEqual(sum(p=='hover' for p,x,y in game.inputs),0)
                self.assertEqual(sum(p=='board' and y<850 for p,x,y in game.inputs),2)
                self.assertEqual(sum(p=='battle' for p,x,y in game.inputs),3)
                report=json.loads((runner.folder/'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['result'],'battle_limit_done')
                self.assertEqual(report['battleLimit'],3);self.assertFalse(report['automaticLowering'])

    def test_claim_does_not_replay_when_ui_never_changes(self):
        runner,game=self.runner();game.tasks[0].update(state='claim',progress=1);game.ignore_claim=True
        with self.assertRaises(TimeoutError):runner.run()
        self.assertEqual(sum(p=='board' and y<850 for p,x,y in game.inputs),1)
        self.assertEqual(runner.battles,0)

    def test_all_unmet_tasks_never_hover_lower_or_block_matching(self):
        runner,game=self.runner()
        for task in game.tasks:task.update(state='unmet')
        runner.f.window.hover=Mock(side_effect=AssertionError('must not hover'))
        runner.lower=Mock(side_effect=AssertionError('must not lower'))
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(runner.battles,3);self.assertEqual(len(game.tasks),6)
        runner.f.window.hover.assert_not_called();runner.lower.assert_not_called()
        report=json.loads((runner.folder/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['result'],'battle_limit_done')
        self.assertNotIn('降低任务难度',[e['stage'] for e in report['events']])

    def test_claim_unmet_and_completion_priority(self):
        runner,game=self.runner()
        game.tasks[0].update(state='eligible');game.tasks[1].update(state='unmet')
        self.assertEqual(next_action(game.board())[0],'battle')
        game.tasks[0].update(state='claim',progress=1)
        self.assertEqual(next_action(game.board())[0],'claim')
        self.assertEqual(next_action(dict(remaining=0,cards=[]))[0],'battle')

    def test_empty_tasks_continue_until_cap_and_no_fourth_match(self):
        runner,game=self.runner();game.tasks=[]
        self.assertEqual(runner.run(),'battle_limit_done');self.assertEqual(runner.battles,3)
        self.assertEqual(sum(p=='board' and y>850 for p,x,y in game.inputs),3)
        with self.assertRaisesRegex(RuntimeError,'场数上限'):runner.fight(game.board())
        self.assertEqual(sum(p=='board' and y>850 for p,x,y in game.inputs),3)

    def test_rewards_after_last_battle_are_claimed_without_extra_match(self):
        runner,game=self.runner(limit=1)
        game.tasks[0].update(state='claim',progress=1)
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(sum(p=='board' and y>850 for p,x,y in game.inputs),1)
        self.assertEqual(sum(p=='board' and y<850 for p,x,y in game.inputs),2)
        self.assertLess(game.inputs[0][2],850)
        self.assertEqual(runner.battles,1)
        self.assertFalse(any(t['state']=='claim' for t in game.tasks[:2]))

    def test_legacy_lower_entry_is_disabled_without_any_input(self):
        runner,game=self.runner()
        with self.assertRaisesRegex(RuntimeError,'已停用'):runner.lower(game.board(),game.board()['cards'][0])
        self.assertEqual(game.inputs,[])

    def test_limit_default_validation_and_both_results_count(self):
        from arena_settings import battle_limit
        self.assertEqual(battle_limit({}),3)
        for value in (1,100):self.assertEqual(battle_limit({'arenaBattleLimit':value}),value)
        for value in (0,101,-1,False,True,2.5,'3',None):
            with self.subTest(value=value):
                cfg=dict(tasks=['arena'],arenaMode='休闲战斗',arenaBattleLimit=value)
                flow=Mock(cfg=cfg)
                with self.assertRaises(ValueError):run_arena(flow)
                flow.observe.assert_not_called()
        runner,game=self.runner(limit=None)
        self.assertEqual(runner.battle_limit,3)
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual([e['result'] for e in runner.events if e['stage'].startswith('已返回竞技场')],
                         ['victory','defeat','victory'])

    def test_unsafe_or_unrelated_lower_dialog_is_not_confirmed(self):
        runner,game=self.runner();runner.f.ocr=Mock()
        method=ArenaDaily.lower_dialog.__get__(runner)
        for text,expected in [('是否降低任务难度？','button'),('领取奖励是否继续？',None),('降低难度消耗元宝','error')]:
            runner.f.ocr.read.return_value=[{'text':text,'score':.99,'box':[10,20,200,30]},
                                            {'text':'确定','score':.99,'box':[400,400,70,30]}]
            if expected=='error':
                with self.assertRaisesRegex(RuntimeError,'消耗'):method()
            elif expected=='button':self.assertIsNotNone(method())
            else:self.assertIsNone(method())
        self.assertEqual(game.inputs,[])

    def test_input_exception_does_not_retry_claim(self):
        runner,game=self.runner();game.tasks[0].update(state='claim',progress=1)
        def fail(item):
            game.inputs.append(('uncertain',0,0));raise RuntimeError('unknown send')
        runner.f.click_item=fail
        with self.assertRaisesRegex(RuntimeError,'unknown send'):runner.run()
        self.assertEqual(game.inputs,[('uncertain',0,0)])

    def test_stale_task_before_match_sends_nothing(self):
        runner,game=self.runner();expected=game.board();game.tasks[0].update(state='claim',progress=1)
        with self.assertRaisesRegex(RuntimeError,'已变化'):runner.fight(expected)
        self.assertEqual(game.inputs,[])

    def test_mode_validation_and_open_only_diagnostic(self):
        for mode in ('段位战斗','排位战斗','休闲战斗'):
            validate_arena_config({'tasks':['arena'],'arenaMode':mode})
        for cfg in ({'tasks':['arena'],'arenaMode':'随意'},
                    {'tasks':['arena'],'arenaMode':'休闲战斗','battleSeconds':False}):
            with self.assertRaises(ValueError):validate_arena_config(cfg)
        f=Mock();f.cfg={'tasks':['arena']}
        with patch('arena_task.ArenaTask') as cls,patch('arena_daily.run_daily') as daily:
            cls.return_value.run.return_value='opened'
            self.assertEqual(run_arena(f),'opened');daily.assert_not_called()


if __name__=='__main__':unittest.main()
