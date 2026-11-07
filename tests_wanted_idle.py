"""Quiet wanted progress and stable-home completion; simulated IO only."""
import ast
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from wanted_task import WantedTask
from tests_wanted import Game
import tests_wanted
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent
QUESTS=[{'text':'任务列表','box':[1662,487,84,28],'score':.99},
        {'text':'[支线]等级达到100级','box':[1636,602,164,20],'score':.99},
        {'text':'[支线]通关剧情副本','box':[1634,668,204,25],'score':.99}]


class IdleGame(Game):
    def __init__(self):
        super().__init__(page='panel');self.sequence=[('battle',5),('panel',4),('home',1)]
        original=self.ocr.read
        self.ocr.read=lambda image,only_rec=False:QUESTS if self.page=='home' and not only_rec else original(image,only_rec)


class WantedIdleTests(unittest.TestCase):
    run_game=tests_wanted.WantedFlowTests.run_game

    def task(self):
        game=IdleGame();game.page='home';game.image=np.full((1015,1920,3),50,dtype=np.uint8);game.items=list(QUESTS)
        task=WantedTask(game);task.clock=lambda:game.time
        task.sent.add('确认免费自动完成（是）')
        return task,game

    def test_no_per_count_decrement_log_and_original_zero_path_still_finishes(self):
        game=Game(page='panel');self.run_game(game)
        self.assertFalse(any('今日余下次数' in message and '→' in message for _,message,_ in game.events))
        self.assertEqual(game.page,'home')
        self.assertEqual(game.inputs,['wanted_auto','yes','wanted_close'])

    def test_stable_home_needs_ten_active_seconds_and_three_frames(self):
        task,game=self.task()
        for now,expected in ((0,False),(5,False),(9.9,False),(10,True)):
            game.time=now;self.assertEqual(task.idle_home_completed(),expected)

    def test_initial_home_or_unconfirmed_auto_is_not_completion(self):
        task,game=self.task();task.sent.clear()
        for now in (0,10,30):game.time=now;self.assertFalse(task.idle_home_completed())

    def test_active_wanted_quest_dialog_missing_panel_or_scene_motion_resets_timer(self):
        for kind in ('quest','dialog','no_panel','motion','battle'):
            with self.subTest(kind=kind):
                task,game=self.task();self.assertFalse(task.idle_home_completed());game.time=9
                if kind=='quest':game.items=QUESTS+[{'text':'[通缉]击败佩恩 自动','box':[1650,563,200,25],'score':.99}]
                elif kind=='dialog':game.items=QUESTS+[{'text':'是','box':[800,500,30,25],'score':.99}]
                elif kind=='no_panel':game.items=[]
                elif kind=='motion':game.image[324:730,614:1267]=100
                else:game.page='battle'
                self.assertFalse(task.idle_home_completed())
                game.page='home';game.items=list(QUESTS);game.image[:]=50;game.time=10
                self.assertFalse(task.idle_home_completed())

    def test_pause_does_not_count_as_idle_time(self):
        task,game=self.task();task.idle_home_completed()
        game.time=3605;task.paused=3600
        self.assertFalse(task.idle_home_completed())
        game.time=3610;self.assertTrue(task.idle_home_completed())

    def test_home_terminal_continues_actual_worker_queue_without_extra_click(self):
        game=IdleGame();game.wanted=lambda:self.run_game(game)
        original_match=game.ocr.match
        def match(image,name,threshold=.9):
            if name=='wanted_autopath':return [{'box':[160,50,249,49],'score':.99}] if game.time<20 else []
            return original_match(image,name,threshold)
        game.ocr.match=match
        game.escort=Mock(side_effect=lambda:'accepted' if game.page=='home' else None)
        worker=ast.parse((ROOT/'native_worker.py').read_text(encoding='utf-8'))
        main=next(n for n in worker.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        loop=next(n for n in main.body if isinstance(n,ast.For) and any(isinstance(x,ast.Try) for x in n.body))
        events=[];env={'cfg':{'tasks':['wanted','escort']},'tasks':{'wanted':'通缉任务','escort':'押镖'},
                      'flow':game,'checkpoint':lambda:None,'run_ranked_pipeline':Mock(),
                      'emit':lambda kind,message,**kw:events.append((kind,message,kw))}
        exec(compile(ast.Module(body=[loop],type_ignores=[]),str(ROOT/'native_worker.py'),'exec'),env)
        self.assertEqual(game.inputs,['wanted_auto','yes'])
        self.assertGreaterEqual(game.time,30);game.escort.assert_called_once()
        self.assertEqual([(e[2]['id'],e[2]['status']) for e in events],
                         [('wanted','running'),('wanted','done'),('escort','running'),('escort','accepted')])

    def test_supplied_home_pixels_and_ocr_qualify_without_wanted_task_or_panel(self):
        ocr=LocalOCR();path=ROOT/'resources/local/wanted/idle-home-game.png'
        image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock());flow.image=image;flow.items=ocr.read(image)
        task=WantedTask(flow);task.sent.add('确认免费自动完成（是）');clock=[0];task.clock=lambda:clock[0]
        for now,expected in ((0,False),(5,False),(10,True)):
            clock[0]=now;self.assertEqual(task.idle_home_completed(),expected)
        flow.window.click.assert_not_called()
        source=json.loads((ROOT/'resources/local/wanted/idle-home-sources.json').read_text(encoding='utf-8'))
        raw=path.parent/source['sourceImage']
        self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(),source['sourceSha256'])
        self.assertEqual(np.array(Image.open(raw).convert('RGB').crop(source['gameCrop'])).tobytes(),image[:,:,::-1].tobytes())

    def test_real_autopath_art_cannot_finish_even_when_ocr_misses_it_and_scene_is_static(self):
        ocr=LocalOCR();image=np.array(Image.open(ROOT/'resources/local/wanted/autopath-home-game.png').convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock());flow.image=image;flow.items=list(QUESTS)
        task=WantedTask(flow);task.sent.add('确认免费自动完成（是）');clock=[0];task.clock=lambda:clock[0]
        # Isolate the new guard even if the banner itself obscures a home icon.
        with patch.object(task,'home_visible',return_value=True):
            for now in (0,5,10,40):
                clock[0]=now;self.assertFalse(task.idle_home_completed())
        flow.window.click.assert_not_called()

    def test_autopath_reappearance_resets_the_whole_ten_second_window(self):
        task,game=self.task();present=[False];original=game.ocr.match
        def match(image,name,threshold=.9):
            if name=='wanted_autopath':return [{'box':[160,50,249,49],'score':.99}] if present[0] else []
            return original(image,name,threshold)
        game.ocr.match=match
        self.assertFalse(task.idle_home_completed())
        game.time=9;present[0]=True;self.assertFalse(task.idle_home_completed())
        game.time=10;present[0]=False;self.assertFalse(task.idle_home_completed())
        game.time=19.9;self.assertFalse(task.idle_home_completed())
        game.time=20;self.assertTrue(task.idle_home_completed())

    def test_ocr_autopath_fallback_is_local_and_supports_split_words(self):
        task,game=self.task();game.ocr.match=Mock(return_value=[])
        for words in (
            [{'text':'自动寻路中','box':[845,128,249,49],'score':.95}],
            [{'text':'自 动','box':[845,128,90,49],'score':.95},
             {'text':'寻 路 中','box':[935,128,159,49],'score':.95}],
        ):
            game.items=words;self.assertTrue(task.autopath_visible())
        for box,score in (([100,800,249,49],.99),([845,128,249,49],.7)):
            game.items=[{'text':'自动寻路中','box':box,'score':score}]
            self.assertFalse(task.autopath_visible())

    def test_real_template_tracks_local_movement_but_does_not_match_chat_region(self):
        ocr=LocalOCR();template=np.array(Image.open(ROOT/'resources/local/image/wanted_autopath_label_user20261019.png').convert('RGB'))[:,:,::-1].copy()
        flow=LocalFlows(Mock(),ocr,{},lambda:None,Mock());flow.items=[];task=WantedTask(flow)
        for x,y,expected in ((856,137,True),(100,800,False)):
            flow.image=np.zeros((1015,1920,3),dtype=np.uint8)
            flow.image[y:y+49,x:x+249]=template
            self.assertEqual(task.autopath_visible(),expected)
        flow.window.click.assert_not_called()

    def test_two_observations_are_not_enough_even_after_ten_seconds(self):
        task,game=self.task();self.assertFalse(task.idle_home_completed())
        game.time=10;self.assertFalse(task.idle_home_completed())
        game.time=10.1;self.assertTrue(task.idle_home_completed())

    def test_autopath_source_hashes_crop_pixels_and_both_supplied_label_appearances(self):
        manifest=json.loads((ROOT/'resources/local/wanted/autopath-sources.json').read_text(encoding='utf-8'))
        for source in manifest['sources']:
            self.assertEqual(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest(),source['sha256'])
        source=Image.open(ROOT/manifest['sources'][0]['path']).convert('RGB')
        game=Image.open(ROOT/manifest['gameImage']).convert('RGB')
        self.assertEqual(source.crop(manifest['gameCrop']).tobytes(),game.tobytes())
        self.assertEqual(hashlib.sha256((ROOT/manifest['gameImage']).read_bytes()).hexdigest(),manifest['gameSha256'])
        ocr=LocalOCR()
        for source in manifest['sources'][1:]:
            image=np.array(Image.open(ROOT/source['path']).convert('RGB'))[:,:,::-1].copy()
            self.assertTrue(ocr.match(image,'wanted_autopath',threshold=.9))


if __name__=='__main__':unittest.main()
