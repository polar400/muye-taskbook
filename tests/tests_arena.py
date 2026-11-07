"""Arena entry contract: original pixels, real Maa recognition, simulated IO."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from arena_task import ArenaTask,run_arena,validate_arena_config
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DAILY='resources/local/arena/daily-user-game.png'
OLD_DAILY='resources/local/catalog/activities/20261016-973-daily/game.png'
PANEL='resources/local/catalog/arena/20261016-973-team-ready/game.png'
HOME='resources/local/catalog/home/20261016-973-village/game.png'
HOME_SOURCE='resources/local/catalog/home/20261013-974-village/game.png'
RANKED='resources/local/ranked-local-live.png'


class ArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR();cls.frames={};cls.recognition_evidence=[]
        for name in (DAILY,PANEL,HOME,HOME_SOURCE,RANKED):
            image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
            cls.frames[name]=(image,cls.ocr.read(image))

    def task(self,name=PANEL):
        flow=LocalFlows(Mock(),self.ocr,{'tasks':['arena']},lambda:None,Mock())
        flow.image=self.frames[name][0].copy();flow.items=list(self.frames[name][1])
        return ArenaTask(flow)

    def test_real_panel_has_two_modes_and_left_task_region(self):
        task=self.task();state=task.panel()
        self.assertEqual(state['modes'],['段位战斗','休闲战斗'])
        self.assertEqual(state['controls']['ranked_battle']['box'],[415,872,265,99])
        self.assertEqual(state['controls']['casual_battle']['box'],[715,872,255,99])
        self.assertTrue(any('胜利1场' in w['text'] for w in state['leftTaskWords']))
        self.assertFalse(state['taskActionsEnabled'])

    def test_two_real_home_pages_locate_only_arena_icon(self):
        for frame in (HOME,HOME_SOURCE):
            with self.subTest(frame=frame):
                task=self.task(frame)
                button=task.home_icon()
                self.assertIsNotNone(button)
                self.assertTrue(1380<=button['box'][0]<=1410)
                self.assertTrue(105<=button['box'][1]<=145)
                self.assertIsNone(task.panel())
                self.recognition_evidence.append(dict(source=frame,button=button))

    def test_missing_home_icon_never_uses_old_route(self):
        task=self.task(HOME);task.f.image[90:210,1370:1470]=0
        self.assertIsNone(task.home_icon())
        self.assertFalse(any(hasattr(task,name) for name in ('daily','row','participate','selected_daily')))

    def test_home_icon_click_target_follows_actual_match(self):
        task=self.task(HOME);icon=task.f.image[99:203,1380:1468].copy()
        task.f.image[90:210,1370:1470]=0
        task.f.image[220:324,1100:1188]=icon
        button=task.home_icon()
        self.assertIsNotNone(button);self.assertEqual(button['box'],[1114,245,56,49])

    def test_each_panel_anchor_is_required(self):
        for name,box in self.task().panel()['controls'].items():
            with self.subTest(name=name):
                task=self.task();x,y,w,h=box['box'];task.f.image[y:y+h,x:x+w]=0
                self.assertIsNone(task.panel())

    def test_other_pages_are_not_arena(self):
        for frame in (HOME,DAILY,RANKED):
            with self.subTest(frame=frame):self.assertIsNone(self.task(frame).panel())

    def test_duplicate_home_icon_stops(self):
        task=self.task(HOME)
        task.f.image[99:203,1100:1188]=task.f.image[99:203,1380:1468]
        with self.assertRaisesRegex(RuntimeError,'不唯一'):task.home_icon()

    def test_popup_blocks_panel_and_home_entry(self):
        for frame in (HOME,PANEL):
            with self.subTest(frame=frame):
                task=self.task(frame);task.f.items.append(dict(text='确定',score=.99,box=[850,500,70,35]))
                self.assertIsNone(task.panel());self.assertIsNone(task.home_icon())

    def test_uncalibrated_image_stops(self):
        task=self.task();task.f.image=task.f.image[::2,::2]
        with self.assertRaisesRegex(RuntimeError,'1920'):task.panel()

    def route(self,start):
        task=self.task(start);flow=task.f;state={'page':start,'time':0.0};clicks=[]
        original=flow.checkpoint
        task.clock=lambda:state['time']
        task.sleep=lambda seconds:state.update(time=state['time']+seconds)
        def observe():
            image,words=self.frames[state['page']]
            flow.image=image.copy();flow.items=list(words)
        flow.observe=observe
        def click(x,y):
            clicks.append((x,y))
            self.assertTrue(1380<=x<=1470 and 99<=y<=203)
            state['page']=PANEL
        flow.window.click.side_effect=click
        with patch('local_flows.time.sleep'):
            self.assertEqual(task.run(),'opened')
        self.assertIs(flow.checkpoint,original)
        self.assertEqual(flow.arena_evidence['page'],'arena')
        self.recognition_evidence.append(dict(start=start,simulatedInputs=clicks,result='opened'))
        return task,clicks,state

    def test_home_to_panel_clicks_only_main_arena_icon(self):
        task,clicks,state=self.route(HOME)
        self.assertEqual(clicks,[(1422,148)])
        self.assertEqual(task.sent,{'主界面竞技场图标'})
        self.assertEqual(state['page'],PANEL)

    def test_existing_daily_page_stops_without_old_navigation(self):
        task=self.task(DAILY);task.f.observe=Mock()
        with self.assertRaisesRegex(RuntimeError,'主界面'):task.run()
        task.f.window.click.assert_not_called();self.assertEqual(task.sent,set())

    def test_existing_arena_reads_two_frames_without_click(self):
        task,clicks,state=self.route(PANEL)
        self.assertEqual(clicks,[]);self.assertEqual(task.sent,set())
        self.assertGreaterEqual(state['time'],.2)

    def test_fresh_frame_must_still_be_home_before_click(self):
        task=self.task(HOME);task.f.image=self.frames[DAILY][0].copy()
        self.assertIsNone(task.home_icon())

    def test_user_icon_group_matches_at_original_pixels_among_neighbors(self):
        task=self.task(HOME)
        group=np.array(Image.open(ROOT/'resources/local/arena/references/home-tray-user.png').convert('RGB'))[:,:,::-1].copy()
        image=np.zeros_like(task.f.image);h,w=group.shape[:2];image[:h,900:900+w]=group
        task.f.image=image
        found=task.matches('home_entry_user',(.4,0,.85,.32))
        self.assertEqual(len(found),1)
        self.assertTrue(1340<found[0]['box'][0]<1370)
        self.recognition_evidence.append(dict(source='home-tray-user.png',placement=[900,0],button=found[0]))

    def test_uncertain_input_is_recorded_before_send_and_never_replayed(self):
        task=self.task(HOME);task.f.observe=Mock();task.f.click_item=Mock(side_effect=RuntimeError('send unknown'))
        with self.assertRaisesRegex(RuntimeError,'unknown'):task.click('主界面竞技场图标',task.home_icon)
        with self.assertRaisesRegex(RuntimeError,'重复'):task.click('主界面竞技场图标',task.home_icon)
        self.assertEqual(task.f.click_item.call_count,1)

    def test_timeout_sends_no_click_and_restores_checkpoint(self):
        task=self.task(HOME);original=task.f.checkpoint;state={'time':0}
        task.clock=lambda:state['time']
        def observe():state['time']+=31
        task.f.observe=observe
        with self.assertRaises(TimeoutError):task.run()
        self.assertIs(task.f.checkpoint,original)
        task.f.window.click.assert_not_called()

    def test_pause_time_does_not_consume_wait_budget(self):
        task=self.task();state={'time':0};task.clock=lambda:state['time']
        task.original_checkpoint=lambda:state.update(time=state['time']+100)
        task.checkpoint();self.assertEqual(task.now(),0)

    def test_panel_must_be_consecutive(self):
        task=self.task();task.f.observe=Mock();task.sleep=Mock()
        task.panel=Mock(side_effect=[{'page':'arena'},None,{'page':'arena'},{'page':'arena'}])
        self.assertEqual(task.stable_panel(),{'page':'arena'})
        self.assertEqual(task.f.observe.call_count,4)

    def test_config_backend_order_and_duplicate_validation(self):
        validate_arena_config({'tasks':['ranked','arena']})
        validate_arena_config({'tasks':['ranked'],'backend':'Midscene'})
        for cfg in ({'tasks':['arena','ranked']},{'tasks':['arena','arena']},
                    {'tasks':['arena'],'backend':'Midscene'}):
            flow=Mock();flow.cfg=cfg
            with self.assertRaises(ValueError):run_arena(flow)
            flow.observe.assert_not_called()

    def test_template_provenance_and_pixels(self):
        manifest=json.loads((ROOT/'resources/local/arena/sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['assets']),13)
        self.assertEqual(manifest['route'],'home-icon')
        self.assertTrue(manifest['rewardAutomationEnabled'])
        self.assertEqual({m['name'] for m in manifest['assets'] if m['runtimeEnabled']},
                         {'home_entry_catalog','home_entry_user','ranked_battle','casual_battle','score_label','task_header'})
        for record in manifest['assets']:
            with self.subTest(name=record['name']):
                source=ROOT/record['source'];asset=ROOT/record['path']
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),record['sourceSha256'])
                self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(),record['sha256'])
                original=Image.open(source).convert('RGB')
                if record['box']:original=original.crop(record['box'])
                self.assertEqual(np.array(original).tobytes(),np.array(Image.open(asset).convert('RGB')).tobytes())

    def test_reward_references_are_preserved_without_runtime_claim_actions(self):
        manifest=json.loads((ROOT/'resources/local/arena/sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['references']),4)
        for record in manifest['references']:
            self.assertFalse(record['runtimeEnabled'])
            self.assertEqual(hashlib.sha256((ROOT/record['path']).read_bytes()).hexdigest(),record['sha256'])
        ready,unmet=manifest['references'][2:]
        self.assertIn('1/1',ready['state']);self.assertIn('条件未满足',unmet['state'])


if __name__=='__main__':unittest.main()
