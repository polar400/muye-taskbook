"""Production grocery observer for the two evidence-backed moon-store items."""
from pathlib import Path
import hashlib
import json
import re
import time
from grocery_vision import GroceryRecognitionError, crop, patch_similarity, patch_near, to_rgb
import numpy as np
from PIL import Image
from grocery_scroll import scroll_once, drag_thumb

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {'10800057': '洞穴密钥', '10840089': '修行药水'}
NOTICE = '可购买：月商店的洞穴密钥、修行药水。其他商品暂仅展示和保存预设。'


def supports_item(item):
    return item.get('shop') == 'moon' and SUPPORTED.get(str(item.get('id'))) == item.get('name')


def validate_items(items):
    unsupported = [i['name'] for i in items if i.get('status') not in ('done', 'skipped') and not supports_item(i)]
    if unsupported:
        raise ValueError('尚未接入购买：'+'、'.join(unsupported)+'。'+NOTICE)


class GroceryLiveObserver:
    supports_verified_purchase = True

    def __init__(self, window, vision, folder, stop_event, emit=lambda event: None):
        self.window, self.vision, self.folder, self.stop = window, vision, Path(folder), stop_event
        self.emit = emit
        self.references = {}
        assets = ROOT/'resources/local/grocery/purchase'
        for row in json.loads((assets/'sources.json').read_text(encoding='utf-8')):
            path = assets/(row['key']+'.png')
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise GroceryRecognitionError('杂货屋购买参考图校验失败')
            with Image.open(path) as image: self.references[row['key']] = image.convert('RGB')
        self.sequence = 0
        self.used = set()

    def _check(self):
        if self.stop.is_set(): raise InterruptedError('杂货屋已停止')

    def _capture(self):
        self._check()
        return to_rgb(self.window.capture())

    def _pause(self, seconds=.15):
        if self.stop.wait(seconds): self._check()

    def _save(self, image, label):
        self.sequence += 1
        self.folder.mkdir(parents=True, exist_ok=True)
        image.save(self.folder/f'live-{self.sequence:04d}-{label}.png')

    def _moon(self, image):
        try:
            self.vision.require_page(image)
        except GroceryRecognitionError:
            return False
        score, error, _ = patch_near(image, (1435,42,111,91), self.references['moon-tab'])
        return score >= .97 and error <= .025

    def begin(self):
        a = self.vision.read_balances(self._capture())
        self._pause()
        image = self._capture()
        b = self.vision.read_balances(image)
        if a != b: raise GroceryRecognitionError('两帧货币余额不一致')
        self._save(image, 'balances')
        return b

    def locate(self, image, item):
        if not supports_item(item): raise GroceryRecognitionError('该商品尚未接入实机购买')
        if not self._moon(image): raise GroceryRecognitionError('未确认月商店激活状态')
        key = 'key-icon' if str(item['id']) == '10800057' else 'potion-icon'
        template = self.references[key]
        target = np.asarray(template.resize((22,22)),dtype=np.float32).mean(axis=2)
        target -= target.mean()
        target_norm = np.linalg.norm(target)
        hits = []
        # The calibrated shop has four fixed columns; vertical positions vary
        # continuously after scrolling. Coarse matching uses small NumPy arrays,
        # then validates full-resolution candidates without an OpenCV dependency.
        for column_x in (367,667,967,1267):
            strip = image.crop((column_x,130,column_x+88,890)).resize((22,190))
            grey = np.asarray(strip,dtype=np.float32).mean(axis=2)
            windows = np.lib.stride_tricks.sliding_window_view(grey,(22,22))[:,0]
            centered = windows-windows.mean(axis=(1,2),keepdims=True)
            norms = np.linalg.norm(centered,axis=(1,2))*target_norm
            scores = (centered*target).sum(axis=(1,2))/np.maximum(norms,1e-8)
            for _ in range(3):
                row = int(scores.argmax())
                if scores[row] < .75: break
                scores[max(0,row-16):row+17] = -1
                best = None
                for y in range(max(130,130+row*4-5), min(803,130+row*4+6)):
                    for x in (column_x-1,column_x,column_x+1):
                        score,error = patch_similarity(crop(image,(x,y,88,88)),template)
                        candidate = (score,-error,x,y)
                        if best is None or candidate > best: best = candidate
                if best and best[0] >= .94 and -best[1] <= .04:
                    hits.append(best)
        if not hits: return None
        if len(hits) != 1: raise GroceryRecognitionError('目标商品出现多个候选')
        _,_,x,y = hits[0]
        # Never use a clipped card or controls hidden below the shelf.
        if y+217 > 915: return None
        return [x,y,88,88]

    def read_item(self, image, item, box=None):
        box = self.locate(image, item) if box is None else box
        if box is None: raise GroceryRecognitionError('目标商品不在完整可见区域')
        x,y,_,_ = box
        if self.locate(image,item) != box: raise GroceryRecognitionError('商品位置已变化')
        icon = self.vision.recognizer.recognize_region(image, tuple(box), shop='moon')
        if icon.get('status') != 'recognized' or icon.get('asset') != item['asset']:
            raise GroceryRecognitionError('商品图标身份不符')
        name_box=(x+48,y+185,140,30) if str(item['id'])=='10840089' else (x+14,y+184,174,33)
        self.vision.read_text(image,name_box,re.escape(item['name']),minimum=.9)
        price,_ = self.vision.read_text(image,(x+145,y+15,63,32),r'[1-9][0-9]{0,7}')
        stock_patch = crop(image,(x+95,y+51,112,32))
        matches = []
        for key, ref in self.references.items():
            if key.startswith('stock-'):
                score,error = patch_similarity(stock_patch,ref)
                if score >= .995 and error <= .008: matches.append(int(key[6:]))
        if len(matches) > 1: raise GroceryRecognitionError('库存参考图匹配不唯一')
        if matches:
            stock = matches[0]
        else:
            stock_text,_ = self.vision.read_text(image,(x+95,y+51,112,32),r'库存(?:0|[1-9][0-9]{0,7})')
            stock = int(stock_text[2:])
        quantity_patch=crop(image,(x+10,y+109,42,37))
        quantity_matches=[]
        for key,ref in self.references.items():
            if key.startswith('quantity-'):
                score,error=patch_similarity(quantity_patch,ref)
                if score>=.995 and error<=.008: quantity_matches.append(int(key[9:]))
        if len(quantity_matches)>1: raise GroceryRecognitionError('购买数量图样不唯一')
        if quantity_matches:
            quantity=quantity_matches[0]
        else:
            quantity,_ = self.vision.read_text(image,(x+10,y+109,30,37),r'[1-9][0-9]{0,3}')
        return dict(verified=True,shop='moon',asset=item['asset'],name=item['name'],
                    unit_price=int(price),stock=stock,quantity=int(quantity),
                    balances=self.vision.read_balances(image),box=box)

    def _stable(self, item, box=None):
        first = self.read_item(self._capture(),item,box)
        self._pause()
        image = self._capture()
        second = self.read_item(image,item,box)
        if first != second: raise GroceryRecognitionError('两帧商品或余额不稳定')
        self._save(image,'item')
        return second

    def thumb_bounds(self,image):
        strip=np.asarray(image)[175:866,1564:1571]
        mask=(strip.min(axis=2)>200).sum(axis=1)>=3
        runs=[];start=None
        for index,active in enumerate(list(mask)+[False]):
            if active and start is None: start=index+175
            if not active and start is not None:
                if index+175-start>=80: runs.append((start,index+175-1))
                start=None
        if len(runs)!=1: raise GroceryRecognitionError('滚动条滑块不能唯一定位')
        return runs[0]

    def inspect(self, item):
        validate_items([item])
        image = self._capture()
        self.vision.require_page(image)
        if not self._moon(image):
            self.window.click(1488,85)
            self._pause(.5)
            image = self._capture()
            if not self._moon(image): raise GroceryRecognitionError('切换月商店后未确认激活状态')
        if self.locate(image,item) is not None: return self._stable(item)
        # Arrow holds of 1.6s can cross the whole list. Scan overlapping thumb
        # positions instead; each actual drag still lasts a continuous 1.6s.
        for fraction in (0,.15,.30,.45,.60,.75,.90,1):
            image=self._capture()
            if not self._moon(image): raise GroceryRecognitionError('拖动前店铺状态变化')
            top,bottom=self.thumb_bounds(image)
            self._pause()
            if self.thumb_bounds(self._capture()) != (top,bottom):
                raise GroceryRecognitionError('滚动条位置不稳定')
            height=bottom-top
            destination=175+(866-175-height)*fraction+height/2
            self.emit({'kind':'status','message':f"正在查找{item['name']}，列表位置{round(fraction*100)}%"})
            self._save(image,'before-thumb-drag')
            if not drag_thumb(self.window,(top+bottom)/2,destination,cancelled=self.stop.is_set): self._check()
            self._pause(.25)
            image=self._capture()
            if self.locate(image,item) is not None: return self._stable(item)
        raise GroceryRecognitionError('有限滚动后未找到完整目标商品，停止本轮')

    def prepare_quantity(self,item,quantity,inspection):
        current = self._stable(item,inspection['box'])
        for field in ('unit_price','stock','balances','asset','name'):
            if current[field] != inspection[field]: raise GroceryRecognitionError('设置数量前商品状态变化')
        if not 1 <= quantity <= min(9999,current['stock']): raise ValueError('购买数量超出当前库存或9999')
        while current['quantity'] != quantity:
            self._check()
            delta = 1 if current['quantity'] < quantity else -1
            x,y,_,_ = current['box']
            self.window.click(x+70,y+(116 if delta>0 else 140))
            self._pause(.1)
            updated = self._stable(item,current['box'])
            if updated['quantity'] != current['quantity']+delta:
                raise GroceryRecognitionError('数量按钮反馈不符，未发送购买')
            for field in ('unit_price','stock','balances'):
                if updated[field] != current[field]: raise GroceryRecognitionError('修改数量期间商品状态变化')
            current = updated

    def confirm_ready(self,item,quantity,inspection):
        return self._stable(item,inspection['box'])

    def read_confirmation(self,image,item,quantity,total):
        pattern = rf'确定购买{quantity}个{re.escape(item["name"])}[，,]共花费{total}月之印[?？]'
        button_matches=[patch_near(image,(757,499,154,49),ref) for key,ref in self.references.items() if key.startswith('confirm-button')]
        score,error,(dx,dy)=max(button_matches,key=lambda row:row[0])
        if score < .97 or error > .025: raise GroceryRecognitionError('确认按钮外观未确认')
        # Bulk quantities and totals expand the centered text line. Keep its
        # whole first/last glyph and follow the independently matched button.
        padding=5*max(0,len(str(quantity))+len(str(total))-4)
        box=(742-padding//2+dx,438+dy,435+padding,36)
        text,reads=self.vision.read_text(image,box,pattern,minimum=.9)
        return dict(text=text,reads=reads,box=list(box),button_score=score,button_error=error)

    def submit_once(self,item,quantity,before):
        key = (item['key'],item.get('completed',0))
        if key in self.used: raise RuntimeError('本项消费动作已经发出，禁止重放')
        current = self._stable(item,before['box'])
        if current != before: raise GroceryRecognitionError('购买发送前页面发生变化')
        self.used.add(key)
        x,y,_,_ = before['box']
        image = self._capture()
        if self.read_item(image,item,before['box']) != before: raise GroceryRecognitionError('发送前复核发生变化')
        self._save(image,'before-buy')
        self.window.click(x+161,y+132)
        self._pause(.5)
        # If purchase confirmation was disabled in game, do not click anything
        # else: only accept independently verified exact debit and stock changes.
        image = self._capture()
        if self._moon(image): return
        first_confirmation=self.read_confirmation(image,item,quantity,quantity*before['unit_price'])
        self._pause()
        image = self._capture()
        second_confirmation=self.read_confirmation(image,item,quantity,quantity*before['unit_price'])
        self._save(image,'confirmation')
        (self.folder/'confirmation-ready.json').write_text(json.dumps(dict(item=item['name'],quantity=quantity,total=quantity*before['unit_price'],first=first_confirmation,second=second_confirmation),ensure_ascii=False,indent=2),encoding='utf-8')
        self.window.click(831,523)
        self._pause(.5)

    def verify_result(self,item,quantity,before):
        expected=dict(before['balances'])
        expected['moon']-=quantity*before['unit_price']
        fields=('asset','name','unit_price','stock','balances','box')
        error=None
        # Only read while asynchronous debit/stock/quantity-reset feedback
        # settles. Never retry a purchase or confirmation input here.
        for attempt in range(4):
            try:
                first=self.read_item(self._capture(),item,before['box'])
                self._pause()
                image=self._capture()
                second=self.read_item(image,item,before['box'])
                if (all(first[key]==second[key] for key in fields)
                        and second['stock']==before['stock']-quantity
                        and second['balances']==expected):
                    self._save(image,'after-purchase')
                    return dict(verified=True,quantity=quantity,stock=second['stock'],balances=second['balances'])
                error=GroceryRecognitionError('购买后扣币或库存变化未确认，请核对游戏；不会重买')
            except GroceryRecognitionError as failure:
                error=failure
            if attempt<3:self._pause(.2)
        raise error
