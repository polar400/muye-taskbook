"""Protection-token policy: real 2/3 reads and virtual games; no live inputs."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from adapters.local_ocr import LocalOCR
import numpy as np
from PIL import Image
import arena_daily
from arena_daily import DailyVision
from arena_tokens import TokenReader,TokenPolicy,DAILY_MODE
from arena_task import validate_arena_config
import tests_arena_daily as daily_tests

ROOT=Path(__file__).resolve().parents[1]


class TokenReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr=LocalOCR();cls.matcher=DailyVision(cls.ocr,ROOT/'resources/local/arena_tokens/image')
        cls.evidence=[]

    def test_real_2_and_3_are_not_fixed_daily_allowance(self):
        for source,expected in [('resources/local/arena_tokens/references/count2-user.png',2),
                                ('resources/local/catalog/arena/20261016-973-team-ready/game.png',3)]:
            with self.subTest(count=expected):
                image=np.array(Image.open(ROOT/source).convert('RGB'))[:,:,::-1].copy()
                if image.shape[1]==1920:image=image[110:190,960:1152].copy()
                reader=TokenReader(self.ocr,self.matcher)
                self.assertEqual(reader.read(image),expected)
                self.evidence.append(dict(source=source,count=expected,evidence=reader.evidence))

    def test_unknown_conflict_low_confidence_and_invalid_counts_rejected(self):
        image=np.zeros((60,150,3),dtype=np.uint8)
        matcher=Mock();matcher.match.return_value=[dict(box=[12,4,61,28],score=1)]
        for values in ((2,2,1),(4,4,4),('?',2,2),('2个',2,2)):
            ocr=Mock();ocr.read.side_effect=[[dict(text=str(n),score=.99)] for n in values]
            self.assertIsNone(TokenReader(ocr,matcher).read(image))
        for value in (0,1):
            # Mock OCR contracts only: no claim of real 0/1 image verification.
            ocr=Mock();ocr.read.return_value=[dict(text=str(value),score=.99)]
            self.assertEqual(TokenReader(ocr,matcher).read(image),value)
        ocr=Mock();ocr.read.return_value=[dict(text='2',score=.94)]
        self.assertIsNone(TokenReader(ocr,matcher).read(image))

    def test_label_missing_or_duplicated_never_reads_guessed_digit(self):
        image=np.zeros((60,150,3),dtype=np.uint8);ocr=Mock();matcher=Mock()
        for labels in ([],[dict(box=[12,4,61,28],score=1)]*2,[dict(box=[12,4,61,28],score=.94)]):
            matcher.match.return_value=labels
            self.assertIsNone(TokenReader(ocr,matcher).read(image))
        ocr.read.assert_not_called()


class TokenPolicyTests(unittest.TestCase):
    def test_actual_tokens_victory_loss_and_one_way_casual_lock(self):
        policy=TokenPolicy(lambda:0);policy.observe(2)
        policy.verify_result(2,'victory',2);self.assertEqual(policy.mode(),'段位战斗')
        policy.verify_result(2,'defeat',1);policy.verify_result(1,'defeat',0)
        self.assertEqual(policy.mode(),'休闲战斗')
        policy.observe(3);self.assertEqual(policy.mode(),'休闲战斗')

    def test_wrong_consumption_unknown_values_and_60_minute_limit(self):
        clock={'now':0};policy=TokenPolicy(lambda:clock['now']);policy.observe(2)
        for before,result,after in [(2,'defeat',2),(2,'defeat',0),(2,'victory',1),(2,'victory',3)]:
            with self.assertRaisesRegex(RuntimeError,'消耗不符'):policy.verify_result(before,result,after)
        for value in (None,True,-1,4):
            with self.assertRaises(RuntimeError):policy.observe(value)
        self.assertEqual(policy.deadline,3600);clock['now']=3600
        with self.assertRaisesRegex(TimeoutError,'60分钟'):policy.check_time()
        policy.observe(0);policy.check_time()


class TokenLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arena-tokens-test-',dir=ROOT/'verification')
        self.patch=patch.object(arena_daily,'ROOT',Path(self.temp.name));self.patch.start()

    def tearDown(self):self.patch.stop();self.temp.cleanup()

    def runner(self,limit=3):return daily_tests.DailyLoopTests.runner(self,DAILY_MODE,limit)

    def matches(self,game):return [x for phase,x,y in game.inputs if phase=='board' and y>850]

    def test_spends_actual_two_not_three_games_then_finishes_tasks_in_casual(self):
        runner,game=self.runner(limit=5);game.results=iter(['victory','defeat','victory','defeat','victory'])
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(self.matches(game),[500,500,500,500,800])
        self.assertEqual(game.tokens,0);self.assertEqual(len(game.tasks),4)
        self.assertTrue(runner.tokens.casual)

    def test_tasks_done_first_still_spends_tokens_without_extra_casual(self):
        runner,game=self.runner();game.tasks=[];game.results=iter(['victory','defeat','defeat'])
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(self.matches(game),[500,500,500]);self.assertEqual(game.tokens,0)

    def test_initial_zero_and_later_refill_never_reenters_ranked_this_run(self):
        runner,game=self.runner();game.tokens=0;game.results=itertools.repeat('victory')
        click=game.click
        def refill(x,y):
            was_settlement=game.phase=='settlement';click(x,y)
            if was_settlement:game.tokens=3
        runner.f.click_item=lambda item:refill(item['box'][0]+item['box'][2]//2,item['box'][1]+item['box'][3]//2)
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(self.matches(game),[800,800,800])

    def test_unknown_initial_count_stops_before_any_input(self):
        runner,game=self.runner();runner.read_tokens=lambda:None
        with self.assertRaisesRegex(RuntimeError,'战令数无法可靠'):runner.run()
        self.assertEqual(game.inputs,[])

    def test_no_loss_decrement_stops_without_replaying_match(self):
        runner,game=self.runner();game.results=itertools.repeat('defeat')
        click=game.click
        def wrong(x,y):
            was_settlement=game.phase=='settlement';click(x,y)
            if was_settlement:game.tokens+=1
        runner.f.click_item=lambda item:wrong(item['box'][0]+item['box'][2]//2,item['box'][1]+item['box'][3]//2)
        with self.assertRaisesRegex(RuntimeError,'消耗不符'):runner.run()
        self.assertEqual(self.matches(game),[500])

    def test_fresh_zero_before_ranked_sends_no_match(self):
        runner,game=self.runner();reads=iter([2,2,0]);runner.read_tokens=lambda:next(reads)
        with self.assertRaisesRegex(RuntimeError,'未发送匹配'):runner.run()
        self.assertEqual(game.inputs,[])

    def test_winning_does_not_run_forever_and_pause_is_not_counted(self):
        runner,game=self.runner();game.tasks=[];game.results=itertools.repeat('victory')
        # Shorten the fake-clock budget; real policy constant is tested above.
        runner.tokens.deadline=2
        with self.assertRaisesRegex(TimeoutError,'60分钟'):runner.run()
        report=json.loads((runner.folder/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['tokensRemainingLastVerified'],2)
        self.assertNotEqual(report['result'],'battle_limit_done')
        a=runner.a;before=a.now();a.original_checkpoint=lambda:setattr(game,'time',game.time+100)
        a.checkpoint();self.assertAlmostEqual(a.now(),before)

    def test_cap_stops_ranked_with_tokens_still_remaining(self):
        runner,game=self.runner(limit=2);game.results=itertools.repeat('victory');game.tasks=[]
        self.assertEqual(runner.run(),'battle_limit_done')
        self.assertEqual(self.matches(game),[500,500]);self.assertEqual(game.tokens,2)
        self.assertFalse(runner.tokens.casual)

    def test_claims_precede_token_read_failure(self):
        runner,game=self.runner();game.tasks[0].update(state='claim',progress=1)
        runner.read_tokens=lambda:None
        with self.assertRaisesRegex(RuntimeError,'战令数无法可靠'):runner.run()
        self.assertEqual(len(game.inputs),1);self.assertLess(game.inputs[0][2],850)

    def test_new_mode_is_valid_and_manual_modes_have_no_token_policy(self):
        validate_arena_config(dict(tasks=['arena'],arenaMode=DAILY_MODE))
        for mode in ('段位战斗','休闲战斗'):
            runner,game=daily_tests.DailyLoopTests.runner(self,mode)
            self.assertIsNone(runner.tokens)


if __name__=='__main__':unittest.main()
