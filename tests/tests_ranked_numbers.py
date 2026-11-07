"""Unified numeric ROI, independent shape/OCR evidence, frames and diagnostics."""
import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from local_flows import LocalFlows,normalized
from ranked_vision import read_opponent_power
from ranked_pipeline import RankedSession
from ranked_numbers import (NumberRecognitionError,arbitrate,digit_bank,kernels,
                            opponent_region,read_opponent,save_evidence,shape_reading)

ROOT=Path(__file__).resolve().parents[1]
LATEST='出错任务/排位战/证据/ac3c382f3b9deeb677c9b8fb.png'
POWER=[634467,674651,750130,962616,471398]


class UnifiedNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR()
        cls.image=np.array(Image.open(ROOT/LATEST).convert('RGB'))[:,:,::-1].copy()
        cls.items=cls.ocr.read(cls.image)
        cls.buttons=sorted([i for i in cls.items if i['text']=='挑战' and i['box'][1]>550],key=lambda i:i['box'][0])

    def flow(self):
        flow=LocalFlows(Mock(),self.ocr,{'rankedServer':'连服','rankedLimit':1},lambda:None,Mock())
        flow.image=self.image.copy();flow.items=list(self.items)
        return flow

    def test_oct26_touching_zero_nine_is_verified_without_new_bank_samples(self):
        path=ROOT/'verification/failure-20261026-210317-1c9435634012-ranked.png'
        flow=self.flow()
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(5,578895))
        self.assertEqual([o['power'] for o in opponents],[1430931,1095433,935536,1059743,730541])
        shape=flow.ranked_number_evidence['opponents'][0]['shape']
        self.assertEqual(shape['value'],1430931)
        self.assertTrue(all(v['minimumIoU']>=.9 for v in shape['views']))
        session=RankedSession(flow);session.frame_seq=1
        self.assertFalse(session.recognize('stable',flow.image))
        session.frame_seq=2
        self.assertTrue(session.recognize('stable',flow.image))
        flow.window.click.assert_not_called()

    def test_oct26_all_five_archived_failures_resolve_touching_digits(self):
        folders=sorted((ROOT/'verification').glob('failure-20261026-*-ranked-numbers'))
        self.assertEqual(len(folders),5)
        for folder in folders:
            with self.subTest(path=folder.name):
                rgb=np.array(Image.open(folder/'opponent-1.png').convert('RGB'))
                self.assertEqual(shape_reading(rgb)['value'],1430931)

    def test_oct26_boundary_support_keeps_conflict_and_occlusion_rejection(self):
        path=ROOT/'verification/failure-20261026-210317-1c9435634012-ranked.png'
        image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        button={'box':[406,834,56,26]}
        ocr=Mock();ocr.read.return_value=[{'text':'1430937','score':.99}]
        with self.assertRaisesRegex(NumberRecognitionError,'冲突'):
            read_opponent(image,button,ocr)
        x,y,r,b=opponent_region(image,button)[1]
        image[y+4:y+9,x:r]=0
        ocr.read.return_value=[{'text':'1430931','score':.99}]
        with self.assertRaises(NumberRecognitionError):read_opponent(image,button,ocr)

    def test_latest_failure_reproduces_old_caption_path_but_new_production_passes(self):
        item=next(i for i in self.items if '6746' in i['text'])
        with self.assertRaisesRegex(RuntimeError,'不一致'):
            read_opponent_power(self.image,item,self.ocr,normalized)
        flow=self.flow();count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(3,341235))
        self.assertEqual([o['power'] for o in opponents],POWER)
        self.assertEqual(len(flow.ranked_number_evidence['opponents']),5)
        flow.window.click.assert_not_called()

    def test_no_power_caption_is_required_and_wrong_captions_do_not_vote(self):
        flow=self.flow();flow.items=[i for i in flow.items if '战力' not in i['text'] and '战斗力' not in i['text']]
        flow.items.append({'text':'战斗力:999999','box':[362,798,132,22],'score':.99})
        _,_,opponents=flow.ranked_state()
        self.assertEqual([o['power'] for o in opponents],POWER)

    def test_button_relative_roi_tracks_translation_and_preserves_pixel_crop(self):
        button=self.buttons[1];rgb,box=opponent_region(self.image,button)
        moved=np.zeros_like(self.image);moved[7:,11:]=self.image[:-7,:-11]
        new_button=dict(button,box=[button['box'][0]+11,button['box'][1]+7,*button['box'][2:]])
        translated,new_box=opponent_region(moved,new_button)
        self.assertEqual(new_box,[box[0]+11,box[1]+7,box[2]+11,box[3]+7])
        self.assertTrue(np.array_equal(rgb,translated))
        self.assertEqual(shape_reading(translated)['value'],674651)

    def test_blank_dense_occluded_and_wrong_size_regions_are_not_guessed(self):
        button=self.buttons[1];x,y,r,b=opponent_region(self.image,button)[1]
        for kind in ('blank','dense','occluded','size'):
            with self.subTest(kind=kind):
                image=self.image.copy()
                if kind=='blank':image[y-2:b+2,x-2:r+2]=0
                elif kind=='dense':image[y:b,x:r]=255
                elif kind=='occluded':image[y+4:y+9,x:r]=0
                else:image=image[:900]
                ocr=Mock();ocr.read.return_value=[{'text':'999999','score':.99}]
                with self.assertRaises(NumberRecognitionError) as error:read_opponent(image,button,ocr)
                self.assertTrue(error.exception.evidence['reason'])

    def test_duplicate_challenge_anchors_stop_before_numeric_read_or_input(self):
        flow=self.flow();buttons=[i for i in flow.items if i['text']=='挑战']
        flow.items=[i for i in flow.items if i['text']!='挑战']+[buttons[0]]*5
        with patch('local_flows.read_opponent',side_effect=AssertionError('must not read ambiguous anchors')):
            with self.assertRaisesRegex(RuntimeError,'唯一定位'):flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_ocr_receives_only_numeric_views_without_caption_detection(self):
        calls=[]
        class Spy:
            def read(_,image,only_rec=False):
                calls.append((image.shape,only_rec))
                return self.ocr.read(image,only_rec=only_rec)
        reading=read_opponent(self.image,self.buttons[1],Spy())
        self.assertEqual(reading['value'],674651)
        self.assertTrue(all(only_rec for _,only_rec in calls))
        self.assertTrue(all(shape[1]<300 and shape[0]<80 for shape,_ in calls))

    def test_numeric_ocr_conflict_is_not_erased_by_further_views_or_templates(self):
        ocr=Mock();ocr.read.side_effect=[[{'text':'674651','score':.99}],[{'text':'674631','score':.99}]]
        with self.assertRaisesRegex(NumberRecognitionError,'冲突') as error:
            read_opponent(self.image,self.buttons[1],ocr)
        self.assertEqual(ocr.read.call_count,2)
        self.assertEqual(error.exception.evidence['shape']['value'],674651)

    def test_high_quality_shape_recovers_percent_without_character_substitution(self):
        ocr=Mock();ocr.read.return_value=[{'text':'6%6S1','score':.99}]
        reading=read_opponent(self.image,self.buttons[1],ocr)
        self.assertEqual(reading['value'],674651)
        self.assertIn('高质量',reading['reason'])
        self.assertTrue(all(o['value'] is None for o in reading['observations']))

    def test_concentrated_arbiter_requires_independent_shape_and_rejects_unknown(self):
        shape={'value':674651,'views':[{'meanIoU':.95,'minimumIoU':.85}]*2}
        self.assertEqual(arbitrate([{'value':674651}],shape)[0],674651)
        self.assertIsNone(arbitrate([{'value':674631}],shape)[0])
        self.assertIsNone(arbitrate([{'value':674651},{'value':674631}],shape)[0])
        self.assertIsNone(arbitrate([{'value':674651}]*4,{'value':None,'views':[]})[0])
        self.assertIsNone(arbitrate([],{'value':674651,'views':[{'meanIoU':.85,'minimumIoU':.7}]*2})[0])
        self.assertIsNone(arbitrate([],{'value':None,'views':[]})[0])

    def test_multiple_real_variants_have_source_pixels_and_holdout_separation(self):
        bank=json.loads((ROOT/'resources/local/ranked_numbers/bank.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(min(bank['variantCounts'].values()),2)
        self.assertNotIn(LATEST,[s['path'] for s in bank['sources']])
        self.assertNotIn(674651,[a['value'] for a in bank['annotations']])
        self.assertNotIn(750130,[a['value'] for a in bank['annotations']])
        for source in bank['sources']:
            path=ROOT/source['path'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),source['sha256'])
            with Image.open(path) as im:
                for ref in [t for t in bank['templates'] if t['sourceId']==source['id']]:
                    pixels=np.array(im.crop(ref['box']).convert('RGB'))
                    self.assertEqual(hashlib.sha256(pixels.tobytes()).hexdigest(),ref['pixelSha256'])
        self.assertEqual(len(digit_bank()),len(bank['templates']))

    def test_corrupt_bank_source_stops_even_with_numeric_ocr(self):
        digit_bank.cache_clear();kernels.cache_clear()
        try:
            with patch('pathlib.Path.read_bytes',return_value=b'changed'):
                ocr=Mock();ocr.read.return_value=[{'text':'674651','score':.99}]
                with self.assertRaisesRegex(NumberRecognitionError,'校验失败'):
                    read_opponent(self.image,self.buttons[1],ocr)
                ocr.read.assert_not_called()
        finally:digit_bank.cache_clear();kernels.cache_clear()

    def test_same_frame_never_counts_as_two_stable_observations(self):
        session=RankedSession(self.flow())
        session.frame_seq=1
        self.assertFalse(session.recognize('stable',self.image))
        self.assertFalse(session.recognize('stable',self.image))
        session.frame_seq=2
        self.assertTrue(session.recognize('stable',self.image))
        self.assertEqual([o['power'] for o in session.state[2]],POWER)
        session.flow.window.click.assert_not_called()

    def test_real_numeric_readings_drive_two_round_tasker_refresh_and_home(self):
        # Real saved pixels/OCR feed production ranked_state; game transitions
        # and inputs are simulated. These pictures are from different runs.
        from tests_ranked_pipeline import Game,FAST
        from ranked_pipeline import run_ranked_pipeline
        frames={4:'出错任务/排位战/证据/562b157c91b3f43476ed8383.png',3:LATEST,
                '3before':'verification/ranked-live-20261016-230143/input-04-close.png',
                2:'出错任务/排位战/证据/859054be011704e1a56a2121.png'}
        flows={}
        for count,path in frames.items():
            flow=self.flow()
            flow.image=np.array(Image.open(ROOT/path).convert('RGB'))[:,:,::-1].copy()
            flow.items=self.ocr.read(flow.image);flows[count]=flow
        game=Game(count=4,results=('defeat','victory'),limit=2)
        game.cfg['tolerance']=1000
        readings=[]
        def actual_state():
            key='3before' if game.count==3 and 'refresh' not in game.inputs else game.count
            count,own,opponents=flows[key].ranked_state()
            self.assertEqual(count,game.count)
            readings.append((count,[o['power'] for o in opponents]))
            for opponent in opponents:opponent['button']=dict(opponent['button'],type='challenge')
            return count,own,opponents
        game.ranked_state=actual_state
        run_ranked_pipeline(game,pipeline_override=FAST)
        self.assertEqual(game.inputs,['challenge','end','confirm','refresh','challenge','end','confirm','close'])
        self.assertEqual((game.page,game.count),('home',2))
        self.assertTrue(any(count==3 and powers==POWER for count,powers in readings))
        self.assertTrue(any(e.get('status')=='done' and e['completed']==2 for e in game.events))
        game.window.click.assert_not_called()
        for flow in flows.values():flow.window.click.assert_not_called()

    def test_diagnostic_saves_exact_crops_and_keeps_previous_folder(self):
        flow=self.flow();flow.ranked_state()
        with TemporaryDirectory(prefix='test-ranked-numbers-',dir=ROOT/'verification') as folder:
            first=save_evidence(folder,'test',flow.ranked_number_evidence,flow.ranked_number_crops)
            original=first.read_bytes()
            second=save_evidence(folder,'test',flow.ranked_number_evidence,flow.ranked_number_crops)
            self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),original)
            data=json.loads(first.read_text(encoding='utf-8'))
            for record,rgb in zip(data['opponents'],flow.ranked_number_crops):
                path=first.parent/record['crop']
                self.assertTrue(np.array_equal(np.array(Image.open(path)),rgb))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['cropSha256'])

    def test_worker_failure_note_links_diagnostics_without_hiding_original_error(self):
        flow=self.flow();flow.ranked_state()
        tree=ast.parse((ROOT/'src/native_worker.py').read_text(encoding='utf-8'))
        report=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='report_error')
        with TemporaryDirectory(prefix='test-ranked-worker-',dir=ROOT/'verification') as folder:
            tracker=Mock(task_id='ranked',run='offline',secrets=[],finished=False,failed=True)
            emit=Mock();stopped=Mock();stopped.is_set.return_value=False
            env={'ROOT':Path(folder),'flow':flow,'tracker':tracker,'window':Mock(),'stopped':stopped,
                 'emit':emit,'exception_details':lambda *a:{},'clean':lambda s,*a:s}
            exec(compile(ast.Module(body=[report],type_ignores=[]),'native_worker.py','exec'),env)
            env['report_error'](RuntimeError('original failure'))
            tracker.failure.assert_called_once()
            details=tracker.failure.call_args.args[2]
            self.assertIn('evidence.json',details['evidenceNote'])
            tracker.reset_mock()
            with patch('ranked_numbers.save_evidence',side_effect=OSError('disk problem')):
                env['report_error'](RuntimeError('original failure'))
            self.assertEqual(tracker.failure.call_args.args[0],'original failure')


if __name__=='__main__':unittest.main()
