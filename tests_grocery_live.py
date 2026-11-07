"""UI purchase protocol replay using genuine captures; never touches the game."""
from pathlib import Path
import tempfile
import threading
import unittest
from PIL import Image
from grocery_live import GroceryLiveObserver, validate_items
from grocery_driver import GroceryDriver
from grocery_vision import GroceryVision, GroceryRecognitionError
from grocery_plan import load_catalog, new_state, run_state

ROOT = Path(__file__).resolve().parent

class FastStop:
    def is_set(self): return False
    def wait(self, seconds): return False

class ReplayWindow:
    def __init__(self, product='10840089', mismatch=False):
        potion = product == '10840089'
        folder = ROOT/('verification/grocery-potion-live-20261031' if potion else 'verification/grocery-key-live-20261031')
        names = ('preflight-1.png','confirmation-1.png','confirm-one-potion-after.png') if potion else ('key-preflight-1.png','confirmation-preflight-1.png','confirm-one-key-after.png')
        self.frames = [Image.open(folder/name).convert('RGB') for name in names]
        self.stage, self.clicks, self.mismatch = 0, [], mismatch
        self.buy = (1128,800 if potion else 829)
    def calibrate(self, **kwargs): return self.capture()
    def capture(self): return self.frames[self.stage].copy()
    def click(self,x,y):
        self.clicks.append((x,y))
        if (x,y) == self.buy and self.stage == 0: self.stage=1
        elif (x,y) == (831,523) and self.stage == 1: self.stage=0 if self.mismatch else 2
        else: raise AssertionError('Unexpected/repeated input '+str((x,y)))

class GroceryLiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='grocery-live-',dir=ROOT/'verification')
        self.folder = Path(self.temp.name)
        self.items = {str(i['id']):i for i in load_catalog() if i['shop']=='moon'}
    def tearDown(self): self.temp.cleanup()
    def observer(self,window): return GroceryLiveObserver(window,GroceryVision(),self.folder,FastStop())
    def test_only_two_evidenced_items_pass_support_gate(self):
        validate_items([self.items['10800057'],self.items['10840089']])
        other = next(i for i in load_catalog() if i['shop']=='sun')
        with self.assertRaisesRegex(ValueError,'尚未接入'): validate_items([other])
    def test_both_real_purchase_sequences_pass_with_exactly_two_inputs(self):
        for product in ('10800057','10840089'):
            with self.subTest(product=product):
                window=ReplayWindow(product)
                driver=GroceryDriver(123,evidence_dir=self.folder,window=window,vision=GroceryVision(),purchase_enabled=True,stop_event=FastStop())
                item=self.items[product]
                state=new_state([item],{item['key']:1})
                result=run_state(state,self.folder/'state.json',driver)
                self.assertEqual(result['status'],'done',result['last_error'])
                self.assertEqual(result['items'][0]['completed'],1)
                self.assertEqual(window.clicks,[window.buy,(831,523)])
    def test_post_purchase_mismatch_is_uncertain_and_cannot_be_replayed(self):
        window=ReplayWindow(mismatch=True)
        driver=GroceryDriver(123,evidence_dir=self.folder,window=window,vision=GroceryVision(),purchase_enabled=True,stop_event=FastStop())
        item=self.items['10840089'];state=new_state([item],{item['key']:1});path=self.folder/'state.json'
        result=run_state(state,path,driver)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['items'][0]['completed'],0)
        run_state(result,path,driver)
        self.assertEqual(window.clicks,[window.buy,(831,523)])
    def test_disabled_game_confirmation_uses_one_purchase_click(self):
        window=ReplayWindow()
        def click(x,y):
            window.clicks.append((x,y))
            if (x,y)!=window.buy: raise AssertionError('No second click allowed')
            window.stage=2
        window.click=click
        driver=GroceryDriver(123,evidence_dir=self.folder,window=window,vision=GroceryVision(),purchase_enabled=True,stop_event=FastStop())
        item=self.items['10840089'];state=new_state([item],{item['key']:1})
        result=run_state(state,self.folder/'state.json',driver)
        self.assertEqual(result['status'],'done',result['last_error'])
        self.assertEqual(window.clicks,[window.buy])
    def test_quantity_feedback_mismatch_stops_before_purchase(self):
        from unittest.mock import Mock
        window=ReplayWindow();observer=self.observer(window)
        current=observer.read_item(window.frames[0],self.items['10840089'])
        observer._stable=Mock(side_effect=[current,dict(current)])
        window.click=lambda x,y: window.clicks.append((x,y))
        with self.assertRaisesRegex(GroceryRecognitionError,'数量按钮反馈'):
            observer.prepare_quantity(self.items['10840089'],2,current)
        self.assertNotIn(window.buy,window.clicks)
        self.assertNotIn((831,523),window.clicks)
    def test_real_ten_potion_confirmation_includes_full_quantity_and_total(self):
        observer=self.observer(ReplayWindow())
        image=Image.open(ROOT/'verification/grocery-ui-10potions-live-20261106/attempt4-game.png')
        data=observer.read_confirmation(image,self.items['10840089'],10,2000)
        self.assertIn('10个修行药水',data['text'])
        self.assertIn('2000月之印',data['text'])
        with self.assertRaises(GroceryRecognitionError): observer.read_confirmation(image,self.items['10840089'],1,200)

    def test_real_ten_potion_result_and_quantity_reset_are_read_only(self):
        from unittest.mock import Mock
        observer=self.observer(ReplayWindow())
        image=Image.open(ROOT/'verification/grocery-ui-10potions-live-20261106/game-after-attempt5.png')
        data=observer.read_item(image,self.items['10840089'])
        self.assertEqual((data['stock'],data['balances']['moon'],data['quantity']),(90,401945,1))
        before=dict(data,stock=100,balances=dict(data['balances'],moon=403945),quantity=10)
        observer._capture=Mock(return_value=image)
        observer.read_item=Mock(side_effect=[dict(data,quantity=10),data])
        result=observer.verify_result(self.items['10840089'],10,before)
        self.assertEqual(result['quantity'],10)
        self.assertEqual(result['stock'],90)
        self.assertFalse(observer.window.clicks)

    def test_confirmation_wrong_price_is_rejected(self):
        window=ReplayWindow();obs=self.observer(window)
        with self.assertRaises(GroceryRecognitionError):
            obs.read_confirmation(window.frames[1],self.items['10840089'],1,201)
        self.assertFalse(window.clicks)
    def test_duplicate_icon_is_rejected(self):
        window=ReplayWindow();obs=self.observer(window);image=window.frames[0].copy()
        image.paste(image.crop((967,668,1055,756)),(667,668))
        with self.assertRaisesRegex(GroceryRecognitionError,'多个候选'):
            obs.locate(image,self.items['10840089'])
    def test_image_matching_tracks_arbitrary_vertical_scroll_offset(self):
        window=ReplayWindow();obs=self.observer(window);image=window.frames[0].copy()
        card=image.crop((967,668,1250,885));image.paste((0,0,0),(967,668,1250,885));image.paste(card,(967,608))
        self.assertEqual(obs.locate(image,self.items['10840089']),[967,608,88,88])
    def test_real_quantities_one_through_ten_are_distinct_image_matches(self):
        observer=self.observer(ReplayWindow())
        f=ROOT/'verification/grocery-ui-10potions-live-20261106'
        for n in range(1,11):
            with self.subTest(quantity=n):
                data=observer.read_item(Image.open(f/f'quantity-source-{n}.png'),self.items['10840089'])
                self.assertEqual(data['quantity'],n)
                self.assertEqual(data['stock'],100)
                self.assertEqual(data['balances']['moon'],403945)

    def test_live_potion_label_excludes_decorative_nameplate_edges(self):
        image=Image.open(ROOT/'verification/grocery-ui-10potions-live-20261106/attempt2-game.png')
        observer=self.observer(ReplayWindow())
        data=observer.read_item(image,self.items['10840089'])
        self.assertEqual((data['name'],data['unit_price'],data['stock'],data['quantity']),('修行药水',200,100,1))
        self.assertEqual(data['balances']['moon'],403945)

    def test_live_scrollbar_thumb_has_unique_verified_bounds(self):
        observer=self.observer(ReplayWindow())
        f=ROOT/'verification/grocery-ui-10potions-live-20261106'
        self.assertEqual(observer.thumb_bounds(Image.open(f/'thumb-drag-before.png')),(467,860))
        self.assertEqual(observer.thumb_bounds(Image.open(f/'thumb-drag-after.png')),(366,760))
        with self.assertRaises(GroceryRecognitionError): observer.thumb_bounds(Image.new('RGB',(1920,1015),'black'))

    def test_stopped_observer_never_clicks(self):
        window=ReplayWindow();stop=threading.Event();stop.set()
        observer=GroceryLiveObserver(window,GroceryVision(),self.folder,stop)
        with self.assertRaises(InterruptedError): observer.inspect(self.items['10840089'])
        self.assertFalse(window.clicks)

if __name__=='__main__': unittest.main()
