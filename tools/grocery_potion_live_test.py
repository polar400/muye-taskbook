"""One authorized practice-potion purchase; evidence-led background input only."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from tools import grocery_key_live_test as common
from grocery_plan import now,_write_json
from grocery_vision import GroceryVision
from grocery_recognition import GroceryRecognizer,np
from grocery_scroll import SCROLL_SECONDS, ARROW_BOXES, ARROW_POINTS, scroll_once
from PIL import Image

FOLDER=ROOT/'verification/grocery-potion-live-20261031'


def capture(w,name):
    image=Image.fromarray(w.capture()[:,:,::-1])
    image.save(FOLDER/name)
    return image


def guard(current,reference,boxes):
    for x,y,width,height in boxes:
        a=np.asarray(current.crop((x,y,x+width,y+height)),dtype=np.float32)
        b=np.asarray(reference.crop((x,y,x+width,y+height)),dtype=np.float32)
        if float(b.std())<5 or float(np.abs(a-b).mean()/255)>.015:
            raise RuntimeError('发送前图像与已核对证据不一致，不发送输入')


def fields(vision,recognizer,image,box):
    x,y,width,height=box
    icon=recognizer.recognize_region(image,tuple(box),shop='moon')
    if icon.get('asset')!='item_10840089' or icon.get('status')!='recognized':
        raise RuntimeError('没有唯一识别修行药水图标')
    name,nr=vision.read_text(image,(x+14,y+184,174,33),r'修行药水')
    price,pr=vision.read_text(image,(x+145,y+15,63,32),r'[1-9][0-9]{0,7}')
    stock,sr=vision.read_text(image,(x+95,y+51,112,32),r'库存(?:0|[1-9][0-9]{0,7})')
    quantity,qr=vision.read_text(image,(x+10,y+109,30,37),r'[1-9][0-9]{0,3}')
    balances,br=common.read_test_balances(vision,image)
    return {'name':name,'id':'10840089','shop':'moon','asset':icon['asset'],'quantity':int(quantity),
            'unit_price':int(price),'stock':int(stock[2:]),'balances':balances,'icon_box':list(box),
            'evidence':{'icon':icon,'name':nr,'price':pr,'stock':sr,'quantity':qr,'balances':br}}


def observe(w,box,persist=True):
    vision,recognizer=GroceryVision(),GroceryRecognizer();reads=[]
    for index in range(2):
        image=Image.fromarray(w.capture()[:,:,::-1])
        if persist:image.save(FOLDER/f'preflight-{index+1}.png')
        reads.append(fields(vision,recognizer,image,box))
    for key in ('name','id','shop','quantity','unit_price','stock','balances'):
        if reads[0][key]!=reads[1][key]:raise RuntimeError('修行药水两帧字段不一致')
    result=deepcopy(reads[-1]);result.update(at=now(),verified=True,reads=reads)
    if result['quantity']!=1 or result['unit_price']!=200 or result['stock']<1 or result['balances']['moon']<200:
        raise RuntimeError('本轮1瓶／200月之币购买条件不符')
    if persist:_write_json(FOLDER/'purchase-preflight.json',result)
    return result


def confirmation(w,persist=True):
    vision=GroceryVision();rows=[]
    pattern=r'确定购买(?P<quantity>[1-9][0-9]*)个修行药水[，,]共花费(?P<total>[1-9][0-9]*)月之印[?？]'
    for index in range(2):
        image=Image.fromarray(w.capture()[:,:,::-1])
        if persist:image.save(FOLDER/f'confirmation-{index+1}.png')
        text,reads=vision.read_text(image,(742,438,435,36),pattern,minimum=.9)
        parsed=re.fullmatch(pattern,text)
        if int(parsed['quantity'])!=1 or int(parsed['total'])!=200:raise RuntimeError('确认数量或总价不符')
        rows.append({'text':text,'reads':reads})
    result={'at':now(),'verified':True,'quantity':1,'total':200,'name':'修行药水','reads':rows}
    if persist:_write_json(FOLDER/'confirmation-preflight.json',result)
    return result


def send(w,label,source,boxes,point,duration=None):
    common.active_worker_check()
    path=FOLDER/'input-journal.json'
    journal=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'actions':[]}
    if any(row['label']==label for row in journal['actions']):raise RuntimeError('动作已记录，禁止重放')
    direction = next((d for d in ARROW_POINTS if label.startswith(f'scroll-{d}-1600ms-')), None)
    if label=='buy-one-potion':
        before=json.loads((FOLDER/'purchase-preflight.json').read_text(encoding='utf-8'))
        live=observe(w,before['icon_box'],persist=False)
        if any(before[k]!=live[k] for k in ('name','id','quantity','unit_price','stock','balances')):
            raise RuntimeError('购买前字段变化，不发送')
    elif label=='confirm-one-potion':
        if not any(row['label']=='buy-one-potion' for row in journal['actions']):raise RuntimeError('没有本轮购买记录')
        confirmation(w,persist=False)
    elif direction is None:
        raise RuntimeError('只允许本轮单件购买或1.6秒向上／向下滚动')
    if direction is not None and duration!=SCROLL_SECONDS:
        raise RuntimeError('向上向下滑动必须1.6秒')
    if direction is not None and (tuple(point)!=ARROW_POINTS[direction] or tuple(ARROW_BOXES[direction]) not in [tuple(b) for b in boxes]):
        raise RuntimeError('滚动坐标或核对区域与方向不符')
    if label in ('buy-one-potion','confirm-one-potion') and duration is not None:
        raise RuntimeError('购买和确定只能单击一次')
    current=capture(w,label+'-before.png')
    with Image.open(source) as reference:guard(current,reference.convert('RGB'),boxes)
    if not any(x<=point[0]<x+width and y<=point[1]<y+height for x,y,width,height in boxes):
        raise RuntimeError('输入坐标不在已核对区域内')
    row={'at':now(),'label':label,'point':list(point),'consuming':label in ('buy-one-potion','confirm-one-potion'),
         'status':'input_outcome_unknown'}
    if duration is not None:row.update(duration_seconds=duration,direction=direction)
    journal['actions'].append(row);_write_json(path,journal)
    if duration is None:w.click(*point)
    else:
        start=time.monotonic();ok=scroll_once(w,direction)
        row['actual_hold_seconds']=time.monotonic()-start
        if not ok:raise RuntimeError('滚动中断，已释放')
    time.sleep(.8 if duration is None else .4)
    capture(w,label+'-after.png');row['status']='sent_once_result_requires_verification';_write_json(path,journal)
    print(json.dumps(row,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['scroll','observe','buy','confirmation','confirm'])
    parser.add_argument('--source');parser.add_argument('--label')
    parser.add_argument('--direction',choices=['up','down'],default='down')
    parser.add_argument('--box',nargs=4,type=int)
    args=parser.parse_args();FOLDER.mkdir(parents=True,exist_ok=True);w=common.window()
    if args.action=='scroll':
        send(w,args.label or f'scroll-{args.direction}-1600ms-1',Path(args.source),
             [ARROW_BOXES[args.direction]],ARROW_POINTS[args.direction],SCROLL_SECONDS)
    elif args.action=='observe':print(json.dumps(observe(w,args.box),ensure_ascii=False))
    elif args.action=='confirmation':print(json.dumps(confirmation(w),ensure_ascii=False))
    elif args.action=='confirm':send(w,'confirm-one-potion',Path(args.source),[(742,438,435,36),(757,499,154,49)],(831,523))
    elif args.action=='buy':
        pre=json.loads((FOLDER/'purchase-preflight.json').read_text(encoding='utf-8'));x,y,_,_=pre['icon_box']
        send(w,'buy-one-potion',Path(args.source),[(320,45,835,50),(1435,42,111,91),(x,y,88,88),
              (x+145,y+15,63,32),(x+95,y+51,112,32),(x+10,y+109,30,37),(x+14,y+184,174,33),
              (x+95,y+105,140,57)],(x+161,y+132))


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    main()
