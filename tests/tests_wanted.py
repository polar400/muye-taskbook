"""Wanted task: simulated navigation, real supplied images; no game IO."""
import hashlib
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from wanted_task import WantedTask
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
BOXES={
 'wanted_kunai':([44,193,57,59],(0,142)),
 'wanted_daily':([297,55,205,78],(230,20)),
 'wanted_row':([311,337,166,54],(268,162)),
 'wanted_participate':([1267,689,173,52],(1152,609)),
 'wanted_title':([812,111,343,73],(614,60)),
 'wanted_counter':([821,255,238,38],(672,192)),
 'wanted_auto':([1230,248,175,55],(1152,203)),
 'wanted_close':([1530,167,53,52],(1440,121)),
}


class GameOCR:
    def __init__(self,game):self.g=game

    def match(self,image,name,threshold=.9):
        g=self.g
        if name.startswith('entry_'):
            return [{'box':[0,0,1,1]}] if g.page in ('home','panel') else []
        visible={'home':{'wanted_kunai'},'daily':{'wanted_daily','wanted_row'},
                 'selected':{'wanted_daily','wanted_row','wanted_participate'},
                 'panel':{'wanted_title','wanted_counter','wanted_auto','wanted_close'}}
        if name not in visible.get(g.page,set()):return []
        box,offset=BOXES[name];x,y,w,h=box;ox,oy=offset
        value={'box':[x-ox,y-oy,w,h],'template':name,'score':.99}
        return [value,dict(value,box=[x-ox+40,y-oy,w,h])] if g.ambiguous==name else [value]

    def read(self,image,only_rec=False):
        g=self.g
        if only_rec:return [{'text':'?' if g.bad_count else str(g.count),'score':.99,'box':[0,0,1,1]}]
        full=image.shape[:2]==(1015,1920)
        if g.page=='selected':return [{'text':'通缉任务','box':[1170,160,130,40],'score':.99}]
        if g.page=='dialog':
            return [{'text':g.question,'box':[700,400,400,40] if full else [220,96,400,40],'score':.99},
                    {'text':'是','box':[860,600,40,30] if full else [380,296,40,30],'score':.99}]
        return []


class Game(LocalFlows):
    def __init__(self,page='home',count=5):
        self.page=page;self.count=count;self.time=0
        self.inputs=[];self.events=[];self.progress=[]
        self.ambiguous=None;self.uncertain=None;self.ignore_close=False
        self.bad_count=False
        self.question='是否自动完成全部通缉任务？'
        self.delay_dialog=0;self.dialog_frames=0
        self.stop=False;self.pause_once=False
        self.sequence=[('battle',5),('panel',4),('battle',4),('panel',1),('battle',1),('panel',0),('panel',0)]
        self.tick=1;self.auto_started=False
        super().__init__(Mock(),GameOCR(self),{},self.check,lambda kind,message,**kw:self.events.append((kind,message,kw)))

    def check(self):
        if self.auto_started and self.stop:raise RuntimeError('已停止')
        if self.auto_started and self.pause_once:self.time+=3600;self.pause_once=False

    def capture_ready(self):
        self.time+=self.tick if self.auto_started else 1
        if self.dialog_frames:
            self.dialog_frames-=1
            self.page='dialog' if not self.dialog_frames else 'battle'
        elif self.auto_started and self.sequence:
            self.page,self.count=self.sequence.pop(0)
            self.progress.append((self.page,self.count))
        return np.full((1015,1920,3),10,dtype=np.uint8)

    def click_item(self,item,delay=.6):
        self.checkpoint()
        name=item.get('template','yes')
        self.inputs.append(name)
        if name=='wanted_kunai':self.page='daily'
        elif name=='wanted_daily':self.page='daily'
        elif name=='wanted_row':self.page='selected'
        elif name=='wanted_participate':self.page='panel'
        elif name=='wanted_auto':
            self.dialog_frames=self.delay_dialog
            self.page='battle' if self.delay_dialog else 'dialog'
        elif name=='yes':self.auto_started=True;self.page='battle'
        elif name=='wanted_close' and not self.ignore_close:self.page='home';self.auto_started=False
        if name==self.uncertain:raise RuntimeError('输入发送结果未知')


class WantedFlowTests(unittest.TestCase):
    def run_game(self,game):
        original=game.checkpoint
        task=WantedTask(game);task.clock=lambda:game.time
        task.sleep=lambda seconds:setattr(game,'time',game.time+seconds)
        try:task.run()
        finally:
            self.assertEqual(game.checkpoint,original)
            game.window.click.assert_not_called()
        return task

    def test_full_navigation_one_auto_one_yes_then_observed_zero_and_home(self):
        game=Game();self.run_game(game)
        self.assertEqual(game.inputs,['wanted_kunai','wanted_daily','wanted_row','wanted_participate','wanted_auto','yes','wanted_close'])
        self.assertEqual((game.page,game.count),('home',0))
        self.assertIn(('panel',1),game.progress)
        self.assertIn('已确认今日余下次数0',game.events[-1][1])

    def test_existing_panel_resumes_without_navigation_or_claim_inputs(self):
        game=Game(page='panel');self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes','wanted_close'])

    def test_unreadable_existing_panel_never_falls_through_to_home(self):
        game=Game(page='panel');game.bad_count=True
        game.home=Mock(side_effect=AssertionError('已有面板时不能重走主页入口'))
        with self.assertRaisesRegex(TimeoutError,'复核已有通缉面板次数'):self.run_game(game)
        self.assertEqual(game.inputs,[])
        game.home.assert_not_called()

    def test_zero_count_skips_auto_and_yes(self):
        game=Game(page='panel',count=0);self.run_game(game)
        self.assertEqual(game.inputs,['wanted_close'])

    def test_last_one_is_not_completion(self):
        game=Game(page='panel',count=1)
        game.sequence=[('battle',1),('panel',0),('panel',0)]
        self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes','wanted_close'])
        self.assertEqual(game.count,0)

    def test_delayed_dialog_does_not_repeat_auto(self):
        game=Game(page='panel');game.delay_dialog=4;self.run_game(game)
        self.assertEqual(game.inputs.count('wanted_auto'),1)
        self.assertEqual(game.inputs.count('yes'),1)

    def test_zero_must_be_seen_on_two_consecutive_panel_frames(self):
        game=Game(page='panel')
        game.sequence=[('panel',0),('battle',0),('panel',0),('panel',0)]
        self.run_game(game)
        self.assertEqual(game.progress,[('panel',0),('battle',0),('panel',0),('panel',0)])

    def test_paid_dialog_stops_without_yes(self):
        game=Game(page='panel');game.question='是否花费100元宝自动完成？'
        with self.assertRaisesRegex(RuntimeError,'消耗提示'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto'])

    def test_unrelated_yes_dialog_is_not_confirmed(self):
        game=Game(page='panel');game.question='是否放弃当前任务？'
        with self.assertRaisesRegex(TimeoutError,'确认免费'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto'])

    def test_real_solo_warning_wording_completes_the_simulated_flow(self):
        game=Game(page='panel')
        game.question='你现在为单人状态，继续进行通缉任务将无法获得双倍经验奖励，是否继续本操作？'
        original=game.ocr.read
        def read(image,only_rec=False):
            words=original(image,only_rec)
            if game.page=='dialog' and not only_rec:
                full=image.shape[:2]==(1015,1920)
                words.append({'text':'否','score':.99,'box':[1100,600,40,30] if full else [620,296,40,30]})
            return words
        game.ocr.read=read
        self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes','wanted_close'])
        self.assertEqual((game.page,game.count),('home',0))

    def test_ambiguous_button_stops_without_click(self):
        game=Game(page='panel');game.ambiguous='wanted_auto'
        with self.assertRaisesRegex(RuntimeError,'不唯一'):self.run_game(game)
        self.assertEqual(game.inputs,[])

    def test_uncertain_send_is_not_repeated(self):
        game=Game(page='panel');game.uncertain='wanted_auto'
        with self.assertRaisesRegex(RuntimeError,'发送结果未知'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto'])

    def test_increasing_count_stops(self):
        game=Game(page='panel');game.sequence=[('panel',3),('panel',4)]
        with self.assertRaisesRegex(RuntimeError,'次数异常增加'):self.run_game(game)
        self.assertNotIn('wanted_close',game.inputs)

    def test_never_zero_times_out_without_further_inputs(self):
        game=Game(page='panel');game.sequence=[('panel',1)];game.tick=61
        with self.assertRaisesRegex(TimeoutError,'今日余下次数0'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes'])

    def test_failed_close_not_mistaken_for_home_background(self):
        game=Game(page='panel',count=0);game.ignore_close=True
        with self.assertRaisesRegex(TimeoutError,'返回木叶村'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_close'])

    def test_stop_during_auto_never_reports_completion(self):
        game=Game(page='panel');game.stop=True
        with self.assertRaisesRegex(RuntimeError,'已停止'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes'])

    def test_pause_is_excluded_from_wait_budget(self):
        game=Game(page='panel');game.pause_once=True
        task=self.run_game(game)
        self.assertGreaterEqual(task.paused,3600)
        self.assertEqual(game.inputs.count('yes'),1)


class CompletedActivityGame(Game):
    def __init__(self,page='completed',**kwargs):
        super().__init__(page=page,**kwargs)
        original=self.ocr.match
        def match(image,name,threshold=.9):
            if self.page=='completed':
                boxes={'wanted_daily':([297,56,205,78],(230,20)),
                       'wanted_daily_selected':([297,56,205,78],(230,20)),
                       'wanted_daily_completed_rows':([320,335,146,138],(268,304)),
                       'close':([1622,21,46,50],(1536,0))}
                if name not in boxes:return []
                box,(ox,oy)=boxes[name];x,y,w,h=box
                return [{'box':[x-ox,y-oy,w,h],'score':.99,'template':name}]
            return original(image,name,threshold)
        self.ocr.match=match
        # Simulated waits must not retain a fresh 6 MB frame in every Mock call.
        self.window.save=lambda *args:None

    def click_item(self,item,delay=.6):
        if item.get('template')=='wanted_daily' and self.page=='completed':
            self.inputs.append('wanted_daily')
        elif item.get('template')=='close':
            self.checkpoint();self.inputs.append('close')
            if not self.ignore_close:self.page='home';self.auto_started=False
            if self.uncertain=='close':raise RuntimeError('输入发送结果未知')
        else:super().click_item(item,delay)


class WantedCompletedActivityTests(unittest.TestCase):
    run_game=WantedFlowTests.run_game

    def test_absent_entry_closes_activity_then_allows_next_task(self):
        game=CompletedActivityGame()
        game.wanted=lambda:self.run_game(game)
        def next_task():
            self.assertEqual(game.page,'home')
            return 'accepted'
        game.escort=Mock(side_effect=next_task)
        worker=ast.parse((ROOT/'src/native_worker.py').read_text(encoding='utf-8'))
        main=next(n for n in worker.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        loop=next(n for n in main.body if isinstance(n,ast.For) and any(isinstance(x,ast.Try) for x in n.body))
        events=[]
        # Execute the unchanged real queue loop with simulated task IO only.
        env={'cfg':{'tasks':['wanted','escort']},'tasks':{'wanted':'通缉任务','escort':'押镖'},
             'flow':game,'checkpoint':lambda:None,'run_ranked_pipeline':Mock(),
             'emit':lambda kind,message,**kw:events.append((kind,message,kw))}
        exec(compile(ast.Module(body=[loop],type_ignores=[]),str(ROOT/'src/native_worker.py'),'exec'),env)
        self.assertEqual(game.inputs,['wanted_daily','close'])
        self.assertEqual(game.page,'home')
        game.escort.assert_called_once()
        self.assertEqual([(e[2]['id'],e[2]['status']) for e in events],
                         [('wanted','running'),('wanted','done'),('escort','running'),('escort','accepted')])

    def test_auto_finishes_into_activity_without_a_zero_counter(self):
        game=CompletedActivityGame(page='panel')
        game.sequence=[('panel',2),('completed',0),('completed',0)]
        self.run_game(game)
        self.assertEqual(game.inputs,['wanted_auto','yes','close'])
        self.assertEqual(game.page,'home')

    def test_transient_absent_page_needs_two_consecutive_frames(self):
        game=CompletedActivityGame(page='panel')
        game.sequence=[('completed',2),('battle',2),('completed',1),('completed',0)]
        self.run_game(game)
        self.assertEqual(game.progress,[('completed',2),('battle',2),('completed',1),('completed',0)])
        self.assertEqual(game.inputs,['wanted_auto','yes','close'])

    def test_missing_layout_does_not_turn_unknown_into_success(self):
        game=CompletedActivityGame();original=game.ocr.match
        game.ocr.match=lambda image,name,threshold=.9:[] if name=='wanted_daily_completed_rows' else original(image,name,threshold)
        with self.assertRaisesRegex(TimeoutError,'通缉条目或已完成'):self.run_game(game)
        self.assertEqual(game.inputs,['wanted_daily'])

    def test_close_failure_or_unknown_send_cannot_continue(self):
        for unknown in (False,True):
            with self.subTest(unknown=unknown):
                game=CompletedActivityGame()
                game.ignore_close=not unknown;game.uncertain='close' if unknown else None
                with self.assertRaisesRegex((RuntimeError,TimeoutError),'返回木叶村|发送结果未知'):
                    self.run_game(game)
                self.assertEqual(game.inputs,['wanted_daily','close'])


class WantedConfirmationTests(unittest.TestCase):
    warning='你现在为单人状态，继续进行通缉任务将无法获得双倍经验奖励，是否继续本操作？'

    def task(self,text=None,extra=None):
        f=LocalFlows(Mock(),Mock(),{},lambda:None,Mock())
        f.image=np.zeros((1015,1920,3),dtype=np.uint8);f.items=[]
        # Coordinates here are relative to the central OCR crop (480,304).
        words=[{'text':self.warning if text is None else text,'box':[250,150,460,50],'score':.99},
               {'text':'是','box':[340,245,24,25],'score':.99},
               {'text':'否','box':[595,247,24,25],'score':.99}]
        if extra is not None:extra(words)
        f.ocr.read.return_value=words
        return WantedTask(f)

    def test_solo_warning_accepts_line_breaks_and_irrelevant_ocr_typo(self):
        t=self.task(self.warning.replace('继续进行','继耗续进行').replace('双倍经验','双倍\n经验'))
        self.assertEqual(t.confirmation()['box'],[820,549,24,25])
        t.f.window.click.assert_not_called()

    def test_solo_warning_needs_each_local_semantic_feature(self):
        for fragment in ('单人状态','通缉任务','无法获得双倍经验','是否继续'):
            with self.subTest(fragment=fragment):
                t=self.task(self.warning.replace(fragment,''))
                self.assertIsNone(t.confirmation())
                t.f.window.click.assert_not_called()

    def test_solo_warning_needs_unique_right_hand_no_on_same_row(self):
        def remove(words):words.pop()
        def duplicate(words):words.append(dict(words[-1]))
        def wrong_row(words):words[-1]['box']=[595,310,24,25]
        def wrong_side(words):words[-1]['box']=[200,247,24,25]
        for change in (remove,duplicate,wrong_row,wrong_side):
            with self.subTest(change=change.__name__):
                t=self.task(extra=change)
                self.assertIsNone(t.confirmation())
                t.f.window.click.assert_not_called()

    def test_solo_warning_paid_or_multiple_yes_never_clicks(self):
        t=self.task(self.warning+'消耗100元宝')
        with self.assertRaisesRegex(RuntimeError,'消耗提示'):t.confirmation()
        t.f.window.click.assert_not_called()
        t=self.task(extra=lambda words:words.append({'text':'是','box':[420,245,24,25],'score':.99}))
        with self.assertRaisesRegex(RuntimeError,'不唯一'):t.confirmation()
        t.f.window.click.assert_not_called()

    def test_background_warning_cannot_authorize_unrelated_local_dialog(self):
        t=self.task('是否放弃当前任务？')
        t.f.items=[{'text':self.warning,'box':[700,450,460,40],'score':.99}]
        self.assertIsNone(t.confirmation())
        t.f.window.click.assert_not_called()


class WantedImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ocr=LocalOCR()

    def task(self,path):
        f=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
        f.image=np.array(Image.open(ROOT/path).convert('RGB'))[:,:,::-1].copy()
        f.items=self.ocr.read(f.image)
        return WantedTask(f)

    def test_supplied_panel_reads_five_and_finds_auto_and_close(self):
        t=self.task('resources/local/wanted/panel-game.png')
        self.assertEqual(t.panel_count(),5)
        self.assertEqual(t.button('wanted_auto',(.6,.2,.75,.32))['box'],[1230,248,175,55])
        self.assertEqual(t.button('wanted_close',(.75,.12,.86,.24))['box'],[1530,167,53,52])
        t.f.window.click.assert_not_called()

    def test_saved_home_and_activity_scene_locate_supplied_controls(self):
        t=self.task('resources/local/catalog/home/20261016-973-village/game.png')
        self.assertIsNotNone(t.button('wanted_kunai',(0,.14,.1,.3)))
        t=self.task('resources/local/catalog/activities/20261016-973-daily/game.png')
        for name,roi in [('wanted_daily',(.12,.02,.4,.16)),('wanted_row',(.14,.16,.3,.74)),
                         ('wanted_participate',(.6,.6,.8,.78))]:self.assertIsNotNone(t.button(name,roi))
        self.assertFalse(t.selected_row())  # Actual saved right pane is arena.
        t.f.window.click.assert_not_called()

    def test_real_glowing_kunai_failure_still_locates_the_icon(self):
        t=self.task('出错任务/通缉任务/证据/d6cbca467d3d9838eee51fd5.png')
        button=t.button('wanted_kunai',(0,.14,.1,.3))
        self.assertIsNotNone(button)
        x,y,w,h=button['box']
        self.assertTrue(44<=x+w/2<=101 and 193<=y+h/2<=252)
        t.f.window.click.assert_not_called()

    def test_real_completed_activity_has_a_verified_close_target(self):
        sources=json.loads((ROOT/'resources/local/wanted/completed-activity-sources.json').read_text(encoding='utf-8'))
        for source in sources['sources']:
            with self.subTest(source=source['path']):
                t=self.task('出错任务/通缉任务/证据/c3f691628bbbdc5d990d88a4.png')
                t.f.image=np.array(Image.open(ROOT/source['path']).convert('RGB').crop(source['gameBox']))[:,:,::-1].copy()
                t.f.items=self.ocr.read(t.f.image)
                self.assertIsNone(t.button('wanted_row',(.14,.16,.3,.74)))
                self.assertEqual(t.completed_activity_close()['box'],[1622,21,46,50])
                t.f.window.click.assert_not_called()

    def test_completed_activity_rejects_missing_features_or_dialog(self):
        for feature in ('selected-tab','rows','close','wanted-text','dialog'):
            with self.subTest(feature=feature):
                t=self.task('出错任务/通缉任务/证据/c3f691628bbbdc5d990d88a4.png')
                if feature=='selected-tab':t.f.image[50:140,290:510]=0
                elif feature=='rows':t.f.image[330:475,310:475]=0
                elif feature=='close':t.f.image[15:80,1615:1675]=0
                elif feature=='wanted-text':t.f.items.append({'text':'通缉任务','score':.99,'box':[350,350,120,35]})
                else:t.f.items.append({'text':'是','score':.99,'box':[820,550,30,25]})
                self.assertIsNone(t.completed_activity_close())
                t.f.window.click.assert_not_called()

    def test_active_wanted_entry_is_never_completed_activity(self):
        for path in ('resources/local/catalog/activities/20261016-973-daily/game.png',
                     '出错任务/通缉任务/证据/831508e2d050f1b570feb564.png'):
            with self.subTest(path=path):
                t=self.task(path)
                self.assertIsNotNone(t.button('wanted_row',(.14,.16,.3,.74)))
                self.assertIsNone(t.completed_activity_close())
                t.f.window.click.assert_not_called()

    def test_completed_activity_source_pixels_and_hashes(self):
        sources=json.loads((ROOT/'resources/local/wanted/completed-activity-sources.json').read_text(encoding='utf-8'))
        for source in sources['sources']:
            self.assertEqual(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest(),source['sha256'])
        for asset in sources['assets']:
            self.assertEqual(hashlib.sha256((ROOT/asset['path']).read_bytes()).hexdigest(),asset['sha256'])
            self.assertTrue(np.array_equal(np.array(Image.open(ROOT/asset['source']).convert('RGB').crop(asset['sourceBox'])),
                                           np.array(Image.open(ROOT/asset['path']).convert('RGB'))))

    def test_real_completed_activity_closes_once_and_verifies_home(self):
        t=self.task('出错任务/通缉任务/证据/c3f691628bbbdc5d990d88a4.png')
        activity=t.f.image.copy()
        home=np.array(Image.open(ROOT/'resources/local/catalog/home/20261016-973-village/game.png').convert('RGB'))[:,:,::-1].copy()
        t.f.capture_ready=Mock(side_effect=[activity,home])
        with patch('local_flows.time.sleep'):
            t.complete_from_activity()
        t.f.window.click.assert_called_once_with(1645,46)
        self.assertEqual(t.f.capture_ready.call_count,2)
        with self.assertRaisesRegex(RuntimeError,'拒绝重复'):
            t.complete_from_activity()
        t.f.window.click.assert_called_once()

    def confirmation_frames(self):
        sources=json.loads((ROOT/'resources/local/wanted/confirmation-sources.json').read_text(encoding='utf-8'))
        for source in sources['sources']:
            path=ROOT/source['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),source['sha256'])
            yield source['path'],np.array(Image.open(path).convert('RGB').crop(source['gameBox']))[:,:,::-1].copy()

    def test_real_solo_confirmation_images_locate_yes(self):
        for source,image in self.confirmation_frames():
            with self.subTest(source=source):
                f=LocalFlows(Mock(),self.ocr,{},lambda:None,Mock())
                f.image=image;f.items=self.ocr.read(image)
                target=WantedTask(f).confirmation()
                self.assertIsNotNone(target)
                x,y,w,h=target['box']
                self.assertTrue(756<=x+w//2<=908 and 537<=y+h//2<=585)
                f.window.click.assert_not_called()

    def test_real_solo_confirmation_sends_only_one_mock_yes(self):
        t=self.task('出错任务/通缉任务/证据/31bbb72819c67c03690bf62e.png')
        t.f.observe=Mock(return_value=t.f.items)
        t.clock=lambda:0;t.sleep=lambda seconds:None
        # Do not loop on the unfixed recognizer while reproducing the symptom.
        self.assertIsNotNone(t.confirmation())
        with patch('local_flows.time.sleep'):
            t.click('确认免费自动完成（是）',t.confirmation)
        x,y=t.f.window.click.call_args.args
        self.assertTrue(756<=x<=908 and 537<=y<=585)
        t.f.window.click.assert_called_once()
        with self.assertRaisesRegex(RuntimeError,'拒绝重复'):
            t.click('确认免费自动完成（是）',t.confirmation)
        t.f.window.click.assert_called_once()

    def test_real_selected_wanted_details_authorize_only_the_participate_button(self):
        for sid in ('1f8d0f82033e65724af5aade','831508e2d050f1b570feb564'):
            with self.subTest(sid=sid):
                t=self.task('出错任务/通缉任务/证据/'+sid+'.png')
                self.assertIsNotNone(t.button('wanted_participate',(.6,.6,.8,.78)))
                self.assertTrue(t.selected_row())
                t.f.window.click.assert_not_called()

    def test_real_selected_detail_art_needs_no_ocr_transcription(self):
        t=self.task('出错任务/通缉任务/证据/831508e2d050f1b570feb564.png')
        t.f.items=[]
        t.f.ocr=Mock(wraps=self.ocr)
        t.f.ocr.read.side_effect=AssertionError('标题素材已确认，不依赖美术字OCR')
        self.assertTrue(t.selected_row())
        t.f.ocr.read.assert_not_called()
        t.f.window.click.assert_not_called()

    def test_real_participate_failure_sends_one_targeted_mock_click(self):
        for sid in ('1f8d0f82033e65724af5aade','831508e2d050f1b570feb564'):
            with self.subTest(sid=sid):
                t=self.task('出错任务/通缉任务/证据/'+sid+'.png')
                t.f.observe=Mock(return_value=t.f.items)
                reader=lambda:t.button('wanted_participate',(.6,.6,.8,.78)) if t.selected_row() else None
                with patch('local_flows.time.sleep'):
                    t.click('参与通缉任务',reader)
                t.f.window.click.assert_called_once_with(1353,715)
                with self.assertRaisesRegex(RuntimeError,'拒绝重复'):
                    t.click('参与通缉任务',reader)
                t.f.window.click.assert_called_once()

    def test_kunai_core_moves_with_image_and_rejects_duplicate_or_outside_roi(self):
        t=self.task('出错任务/通缉任务/证据/d6cbca467d3d9838eee51fd5.png')
        core=t.f.image[208:242,50:94].copy()
        t.f.image[:]=0
        t.f.image[210:244,100:144]=core
        self.assertEqual(t.button('wanted_kunai',(0,.14,.1,.3))['box'],[100,210,44,34])
        t.f.image[170:204,10:54]=core
        with self.assertRaisesRegex(RuntimeError,'不唯一'):t.button('wanted_kunai',(0,.14,.1,.3))
        t.f.image[:]=0
        t.f.image[210:244,500:544]=core
        self.assertIsNone(t.button('wanted_kunai',(0,.14,.1,.3)))
        t.f.window.click.assert_not_called()

    def test_detail_title_outside_right_pane_cannot_authorize_participation(self):
        t=self.task('出错任务/通缉任务/证据/831508e2d050f1b570feb564.png')
        title=t.f.image[154:186,1185:1308].copy()
        t.f.image[:]=0;t.f.image[154:186,300:423]=title;t.f.items=[]
        self.assertFalse(t.selected_row())
        t.f.window.click.assert_not_called()

    def test_navigation_template_provenance(self):
        manifest=json.loads((ROOT/'resources/local/wanted/navigation-template-sources.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['threshold'],.9)
        for a in manifest['assets']:
            self.assertEqual(hashlib.sha256((ROOT/a['source']).read_bytes()).hexdigest(),a['sourceSha256'])
            self.assertEqual(hashlib.sha256((ROOT/a['path']).read_bytes()).hexdigest(),a['sha256'])
            expected=np.array(Image.open(ROOT/a['source']).convert('RGB').crop(a['sourceBox']))
            self.assertTrue(np.array_equal(expected,np.array(Image.open(ROOT/a['path']))))

    def test_non_wanted_scenes_never_supply_a_count(self):
        for path in ['resources/local/ranked-1920-calibration.png','resources/local/battle-settlement-calibration.png',
                     'resources/local/catalog/home/20261016-973-village/game.png']:
            with self.subTest(path=path):
                t=self.task(path);self.assertIsNone(t.panel_count());t.f.window.click.assert_not_called()

    def test_counter_conflict_low_score_or_letters_are_not_guessed(self):
        t=self.task('resources/local/wanted/panel-game.png')
        for pair in [('5','0'),('s','s'),('0','0')]:
            with self.subTest(pair=pair):
                proxy=Mock(wraps=self.ocr)
                proxy.read.side_effect=[[{'text':v,'score':.7 if pair==('0','0') else .99}] for v in pair]
                t.f.ocr=proxy
                if pair==('5','0'):
                    with self.assertRaisesRegex(RuntimeError,'次数识别冲突'):t.panel_count()
                else:self.assertIsNone(t.panel_count())
        t.f.window.click.assert_not_called()

    def test_asset_provenance_and_reused_crops(self):
        manifest=json.loads((ROOT/'resources/local/wanted/manifest.json').read_text(encoding='utf-8'))
        for source in manifest['sources'].values():
            self.assertEqual(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest(),source['sha256'])
        for asset in manifest['assets']:
            path=ROOT/asset['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),asset['sha256'])
            if 'reusedFrom' in asset:self.assertEqual(path.read_bytes(),(ROOT/asset['reusedFrom']).read_bytes())
            else:
                source=ROOT/manifest['sources'][asset['source']]['path']
                expected=np.array(Image.open(source).convert('RGB').crop(asset['sourceBox']))
                self.assertTrue(np.array_equal(expected,np.array(Image.open(path))))


if __name__=='__main__':unittest.main()
