"""Ranked recognition and queue state regressions; no real game input."""
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
from local_flows import LocalFlows,select_opponent,normalized
from ranked_vision import read_red_power,read_opponent_power

ROOT=Path(__file__).resolve().parent

class RankedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR()
        cls.image=np.array(Image.open(ROOT/'resources/local/ranked-1920-calibration.png').convert('RGB'))[:,:,::-1].copy()
        cls.items=cls.ocr.read(cls.image)
        cls.count6_image=np.array(Image.open(ROOT/'resources/local/ranked-remaining6-1920.png').convert('RGB'))[:,:,::-1].copy()
        cls.count6_items=cls.ocr.read(cls.count6_image)
        cls.live_image=np.array(Image.open(ROOT/'resources/local/ranked-remaining6-live.png').convert('RGB'))[:,:,::-1].copy()
        cls.live_items=cls.ocr.read(cls.live_image)

    def flow(self):
        flow=LocalFlows(Mock(),self.ocr,{'tolerance':20},lambda:None,Mock())
        flow.image=self.image.copy();flow.items=list(self.items)
        flow.ensure_ranked_server=Mock()
        return flow

    def test_latest_panel_survives_missing_caption_and_control_ocr(self):
        flow=self.flow()
        path=ROOT/'出错任务/排位战/证据/158ed082d1c10b09032c8de8.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        self.assertFalse(any('剩余挑战次数' in i['text'] for i in flow.items))
        self.assertTrue(flow.ranked_panel_visible())
        # Lose the left control OCR too: the independent refresh control remains.
        flow.items=[i for i in flow.items if normalized(i['text'])!='调整阵容']
        self.assertTrue(flow.ranked_panel_visible())
        flow.window.click.assert_not_called()

    def test_local_cross_and_cooldown_share_panel_detection(self):
        for name in ('ranked-1920-calibration.png','ranked-local-live.png',
                     'ranked-refresh-cooldown-live.png'):
            with self.subTest(name=name):
                flow=self.flow()
                flow.image=np.array(Image.open(ROOT/'resources/local'/name).convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                self.assertTrue(flow.ranked_panel_visible())
                flow.window.click.assert_not_called()

    def test_occluded_title_is_not_a_confirmed_ranked_panel(self):
        flow=self.flow()
        flow.image[:190,670:1160]=0
        flow.items=self.ocr.read(flow.image)
        self.assertFalse(flow.ranked_panel_visible())
        flow.window.click.assert_not_called()

    def test_other_real_pages_are_not_ranked_panels(self):
        for path in ('resources/local/ranked-battle-1920.png',
                     'resources/local/battle-settlement-calibration.png',
                     'resources/local/ranked-defeat-1920.png',
                     'verification/ranked-live-20261016-230143/final.png'):
            with self.subTest(path=path):
                flow=self.flow()
                flow.image=np.array(Image.open(ROOT/path).convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                self.assertFalse(flow.ranked_panel_visible())
                flow.window.click.assert_not_called()

    def test_counter_text_alone_cannot_establish_panel(self):
        flow=self.flow();flow.image[:]=0
        flow.items=[{'text':'剩余挑战次数:1','box':[1646,95,150,21],'score':.99}]
        self.assertFalse(flow.ranked_panel_visible())
        flow.window.click.assert_not_called()

    def test_panel_counter_unknown_conflicting_or_out_of_range_is_rejected(self):
        for caption in ('其他数字:7','剩余共战次数:2','剩余挑战次数:26'):
            with self.subTest(caption=caption):
                flow=self.flow();flow.ocr=Mock()
                flow.ranked_server_state=Mock(return_value='连服')
                flow.ranked_refresh_state=Mock(return_value=('ready',{}))
                flow.items=[{'text':caption,'box':[1646,95,150,21],'score':.99}]
                flow.ocr.read.return_value=[{'text':'剩余共战次数:1','score':.99}] if '共战' in caption else []
                self.assertFalse(flow.ranked_panel_visible())
                flow.window.click.assert_not_called()

    def test_zero_panel_does_not_require_own_or_opponent_power(self):
        flow=self.flow()
        flow.items=[i for i in flow.items if i['box'][1]>200 or i['box'][0]<1400]
        flow.items.append({'text':'剩余挑战次数:0','box':[1646,95,150,21],'score':.99})
        with patch('local_flows.read_red_power',side_effect=AssertionError('must not read power')):
            self.assertTrue(flow.ranked_panel_visible())
        flow.window.click.assert_not_called()

    def test_confirmation_overlay_blocks_underlying_panel(self):
        flow=self.flow()
        flow.items.append({'text':'确定','box':[930,650,60,30],'score':.99})
        self.assertFalse(flow.ranked_panel_visible())
        flow.window.click.assert_not_called()

    def test_failure_frame_reads_red_own_power_and_all_opponents(self):
        flow=self.flow()
        self.assertFalse(any('我方战' in item['text'] for item in self.items))
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(7,565120))
        self.assertEqual([o['power'] for o in opponents],[672886,1174445,1313308,1419289,1162291])
        picked=select_opponent(own,opponents,20)
        self.assertEqual(picked['power'],672886)
        self.assertLess(picked['button']['box'][0],500)
        flow.window.click.assert_not_called()

    def test_archived_remaining_six_survives_misread_counter_caption(self):
        flow=self.flow();flow.image=self.count6_image.copy();flow.items=list(self.count6_items)
        self.assertFalse(any('剩余挑战次数' in item['text'] for item in flow.items))
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(6,565140))
        self.assertEqual([o['power'] for o in opponents],[672886,1174445,1313308,1419289,1162291])
        flow.window.click.assert_not_called()

    def test_live_truncated_opponent_is_verified_before_selection(self):
        flow=self.flow();flow.image=self.live_image.copy();flow.items=list(self.live_items)
        self.assertTrue(any('141928' in item['text'] and '1419289' not in item['text'] for item in flow.items))
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(6,565140))
        self.assertEqual([o['power'] for o in opponents],[672886,1174445,1313308,1419289,1162291])
        flow.window.click.assert_not_called()

    def test_truncated_suffix_requires_both_larger_views_to_agree(self):
        ocr=Mock()
        ocr.read.side_effect=[[{'text':'战斗力:141928','score':.95}],
                             [{'text':'战斗力:1419289','score':.95}],
                             [{'text':'战斗力:1419289','score':.95}],
                             [{'text':'战斗力:141928','score':.95}],
                             [{'text':'战斗力:1419289','score':.95}],
                             [{'text':'战斗力:141928','score':.95}],
                             [{'text':'1419289','score':.95}],
                             [{'text':'141928','score':.95}]]
        item={'text':'战斗力:141928','box':[1116,822,148,28],'score':.95}
        with self.assertRaisesRegex(RuntimeError,'末位复核不一致'):
            read_opponent_power(self.live_image,item,ocr,normalized)

    def test_non_suffix_majority_needs_two_numeric_views(self):
        item=next(a for a in self.items if '672886' in a['text'])
        ocr=Mock()
        ocr.read.side_effect=[[{'text':'战斗力:222222','score':.99}],
                             [{'text':'战斗力:222222','score':.99}],
                             [{'text':'333333','score':.99}],
                             [{'text':'333333','score':.99}]]
        with self.assertRaisesRegex(RuntimeError,'不一致'):
            read_opponent_power(self.image,item,ocr,normalized)

    def test_oct19_middle_digit_omission_reads_all_five_from_archived_frames(self):
        for key in ('1774a0844aa67f95cc020525','92c9aba87dc22a439843a213','562b157c91b3f43476ed8383'):
            with self.subTest(frame=key):
                flow=self.flow()
                flow.image=np.array(Image.open(ROOT/f'出错任务/排位战/证据/{key}.png').convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                count,own,opponents=flow.ranked_state()
                self.assertEqual((count,own),(4,341235))
                self.assertEqual([o['power'] for o in opponents],[634467,815753,885384,962616,471398])
                flow.window.click.assert_not_called()

    def test_numeric_double_read_can_confirm_an_existing_nonmajority_caption(self):
        # The two caption views may repeat the SAME error. Pixel-only double
        # readings can prove the original full-frame candidate instead.
        item=next(a for a in self.items if '672886' in a['text'])
        ocr=Mock()
        ocr.read.side_effect=[[{'text':'战斗力:222222','score':.99}]]*2+[
            [{'text':'672886','score':.99}],[{'text':'672886','score':.99}]]
        self.assertEqual(read_opponent_power(self.image,item,ocr,normalized),672886)
        self.assertEqual(ocr.read.call_count,4)

    def test_nonmajority_caption_needs_two_confident_numeric_reads_and_a_valid_candidate(self):
        item=next(a for a in self.items if '672886' in a['text'])
        cases=[('672886',.99,'672887',.99,.99),
               ('672886',.79,'672886',.79,.99),
               ('672886',.99,'672886',.99,.79),
               ('672886',.99,'',.99,.99)]
        for first,s1,second,s2,caption_score in cases:
            with self.subTest(first=first,second=second,s1=s1,caption_score=caption_score):
                captions=['222222','333333'] if caption_score<.8 else ['222222','222222']
                ocr=Mock();ocr.read.side_effect=[[{'text':'战斗力:'+text,'score':.99}] for text in captions]+[
                    [{'text':first,'score':s1}],[{'text':second,'score':s2}],[]]
                with patch('ranked_vision.read_white_power',side_effect=AssertionError('numeric conflict cannot use templates')):
                    with self.assertRaisesRegex(RuntimeError,'不一致'):
                        read_opponent_power(self.image,dict(item,score=caption_score),ocr,normalized)

    def test_counter_alias_requires_a_second_matching_region_read(self):
        flow=self.flow();flow.image=self.count6_image.copy();flow.items=list(self.count6_items)
        flow.ocr=Mock()
        flow.ocr.read.return_value=[{'text':'剩余挑战次数:7','score':.99}]
        with self.assertRaisesRegex(RuntimeError,'冲突'):
            flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_other_numbers_or_counter_outside_header_do_not_count(self):
        flow=self.flow();flow.ocr=Mock()
        flow.ocr.read.return_value=[{'text':'当日排位战奖励:6','score':.99}]
        flow.items=[{'text':'剩余共战次数:6','box':[100,500,140,25],'score':.99}]
        with self.assertRaisesRegex(RuntimeError,'剩余次数'):
            flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_existing_panel_with_misread_caption_does_not_reopen_entry(self):
        flow=self.flow();flow.image=self.count6_image.copy();flow.items=list(self.count6_items)
        flow.observe=Mock();flow.enter=Mock();flow.close_panel=Mock()
        flow.wait_ranked_ready=Mock(return_value=(0,None,[]))
        self.assertTrue(flow.ranked_panel_visible())
        self.assertEqual(flow.ranked(),'skipped')
        flow.enter.assert_not_called();flow.close_panel.assert_called_once()
        flow.window.click.assert_not_called()

    def test_alias_zero_count_skips_power_read_and_bad_range_is_rejected(self):
        flow=self.flow();flow.image[:150,:600]=0;flow.ocr=Mock()
        flow.items=[{'text':'剩余共战次数:0','box':[1646,95,154,23],'score':.99}]
        flow.ocr.read.return_value=[{'text':'剩余共战次:0','score':.99}]
        self.assertEqual(flow.ranked_state(),(0,None,[]))
        flow.items=[{'text':'剩余共战次数:26','box':[1646,95,154,23],'score':.99}]
        flow.ocr.read.return_value=[{'text':'剩余共战次:26','score':.99}]
        with self.assertRaisesRegex(RuntimeError,'异常'):
            flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_changed_red_glyphs_are_read_from_pixels(self):
        # Swap the final zero with the verified 2 artwork, keeping red colour.
        image=self.image.copy()
        image[85:142,335:372]=0
        glyph=np.array(Image.open(ROOT/'resources/local/image/ranked_power_digit2_runtime.png').convert('L'))<128
        h,w=glyph.shape
        region=image[103:103+h,336:336+w]
        region[glyph]=[0,0,255]
        self.assertEqual(read_red_power(image,self.ocr),565122)

    def test_changed_own_power_from_latest_failure_selects_verified_opponent(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'resources/local/ranked-power340470-1920.png').convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        self.assertTrue(flow.ranked_panel_visible())
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(7,340470))
        self.assertCountEqual([o['power'] for o in opponents],[547461,1389901,647519,611663,402865])
        picked=select_opponent(own,opponents,20)
        self.assertEqual(picked['power'],402865)
        self.assertGreater(picked['button']['box'][0],1300)
        flow.window.click.assert_not_called()

    def test_classified_ranked_sample_reads_current_power(self):
        flow=self.flow()
        path=ROOT/'resources/local/catalog/ranked/20261013-974-cross-ready/game.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        self.assertTrue(flow.ranked_panel_visible())
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(6,341307))
        self.assertCountEqual([o['power'] for o in opponents],[547461,1389901,647519,611663,402865])
        self.assertEqual(select_opponent(own,opponents,20)['power'],402865)
        flow.window.click.assert_not_called()

    def test_afternoon_failure_reads_power_with_repeated_eights(self):
        flow=self.flow()
        path=ROOT/'出错任务/排位战/证据/1d6c05e9d6c508ef8460ef10.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(7,572882))
        self.assertCountEqual([o['power'] for o in opponents],
                              [672886,1174445,1313308,1419289,1162291])
        self.assertEqual(select_opponent(own,opponents,20)['power'],672886)
        flow.window.click.assert_not_called()

    def test_oct16_failures_and_catalog_read_nine_before_selecting(self):
        samples=[('出错任务/排位战/证据/e9a0953937d5bf6332988733.png',
                  [1312030,1698132,1645952,1579496,866320]),
                 ('出错任务/排位战/证据/2b3eeebbb2e4eafbc1a4271e.png',
                  [718017,1498553,726435,1320372,774074]),
                 ('resources/local/catalog/ranked/20261016-973-cross-ready/game.png',
                  [1312030,1698132,1645952,1579496,866320])]
        for name,powers in samples:
            with self.subTest(sample=name):
                flow=self.flow()
                flow.image=np.array(Image.open(ROOT/name).convert('RGB'))[:,:,::-1].copy()
                flow.items=self.ocr.read(flow.image)
                count,own,opponents=flow.ranked_state()
                self.assertEqual((count,own),(5,572798))
                self.assertCountEqual([o['power'] for o in opponents],powers)
                flow.window.click.assert_not_called()

    def test_post_refresh_frame_reads_all_opponents_from_numeric_pixels(self):
        flow=self.flow()
        path=ROOT/'出错任务/排位战/证据/45706e4f3dec2230d7449180.png'
        flow.image=np.array(Image.open(path).convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(2,565140))
        self.assertCountEqual([o['power'] for o in opponents],
                              [1155227,752120,1066599,618173,769353])
        self.assertEqual(select_opponent(own,opponents,20)['power'],618173)
        flow.window.click.assert_not_called()

    def test_eight_artwork_can_change_an_older_power_without_ocr(self):
        image=self.image.copy()
        image[85:142,335:372]=0
        glyph=np.array(Image.open(ROOT/'resources/local/image/ranked_power_digit8_failure572882_3.png').convert('L'))<128
        h,w=glyph.shape
        image[103:103+h,336:336+w][glyph]=[0,0,255]
        ocr=Mock()
        ocr.read.return_value=[]
        self.assertEqual(read_red_power(image,ocr),565128)
        ocr.read.assert_not_called()
        # An unverified rectangle must still stop, even at the same location.
        image[103:103+h,336:336+w]=[0,0,255]
        with self.assertRaisesRegex(RuntimeError,'无法复核'):
            read_red_power(image,ocr)

    def test_oct18_refresh_failure_reads_touching_opponent_digits(self):
        flow=self.flow()
        flow.image=np.array(Image.open(ROOT/'出错任务/排位战/证据/859054be011704e1a56a2121.png').convert('RGB'))[:,:,::-1].copy()
        flow.items=self.ocr.read(flow.image)
        self.assertTrue(flow.ranked_panel_visible())
        count,own,opponents=flow.ranked_state()
        self.assertEqual((count,own),(2,569821))
        self.assertCountEqual([o['power'] for o in opponents],[1109537,1007171,960878,1345437,690256])
        flow.window.click.assert_not_called()

    def test_touching_digits_require_two_stretched_numeric_views(self):
        item=dict(next(a for a in self.items if '672886' in a['text']),text='战斗力:%0878')
        ocr=Mock()
        ocr.read.side_effect=[[{'text':'战斗力:%0878','score':.99}]]*2+[
            [{'text':'9%0878','score':.99}],[{'text':'9%0878','score':.99}],
            [{'text':'960878','score':.95}],[{'text':'960878','score':.95}]]
        self.assertEqual(read_opponent_power(self.image,item,ocr,normalized),960878)
        self.assertEqual(ocr.read.call_count,6)

    def test_stretched_digits_reject_conflict_low_score_letters_or_one_view(self):
        item=dict(next(a for a in self.items if '672886' in a['text']),text='战斗力:%0878')
        cases=[(('960878',.95),('960879',.95)),(('960878',.79),('960878',.79)),
               (('9%0878',.95),('9%0878',.95)),(('960878',.95),('',.95))]
        for pair in cases:
            with self.subTest(pair=pair):
                ocr=Mock()
                ocr.read.side_effect=[[{'text':'战斗力:%0878','score':.99}]]*2+[
                    [{'text':'9%0878','score':.99}],[{'text':'9%0878','score':.99}],
                    [{'text':pair[0][0],'score':pair[0][1]}],[{'text':pair[1][0],'score':pair[1][1]}],[]]
                with self.assertRaisesRegex(RuntimeError,'不一致'):
                    read_opponent_power(self.image,item,ocr,normalized)

    def test_numeric_conflict_never_uses_stretch_to_overwrite_it(self):
        item=dict(next(a for a in self.items if '672886' in a['text']),text='战斗力:960878')
        ocr=Mock()
        ocr.read.side_effect=[[{'text':'战斗力:960878','score':.99}],
                             [{'text':'战斗力:960879','score':.99}],
                             [{'text':'960878','score':.99}],
                             [{'text':'960879','score':.99}],
                             [{'text':'960878','score':.99}],
                             [{'text':'960878','score':.99}]]
        with self.assertRaisesRegex(RuntimeError,'不一致'):
            read_opponent_power(self.image,item,ocr,normalized)
        self.assertEqual(ocr.read.call_count,4)

    def test_unknown_red_artwork_and_missing_button_block_clicks(self):
        flow=self.flow();flow.image[80:150,170:520]=0
        with self.assertRaisesRegex(RuntimeError,'我方战力'):flow.ranked_state()
        flow=self.flow();flow.items=[item for item in flow.items if not (item['text']=='挑战' and item['box'][0]<500)]
        with self.assertRaisesRegex(RuntimeError,'五个'):flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_conflicting_opponent_readings_are_rejected(self):
        flow=self.flow();flow.ocr=Mock()
        flow.ocr.read.return_value=[{'text':'222222','score':.99}]
        with self.assertRaisesRegex(RuntimeError,'冲突'):flow.ranked_state()
        flow.window.click.assert_not_called()

    def test_unknown_caption_requires_matching_confident_numeric_views(self):
        item=dict(next(a for a in self.items if '672886' in a['text']),text='战斗力:1066s9')
        for readings in ((('1066599',.99),('1066399',.99)),
                         (('1066599',.79),('1066599',.79)),
                         (('1066s9',.99),('1066s9',.99))):
            with self.subTest(readings=readings):
                ocr=Mock()
                ocr.read.side_effect=[[{'text':'战斗力:1066s9','score':.99}],
                                     [{'text':'战斗力:1066s9','score':.99}],
                                     [{'text':readings[0][0],'score':readings[0][1]}],
                                     [{'text':readings[1][0],'score':readings[1][1]}],[],[],[]]
                with self.assertRaisesRegex(RuntimeError,'不一致'):
                    read_opponent_power(self.image,item,ocr,normalized)

    def test_ready_requires_two_identical_states_and_resets_after_error(self):
        flow=self.flow();flow.observe=Mock()
        opponents=[{'power':672886,'button':{'box':[400,830,50,30]}}]
        state=(7,565120,opponents)
        flow.ranked_state=Mock(side_effect=[state,RuntimeError('数字未加载'),state,state])
        def wait(predicate,seconds):
            self.assertEqual(seconds,30)
            for expected in (False,False,False,True):self.assertEqual(predicate(),expected)
        flow.wait=wait
        self.assertEqual(flow.wait_ranked_ready(),state)

    def test_existing_panel_continues_and_zero_count_closes(self):
        flow=self.flow();flow.observe=Mock();flow.enter=Mock();flow.close_panel=Mock()
        flow.wait_ranked_ready=Mock(return_value=(0,None,[]))
        self.assertEqual(flow.ranked(),'skipped')
        flow.enter.assert_not_called();flow.close_panel.assert_called_once()

    def test_challenge_cycle_tracks_decreased_count_and_current_button(self):
        flow=self.flow();flow.observe=Mock();flow.enter=Mock();flow.close_panel=Mock()
        button={'box':[406,834,56,26]}
        states=[(2,565120,[{'power':672886,'button':button}]),
                (1,565120,[{'power':672886,'button':button}]),(0,None,[])]
        flow.wait_ranked_ready=Mock(side_effect=states)
        flow.finish_ranked_battle=Mock();flow.click_item=Mock()
        flow.ranked()
        self.assertEqual(flow.click_item.call_count,2)
        self.assertEqual(flow.finish_ranked_battle.call_count,2)
        flow.close_panel.assert_called_once();flow.enter.assert_not_called()
        flow.window.click.assert_not_called()

    def test_unchanged_count_stops_before_second_challenge(self):
        flow=self.flow();flow.observe=Mock();flow.enter=Mock();flow.click_item=Mock()
        state=(7,565120,[{'power':672886,'button':{'box':[406,834,56,26]}}])
        flow.wait_ranked_ready=Mock(side_effect=[state,state])
        flow.finish_ranked_battle=Mock()
        with self.assertRaisesRegex(RuntimeError,'次数未减少'):flow.ranked()
        flow.click_item.assert_called_once()

    def test_zero_count_does_not_require_own_power(self):
        flow=self.flow()
        flow.image[:150,:600]=0
        flow.items=[dict(item,text='剩余挑战次数:0') if '剩余挑战次数' in item['text'] else item for item in flow.items]
        self.assertEqual(flow.ranked_state(),(0,None,[]))


if __name__=='__main__':unittest.main()
