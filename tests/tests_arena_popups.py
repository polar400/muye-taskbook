"""User popup pixels, guarded background routing and one-count battle recovery."""
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from arena_task import ArenaTask
from arena_daily import ArenaDaily
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


class ArenaPopupTests(unittest.TestCase):
    evidence=[]

    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR();cls.frames={}
        for key,path in (
            ('trial','resources/local/arena_popup_references/trial-game.png'),
            ('victory','resources/local/arena_popup_references/victory-game.png'),
            ('panel','resources/local/catalog/arena/20261016-973-team-ready/game.png'),
            ('generic','resources/local/battle-settlement-calibration.png')):
            image=np.array(Image.open(ROOT/path).convert('RGB'))[:,:,::-1].copy()
            cls.frames[key]=(image,cls.ocr.read(image))
        image=np.array(Image.open(ROOT/'resources/local/arena_popup_references/battle-victory-confirm-game.png').convert('RGB'))[:,:,::-1].copy()
        cls.frames['blue']=(image,cls.ocr.read(image))

    def task(self,key='trial'):
        f=LocalFlows(Mock(),self.ocr,{'tasks':['arena'],'battleSeconds':30},lambda:None,Mock())
        task=ArenaTask(f);state=dict(key=key,time=0);inputs=[]
        task.clock=lambda:state['time'];task.sleep=lambda n:state.update(time=state['time']+n)
        def observe():
            image,words=self.frames[state['key']];f.image=image.copy();f.items=list(words)
            state['time']+=.05
        f.observe=observe;observe()
        f.click_item=lambda target:inputs.append((state['key'],tuple(target['box'])))
        return task,state,inputs

    def test_original_trial_and_victory_have_distinct_titles_and_targets(self):
        for kind,box in (('trial',[1135,696,121,41]),('victory',[846,714,194,51])):
            with self.subTest(kind=kind):
                a,_,inputs=self.task(kind);popup=a.popup()
                self.assertEqual(popup['kind'],kind);self.assertEqual(popup['button']['box'],box)
                self.assertEqual(popup['title']['score'],1);self.assertEqual(popup['button']['score'],1)
                self.assertTrue(a.blocked());self.assertIsNone(a.panel());self.assertEqual(inputs,[])
                self.evidence.append(dict(kind=kind,popup=popup))

    def test_trial_orange_confirm_is_not_a_settlement(self):
        a,_,inputs=self.task('trial');daily=ArenaDaily(a,'休闲战斗')
        self.assertIsNone(daily.settlement());self.assertEqual(daily.auto(),{});self.assertEqual(inputs,[])

    def test_victory_overlay_is_a_victory_settlement(self):
        a,_,inputs=self.task('victory');daily=ArenaDaily(a,'休闲战斗')
        self.assertEqual(daily.settlement()['result'],'victory')
        self.assertEqual(daily.settlement()['button']['box'],[846,714,194,51]);self.assertEqual(inputs,[])

    def test_real_blue_battle_confirmation_is_recognized(self):
        a,_,inputs=self.task('blue');daily=ArenaDaily(a,'休闲战斗')
        result=daily.settlement()
        self.assertIsNotNone(result);self.assertEqual(result['result'],'victory')
        self.assertEqual(result['button']['text'],'确认')
        self.assertGreaterEqual(result['button']['score'],.85)
        x,y,w,h=result['button']['box'];self.assertTrue(850<x<1100 and 600<y<700)
        self.assertEqual(inputs,[])
        self.evidence.append(dict(kind='battle-blue-confirm',settlement=result))

    def test_blue_confirm_without_victory_or_defeat_is_not_clicked(self):
        a,_,inputs=self.task('blue');a.f.image[240:590,750:1270]=0
        self.assertIsNone(ArenaDaily(a,'休闲战斗').settlement());self.assertEqual(inputs,[])

    def test_confirmation_word_variants_need_unique_reliable_button_and_result(self):
        a,_,inputs=self.task('blue');a.popup=lambda:None;a.f.ocr=Mock();daily=ArenaDaily(a,'休闲战斗')
        for outcome in ('victory','defeat'):
            a.f.ocr.match.side_effect=lambda image,name,threshold:([dict(score=.99)] if name==outcome else [])
            for text in ('确定','确认'):
                a.f.ocr.read.return_value=[dict(text=text,score=.99,box=[400,450,60,30])]
                self.assertEqual(daily.settlement()['result'],outcome)
        a.f.ocr.read.return_value=[dict(text='确认',score=.8,box=[400,450,60,30])]
        self.assertIsNone(daily.settlement())
        a.f.ocr.read.return_value=[dict(text=t,score=.99,box=[400,450+i*50,60,30]) for i,t in enumerate(('确定','确认'))]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):daily.settlement()
        a.f.ocr.match.side_effect=None;a.f.ocr.match.return_value=[dict(score=.99)]
        with self.assertRaisesRegex(RuntimeError,'胜负证据冲突'):daily.settlement()
        self.assertEqual(inputs,[])

    def test_missing_title_or_button_never_clicks(self):
        for kind,area in (('trial',(735,135,1190,235)),('trial',(1125,686,1266,747)),
                          ('victory',(836,704,1050,775))):
            with self.subTest(kind=kind,area=area):
                a,_,inputs=self.task(kind);x,y,r,b=area;a.f.image[y:b,x:r]=0
                popup=a.popup()
                if popup:self.assertIsNone(popup['button'])
                a.handle_popup();self.assertEqual(inputs,[])

    def test_duplicate_skip_and_payment_prompt_are_rejected(self):
        a,_,inputs=self.task();a.f.image[696:737,930:1051]=a.f.image[696:737,1135:1256]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):a.handle_popup()
        self.assertEqual(inputs,[])
        a,_,inputs=self.task();a.f.items.append(dict(text='消耗元宝',score=.99,box=[800,500,100,25]))
        with self.assertRaisesRegex(RuntimeError,'消耗'):a.handle_popup()
        self.assertEqual(inputs,[])

    def test_fresh_frame_change_before_skip_sends_nothing(self):
        a,state,inputs=self.task();state['key']='panel'
        self.assertTrue(a.handle_popup());self.assertEqual(inputs,[]);self.assertEqual(a.popup_events,[])

    def test_slow_fresh_frame_cannot_click_after_the_wait_deadline(self):
        a,state,inputs=self.task();observe=a.f.observe
        def slow():observe();state['time']+=2
        a.f.observe=slow
        with self.assertRaisesRegex(TimeoutError,'发送前已超时'):a.handle_popup(deadline=1)
        self.assertEqual(inputs,[]);self.assertEqual(a.popup_events,[])

    def test_popup_interrupt_resets_consecutive_panel_frames(self):
        a,_,_=self.task('panel');a.f.observe=Mock();a.sleep=Mock()
        a.handle_popup=Mock(side_effect=[False,True,False,False])
        a.panel=Mock(return_value={'page':'arena'})
        self.assertEqual(a.stable_panel(),{'page':'arena'})
        self.assertEqual(a.f.observe.call_count,4);self.assertEqual(a.panel.call_count,3)

    def test_persistent_trial_times_out_after_one_blue_skip(self):
        a,_,inputs=self.task()
        with self.assertRaises(TimeoutError):a.wait('等待试用弹窗消失',lambda:True,seconds=1)
        self.assertEqual(inputs,[('trial',(1135,696,121,41))])
        self.assertFalse(a.popup_events[0]['cleared'])

    def test_unknown_skip_input_is_never_replayed(self):
        a,_,_=self.task();a.f.click_item=Mock(side_effect=RuntimeError('send unknown'))
        with self.assertRaisesRegex(RuntimeError,'unknown'):a.handle_popup()
        self.assertTrue(a.handle_popup());self.assertEqual(a.f.click_item.call_count,1)
        self.assertEqual(a.popup_events[0]['status'],'sending')

    def test_one_missing_frame_does_not_allow_another_skip(self):
        a,state,inputs=self.task();a.handle_popup()
        state['key']='panel';a.f.observe();self.assertTrue(a.handle_popup())
        state['key']='trial';a.f.observe();self.assertTrue(a.handle_popup())
        self.assertEqual(len(inputs),1);self.assertFalse(a.popup_events[0]['cleared'])
        state['key']='panel';a.f.observe();a.handle_popup();a.f.observe();a.handle_popup()
        self.assertTrue(a.popup_events[0]['cleared'])

    def test_entry_closes_both_popups_and_continues_without_home_or_confirming_trial(self):
        a,state,inputs=self.task();a.f.home=Mock(side_effect=AssertionError('must not go home'))
        def click(target):
            inputs.append((state['key'],tuple(target['box'])))
            state['key']='victory' if state['key']=='trial' else 'panel'
        a.f.click_item=click
        self.assertEqual(a.run(),'opened')
        self.assertEqual(inputs,[('trial',(1135,696,121,41)),('victory',(846,714,194,51))])
        self.assertTrue(all(e['cleared'] for e in a.popup_events));a.f.home.assert_not_called()

    def fight_route(self,route,persistent=False):
        a,state,inputs=self.task('panel');index=0
        board=dict(remaining=6,cards=[])
        daily=ArenaDaily(a,'休闲战斗');daily.board=lambda:board if state['key']=='panel' else None
        def click(target):
            nonlocal index
            inputs.append((state['key'],tuple(target['box'])))
            if state['key']=='panel':state['key']=route[0]
            elif not persistent:
                index+=1;state['key']=route[index] if index<len(route) else 'panel'
        a.f.click_item=click
        if persistent:
            a.stable_panel=lambda:a.wait('返回竞技场',a.panel,seconds=1)
            with self.assertRaises(TimeoutError):daily.fight(board)
            self.assertEqual(daily.battles,0)
        else:
            self.assertEqual(daily.fight(board),'victory');self.assertEqual(daily.battles,1)
            self.assertEqual(state['key'],'panel')
            self.assertTrue(all(e['cleared'] for e in a.popup_events))
        return a,inputs

    def test_battle_victory_and_trial_in_both_orders_count_only_once(self):
        for route in (['victory','trial'],['trial','victory'],['generic','victory','trial'],['blue','victory','trial']):
            with self.subTest(route=route):
                a,inputs=self.fight_route(route)
                self.assertEqual([key for key,box in inputs],['panel']+route)
                self.assertEqual(sum(key=='trial' for key,box in inputs),1)
                self.assertEqual(len(a.popup_events),2)

    def test_sent_victory_confirmation_is_not_repeated_while_waiting_for_return(self):
        _,inputs=self.fight_route(['victory'],persistent=True)
        self.assertEqual([key for key,box in inputs],['panel','victory'])

    def test_blue_confirmation_is_not_replayed_if_return_never_happens(self):
        _,inputs=self.fight_route(['blue'],persistent=True)
        self.assertEqual([key for key,box in inputs],['panel','blue'])

    def test_two_blue_confirm_battles_continue_to_configured_cap(self):
        a,state,inputs=self.task('panel');a.f.cfg['arenaBattleLimit']=2
        board=dict(remaining=6,cards=[])
        transitions={'panel':'blue','blue':'victory','victory':'trial','trial':'panel'}
        def click(target):
            inputs.append((state['key'],tuple(target['box'])));state['key']=transitions[state['key']]
        a.f.click_item=click
        with tempfile.TemporaryDirectory(prefix='arena-blue-confirm-',dir=ROOT/'verification') as temp,patch('arena_daily.ROOT',Path(temp)):
            daily=ArenaDaily(a,'休闲战斗');daily.board=lambda:board if state['key']=='panel' else None
            self.assertEqual(daily.run(),'battle_limit_done')
            report=json.loads((daily.folder/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['battles'],2);self.assertEqual(report['battleLimit'],2)
            self.assertEqual([key for key,box in inputs],['panel','blue','victory','trial']*2)
            self.assertTrue(all(e['cleared'] for e in report['popupEvents']))
            self.evidence.append(dict(kind='blue-confirm-two-battles',battles=report['battles'],
                                     inputKinds=[key for key,box in inputs],result=report['result']))

    def test_blue_confirmation_reference_is_an_unscaled_original_crop(self):
        ref=json.loads((ROOT/'resources/local/arena_popup_references/battle-victory-confirm-20261025.json').read_text(encoding='utf-8'))
        self.assertFalse(ref['runtimeTemplate'])
        self.assertEqual(hashlib.sha256((ROOT/ref['source']).read_bytes()).hexdigest(),ref['sourceSha256'])
        self.assertEqual(hashlib.sha256((ROOT/ref['game']).read_bytes()).hexdigest(),ref['gameSha256'])
        self.assertEqual(Image.open(ROOT/ref['source']).convert('RGB').crop(ref['gameCrop']).tobytes(),
                         Image.open(ROOT/ref['game']).convert('RGB').tobytes())

    def test_popup_asset_sources_and_crops_are_original_pixels(self):
        manifest=json.loads((ROOT/'resources/local/arena/popups/sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['assets']),4);self.assertEqual(len(manifest['references']),2)
        for ref in manifest['references']:
            self.assertEqual(hashlib.sha256((ROOT/ref['path']).read_bytes()).hexdigest(),ref['sha256'])
            expected=Image.open(ROOT/ref['path']).convert('RGB').crop(ref['gameCrop'])
            self.assertEqual(expected.tobytes(),Image.open(ROOT/ref['game']).convert('RGB').tobytes())
        for record in manifest['assets']:
            original=ROOT/record['source'];asset=ROOT/record['path']
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),record['sourceSha256'])
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(),record['sha256'])
            self.assertEqual(Image.open(original).convert('RGB').crop(record['box']).tobytes(),
                             Image.open(asset).convert('RGB').tobytes())


if __name__=='__main__':unittest.main()
