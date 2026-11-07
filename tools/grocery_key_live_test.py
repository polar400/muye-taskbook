"""Bounded, evidence-led test of one cave key. Does not enable general buying.

Each input needs an already inspected screenshot and matching live guard crop.
Buy and confirmation inputs each have a durable one-use boundary; an uncertain
submission is never retried by this tool.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import ctypes
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grocery_plan import now, _write_json
from grocery_recognition import np
from PIL import Image, ImageOps

FOLDER = ROOT/'verification/grocery-key-live-20261031'


def active_worker_check():
    command = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(pythonw?|node)\\.exe$' "
               "-and $_.CommandLine -match '(native_worker\\.py|grocery_worker\\.py|worker\\.mjs)' } "
               "| Select-Object -ExpandProperty ProcessId")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True,
                            text=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    if result.stdout.strip():
        raise RuntimeError('另有任务工作进程运行，停止实机购买测试')


def window():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    from app import game_windows
    from adapters.background_window import BackgroundWindow
    candidates = game_windows()
    if len(candidates) != 1:
        raise RuntimeError('不能唯一定位360火影游戏窗口')
    result = BackgroundWindow(candidates[0][0])
    frame = result.capture()
    if frame.shape[:2] != (1015, 1920):
        raise RuntimeError('游戏区域不是1920×1015，不发送输入')
    return result


def read_test_balances(vision, image):
    """Test-local readers validated against this run's actual white digits.

    The older generic reader confidently confused 6/0 on this frame. Do not
    rewrite its strings or silently enable that reader for general purchases.
    """
    vision.require_page(image)
    balances,evidence={},{}
    for key,box in (('sun',(375,55,68,32)),('moon',(597,61,73,20)),('mystery',(1036,55,56,32))):
        text,reads=vision.read_text(image,box,r'(?:0|[1-9][0-9]{0,8})',only_rec=(key!='moon'))
        balances[key]=int(text); evidence[key]={'box':list(box),'reads':reads}
    patch=image.crop((825,60,877,82))
    patch=ImageOps.grayscale(patch).point(lambda value:255 if value>=220 else 0)
    patch=ImageOps.expand(patch,border=4,fill=0).convert('RGB')
    reads=[]
    for scale in (2,3):
        enlarged=patch.resize((patch.width*scale,patch.height*scale),Image.Resampling.LANCZOS)
        results=vision._ocr().read(np.asarray(enlarged)[:,:,::-1].copy(),only_rec=True)
        valid=[r for r in results if r.get('score',0)>=.9 and re.fullmatch(r'(?:0|[1-9][0-9]{0,8})',r.get('text','').strip())]
        if len(valid)!=1:raise RuntimeError('签到令前景数字未得到唯一高分读数')
        reads.append({'text':valid[0]['text'].strip(),'score':valid[0]['score'],'scale':scale})
    if reads[0]['text']!=reads[1]['text']:raise RuntimeError('签到令双视图读数不一致')
    balances['sign']=int(reads[0]['text'])
    evidence['sign']={'box':[825,60,52,22],'threshold':220,'reads':reads}
    return balances,evidence


def observe_key(w, persist=True):
    from grocery_vision import GroceryVision
    from grocery_recognition import GroceryRecognizer
    vision, recognizer = GroceryVision(), GroceryRecognizer()
    reads=[]
    for index in range(2):
        frame=w.capture()
        image=Image.fromarray(frame[:,:,::-1])
        if persist:image.save(FOLDER/f'key-preflight-{index+1}.png')
        icon=recognizer.recognize_region(image,(967,697,88,88),shop='moon')
        name,nr=vision.read_text(image,(981,881,174,33),r'洞穴密钥')
        price,pr=vision.read_text(image,(1112,712,63,32),r'[1-9][0-9]{0,7}')
        stock,sr=vision.read_text(image,(1062,748,112,32),r'库存(?:0|[1-9][0-9]{0,7})')
        quantity,qr=vision.read_text(image,(977,806,30,37),r'[1-9][0-9]{0,3}')
        balances,balance_evidence=read_test_balances(vision,image)
        reads.append({'at':now(),'name':name,'id':icon.get('item',{}).get('id'),'shop':'moon',
                      'quantity':int(quantity),'unit_price':int(price),'stock':int(stock[2:]),'balances':balances,
                      'icon':icon,'ocr':{'name':nr,'price':pr,'stock':sr,'quantity':qr,'balances':balance_evidence},
                      'verified':icon['status']=='recognized' and icon.get('asset')=='item_10800057'})
    fields=('name','id','quantity','unit_price','stock','balances','verified')
    if any(reads[0][key]!=reads[1][key] for key in fields):
        raise RuntimeError('两帧购买前复核不一致')
    result=deepcopy(reads[-1])
    if (not result['verified'] or result['quantity']!=1 or result['stock']<1
            or result['balances']['moon']<result['unit_price']):
        raise RuntimeError('单件洞穴密钥购买条件不满足')
    result['guard_boxes']=[[320,45,835,50],[1435,42,111,91],[967,697,88,88],
                           [1112,712,63,32],[1062,748,112,32],[977,806,30,37],[981,881,174,33]]
    result['reads']=reads
    if persist:_write_json(FOLDER/'purchase-preflight.json',result)
    return result


def observe_confirmation(w, persist=True):
    from grocery_vision import GroceryVision
    vision=GroceryVision()
    pattern=r'确定购买(?P<quantity>[1-9][0-9]*)个洞穴密钥[，,]共花费(?P<total>[1-9][0-9]*)月之印[?？]'
    rows=[]
    for index in range(2):
        image=Image.fromarray(w.capture()[:,:,::-1])
        if persist:image.save(FOLDER/f'confirmation-preflight-{index+1}.png')
        message,reads=vision.read_text(image,(742,438,435,36),pattern,minimum=.9)
        parsed=re.fullmatch(pattern,message)
        if int(parsed['quantity'])!=1 or int(parsed['total'])!=200:
            raise RuntimeError('确认弹窗不是1个洞穴密钥／200月之印')
        rows.append({'message':message,'reads':reads})
    if rows[0]['message']!=rows[1]['message']:raise RuntimeError('两帧确认弹窗不一致')
    result={'at':now(),'name':'洞穴密钥','id':'10800057','quantity':1,'total':200,'verified':True,
            'reads':rows,'guard_boxes':[[742,438,435,36],[757,499,154,49]]}
    if persist:_write_json(FOLDER/'confirmation-preflight.json',result)
    return result


def guarded_click(w, source, box, point, label, consuming=False):
    active_worker_check()
    if label in ('buy-one-key','confirm-one-key') and not consuming:
        raise RuntimeError('购买及确认必须走单次消费校验')
    journal_path = FOLDER/'input-journal.json'
    journal = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {'actions': []}
    if any(row['label'] == label for row in journal['actions']):
        raise RuntimeError('该动作已经记录，禁止自动重放：'+label)
    if consuming:
        if label not in ('buy-one-key', 'confirm-one-key'):
            raise RuntimeError('只授权洞穴密钥单次购买')
        preflight = json.loads((FOLDER/'purchase-preflight.json').read_text(encoding='utf-8'))
        if (preflight.get('name') != '洞穴密钥' or preflight.get('id') != '10800057'
                or preflight.get('shop') != 'moon' or preflight.get('quantity') != 1
                or preflight.get('verified') is not True):
            raise RuntimeError('单件洞穴密钥购买前证据无效')
        if label == 'confirm-one-key' and not any(a['label']=='buy-one-key' for a in journal['actions']):
            raise RuntimeError('没有本轮单次购买记录，不发送确认')
        if label == 'buy-one-key':
            live=observe_key(w,persist=False)
            if any(live[key]!=preflight[key] for key in ('name','id','shop','quantity','unit_price','stock','balances')):
                raise RuntimeError('实时购买字段与预检查不同，不发送购买')
        else:
            confirmation=json.loads((FOLDER/'confirmation-preflight.json').read_text(encoding='utf-8'))
            live=observe_confirmation(w,persist=False)
            if (confirmation.get('verified') is not True or live['quantity']!=preflight['quantity']
                    or live['total']!=preflight['unit_price']):
                raise RuntimeError('确认弹窗与购买授权不一致')
            preflight['guard_boxes']=confirmation['guard_boxes']
    before = w.capture()
    with Image.open(source) as reference:
        expected = reference.convert('RGB')
    current = Image.fromarray(before[:,:,::-1])
    x,y,width,height = box
    a = np.asarray(current.crop((x,y,x+width,y+height)), dtype=np.float32)
    b = np.asarray(expected.crop((x,y,x+width,y+height)), dtype=np.float32)
    error = float(np.abs(a-b).mean()/255)
    if a.shape != b.shape or error > .015 or float(b.std()) < 5:
        current.save(FOLDER/(label+'-rejected-frame.png'))
        raise RuntimeError(f'发送前画面与已核对证据不一致：{label}，误差{error:.4f}')
    if not (x <= point[0] < x+width and y <= point[1] < y+height):
        raise RuntimeError('点击不在核对过的区域中')
    if consuming:
        # Full header, item/name/quantity card, and modal (if any) are also guarded.
        for critical in preflight.get('guard_boxes', []):
            gx,gy,gw,gh=critical
            aa=np.asarray(current.crop((gx,gy,gx+gw,gy+gh)),dtype=np.float32)
            bb=np.asarray(expected.crop((gx,gy,gx+gw,gy+gh)),dtype=np.float32)
            if float(np.abs(aa-bb).mean()/255) > .015:
                raise RuntimeError('购买前商品、数量或货币区域发生变化，不发送')
    current.save(FOLDER/(label+'-before.png'))
    row={'at':now(),'label':label,'point':list(point),'guard_box':list(box),'error':error,
         'consuming':consuming,'status':'input_outcome_unknown'}
    journal['actions'].append(row)
    _write_json(journal_path,journal)
    w.click(*point)
    time.sleep(.8)
    after=w.capture()
    w.save(after,FOLDER/(label+'-after.png'))
    row['status']='sent_once_result_requires_visual_verification'
    _write_json(journal_path,journal)
    print(json.dumps(row,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--source',required=True)
    parser.add_argument('--box',nargs=4,type=int,required=True)
    parser.add_argument('--point',nargs=2,type=int,required=True)
    parser.add_argument('--consuming',action='store_true')
    args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    guarded_click(window(),Path(args.source),tuple(args.box),tuple(args.point),args.label,args.consuming)


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    main()
