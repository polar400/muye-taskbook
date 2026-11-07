"""Read ranked power glyphs locally; unknown or conflicting digits fail closed."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
from PIL import Image

def read_ranked_remaining(image,items,ocr,normalize):
    height,width=image.shape[:2]
    counters=[item for item in items if item['box'][0]>width*.7 and item['box'][1]<height*.2]
    strict=r'^[()（）]*剩余挑战次数:?(\d{1,2})$'
    values=[int(match.group(1)) for item in counters
            if item.get('score',1)>=.8 and (match:=re.fullmatch(strict,normalize(item['text'])))]
    if values:
        if len(set(values))!=1:raise RuntimeError('排位战剩余次数识别冲突')
        count=values[0]
    else:
        # OCR confuses 挑 with 共 and 数 with 教 in this gold caption. These
        # aliases apply only to the counter strip, and need a second reading.
        pattern=r'^[()（）]*剩余(?:挑战|共战)次(?:数|教|救)?:?(\d{1,2})$'
        readings=[];anchors=[]
        def add(words,offset=(0,0),scale=1):
            for item in words:
                match=re.fullmatch(pattern,normalize(item['text']))
                if match and item.get('score',1)>=.8:
                    readings.append(int(match.group(1)))
                    if 'box' in item:
                        bx,by,bw,bh=item['box']
                        box=[offset[0]+round(bx/scale),offset[1]+round(by/scale),round(bw/scale),round(bh/scale)]
                        if width*.7<box[0]<width and 0<=box[1]<height*.2 and box[2]>0 and box[3]>0:
                            anchors.append(box)
        add(counters)
        x=round(width*1550/1920);y=round(height*70/1015)
        region=image[y:round(height*145/1015),x:round(width*1880/1920)].copy()
        for scale in (1,3):
            source=region if scale==1 else np.array(Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale)))
            add(ocr.read(source),(x,y),scale)
            if len(set(readings))>1:raise RuntimeError('排位战剩余次数局部识别冲突')
            if len(readings)>=2:break
        # The wide strip also contains decorative icons and the plus button.
        # If it cannot corroborate a valid full-screen caption, isolate that
        # caption once. Keep the complete text grammar and score gate; never
        # recover a count by accepting a minus sign or guessing a lone digit.
        if len(readings)<2 and len(anchors)==1:
            ax,ay,aw,ah=anchors[0]
            px=round(width*12/1920);py=round(height*10/1015)
            local=image[max(0,ay-py):min(height,ay+ah+py),
                        max(0,ax-px):min(width,ax+aw+px)].copy()
            if local.size:
                source=np.array(Image.fromarray(local).resize((local.shape[1]*3,local.shape[0]*3)))
                add(ocr.read(source))
                if len(set(readings))>1:raise RuntimeError('排位战剩余次数局部识别冲突')
        if len(readings)<2:raise RuntimeError('无法可靠读取剩余次数')
        count=readings[0]
    if not 0<=count<=20:raise RuntimeError('排位战剩余次数识别异常')
    return count

def split_glyphs(mask):
    groups=[];start=None
    for x,occupied in enumerate([*np.any(mask,axis=0),False]):
        if occupied and start is None:start=x
        if not occupied and start is not None:
            ys,_=np.where(mask[:,start:x])
            groups.append(mask[ys.min():ys.max()+1,start:x]);start=None
    return groups

@lru_cache(maxsize=1)
def power_templates():
    return [(path.name.split('digit')[1][0],np.array(Image.open(path).convert('L'))<128)
            for path in (ROOT/'resources/local/image').glob('ranked_power_digit*_*.png')]

def glyph_image(glyph,scale=4):
    source=Image.fromarray(np.where(glyph,0,255).astype('uint8')).convert('RGB')
    padded=Image.new('RGB',(source.width+12,source.height+12),'white')
    padded.paste(source,(6,6))
    return np.array(padded.resize((padded.width*scale,padded.height*scale)))

def read_red_power(image,ocr):
    h,w=image.shape[:2]
    # Numeric red artwork to the right of the own-power caption; no input.
    region=image[int(h*.084):int(h*.145),int(w*.09):int(w*.27),::-1].astype('float32')
    r,g,b=(region[:,:,index] for index in range(3))
    glyphs=split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))
    if not 4<=len(glyphs)<=9:raise RuntimeError('我方战力红色数字未完整识别')
    digits=[]
    for glyph in glyphs:
        scores={}
        for digit,template in power_templates():
            aspect=(glyph.shape[1]/glyph.shape[0])/(template.shape[1]/template.shape[0])
            if not .85<aspect<1.15:continue
            resized=np.array(Image.fromarray(glyph).resize((template.shape[1],template.shape[0]),Image.Resampling.NEAREST))
            similarity=np.count_nonzero(resized&template)/max(1,np.count_nonzero(resized|template))
            scores[digit]=max(scores.get(digit,0),similarity)
        ranked=sorted(scores.items(),key=lambda item:item[1],reverse=True)
        if ranked and ranked[0][1]>=.92 and (len(ranked)==1 or ranked[0][1]-ranked[1][1]>.08):
            digits.append(ranked[0][0]);continue
        # For glyphs not yet in the verified artwork set, require agreement
        # from two renderings; never substitute letters or guessed numbers.
        readings=[]
        for scale in (3,4):
            items=ocr.read(glyph_image(glyph,scale),only_rec=True)
            if len(items)==1 and items[0]['score']>=.9 and re.fullmatch(r'[0-9]',items[0]['text']):readings.append(items[0]['text'])
        if len(readings)!=2 or readings[0]!=readings[1]:raise RuntimeError('我方战力包含无法复核的数字，停止')
        digits.append(readings[0])
    value=int(''.join(digits))
    if value<=0:raise RuntimeError('我方战力数字无效')
    return value


def white_ink(rgb,threshold):
    rgb=rgb.astype('int16')
    return (np.min(rgb,axis=2)>threshold)&(np.ptp(rgb,axis=2)<50)


@lru_cache(maxsize=1)
def white_power_templates():
    """Explicitly opt in the verified serif family, without copying catalog PNGs."""
    catalog=ROOT/'resources/local/catalog'
    try:
        bank=json.loads((catalog/'digits/index.json').read_text(encoding='utf-8'))
        family=next(f for f in bank['families'] if f['id']=='white_serif_small')
        if set(family['digits'])!=set('0123456789'):return ()
        templates=[]
        for digit,ref in family['digits'].items():
            path=catalog/ref['catalogPath']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:return ()
            with Image.open(path) as source:
                mask=white_ink(np.array(source.convert('RGB')),190)
            ys,xs=np.where(mask)
            if not len(xs):return ()
            templates.append((digit,mask[ys.min():ys.max()+1,xs.min():xs.max()+1]))
        return tuple(templates)
    except (OSError,ValueError,KeyError,StopIteration):
        return ()


def white_digit_candidates(mask,templates):
    """Search alternative cuts through touching ink, retaining two strings per length."""
    ys,xs=np.where(mask)
    if not len(xs):return []
    mask=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
    height,width=mask.shape
    if not 12<=height<=14 or not 20<=width<=100 or mask.mean()>.8:return []
    variants=[]
    for digit,template in templates:
        expected=template.shape[1]*height/template.shape[0]
        for w in range(max(3,round(expected)-1),round(expected)+2):
            resized=np.array(Image.fromarray(template).resize((w,height),Image.Resampling.NEAREST))
            variants.append((digit,resized))
    paths={(0,0):[(0.,'',1.)]}
    def keep(key,values):
        best={}
        for value in paths.get(key,[])+values:
            if value[1] not in best or value[0]<best[value[1]][0]:best[value[1]]=value
        paths[key]=sorted(best.values())[:2]
    for x in range(width):
        for length in range(9):
            previous=paths.get((x,length))
            if not previous:continue
            if not mask[:,x].any():
                end=x
                while end<width and not mask[:,end].any():end+=1
                if end-x<=3:keep((end,length),previous)
                continue
            for digit,template in variants:
                end=x+template.shape[1]
                if end>width:continue
                part=mask[:,x:end]
                score=np.count_nonzero(part&template)/max(1,np.count_nonzero(part|template))
                if score<.55:continue
                keep((end,length+1),[(cost+1-score,text+digit,min(minimum,score))
                                    for cost,text,minimum in previous])
    return sorted((cost/length,text,minimum) for length in range(4,10)
                  for cost,text,minimum in paths.get((width,length),[]))


def read_white_power(image,item):
    """Return a conservative template fallback, or None for unknown/ambiguous ink."""
    templates=white_power_templates()
    if not templates:return None
    x,y,w,h=item['box'];height,width=image.shape[:2]
    patch=image[max(0,y-3):min(height,y+h+3),max(0,x-3):min(width,x+w+12),::-1]
    if not patch.size:return None
    # Keep the existing bright-white numeric anchor; lower thresholds are only
    # evaluated INSIDE it, so gold captions and gray scene edges cannot join in.
    ys,xs=np.where(white_ink(patch,205))
    if not len(xs):return None
    numbers=patch[ys.min():ys.max()+1,xs.min():xs.max()+1]
    readings=[]
    for threshold in (190,200):
        candidates=white_digit_candidates(white_ink(numbers,threshold),templates)
        if not candidates:return None
        cost,text,minimum=candidates[0]
        if cost>.35 or minimum<.55 or text.startswith('0'):return None
        if len(candidates)>1 and candidates[1][0]-cost<.035:return None
        readings.append(int(text))
    return readings[0] if readings[0]==readings[1] else None


def read_opponent_power(image,item,ocr,normalize):
    """Legacy caption API for replaying old reports; production uses ranked_numbers."""
    x,y,w,h=item['box'];height,width=image.shape[:2]
    region=image[max(0,y-3):min(height,y+h+3),max(0,x-3):min(width,x+w+3)].copy()
    values=[];numeric_seen=False
    def read_number_views():
        nonlocal numeric_seen
        # The detector can split the caption and the final digit differently
        # at each scale. Locate white numeric ink, then keep the ORIGINAL
        # antialiased pixels with a small margin (binary serif masks lose 2).
        padded=image[max(0,y-3):min(height,y+h+3),max(0,x-3):min(width,x+w+12)].copy()
        rgb=padded[:,:,::-1].astype('float32')
        white=(np.min(rgb,axis=2)>205)&((np.max(rgb,axis=2)-np.min(rgb,axis=2))<35)
        ys,xs=np.where(white)
        if not len(xs):return None
        numbers=padded[max(0,ys.min()-2):min(padded.shape[0],ys.max()+3),
                       max(0,xs.min()-2):min(padded.shape[1],xs.max()+3)]
        def views(horizontal=1):
            readings=[];numeric_seen=False
            for scale in (3,4):
                source=Image.fromarray(numbers).resize((round(numbers.shape[1]*scale*horizontal),numbers.shape[0]*scale))
                words=ocr.read(np.array(source),only_rec=True)
                for word in words:
                    text=normalize(word['text'])
                    numeric_seen|=bool(re.fullmatch(r'\d+',text))
                    if len(words)==1 and word.get('score',0)>=.8 and re.fullmatch(r'\d{4,9}',text):
                        readings.append(int(text))
            value=readings[0] if len(readings)==2 and readings[0]==readings[1] else None
            return value,numeric_seen
        value,seen=views()
        numeric_seen|=seen
        if value is not None or seen:return value
        # Touching narrow serif digits can become '%' in both normal views.
        # A modest horizontal expansion separates their shapes without guessing
        # characters. Both scales still must agree; never override numeric conflict.
        value,seen=views(1.25)
        numeric_seen|=seen
        return value
    def add(items,only_number=False):
        nonlocal numeric_seen
        for result in items:
            text=normalize(result['text'])
            match=re.fullmatch(r'(\d{4,9})',text) if only_number else re.search(r'(?:战力|战斗力):?(\d{4,9})$',text)
            numeric_seen|=bool(re.fullmatch(r'\d+',text) or re.search(r'(?:战力|战斗力):?\d+$',text))
            if match and result.get('score',1)>=.8:values.append(int(match.group(1)))
    add([item])
    for scale in (2,3):
        source=Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale))
        add(ocr.read(np.array(source)))
    candidates=set(values)
    if len(candidates)>1:
        longest=max(candidates,key=lambda value:len(str(value)))
        if all(str(longest).startswith(str(value)) for value in candidates):
            # A missing last digit can agree in full-screen and 2x OCR.
            # When another view sees a longer suffix, require BOTH larger
            # renderings to confirm it; do not choose the shorter majority.
            confirmed=[]
            for scale in (4,5):
                start=len(values)
                source=Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale))
                add(ocr.read(np.array(source)))
                sample=values[start:]
                if len(sample)==1:confirmed.append(sample[0])
            if confirmed!=[longest,longest]:
                # Some full-screen boxes stop before the final serif digit.
                # Retry only the disputed suffix with a wider right margin;
                # both new renderings must still prove the same longest value.
                padded=image[max(0,y-3):min(height,y+h+3),max(0,x-3):min(width,x+w+12)].copy()
                confirmed=[]
                for scale in (4,5):
                    start=len(values)
                    source=Image.fromarray(padded).resize((padded.shape[1]*scale,padded.shape[0]*scale))
                    add(ocr.read(np.array(source)))
                    sample=values[start:]
                    if len(sample)==1:confirmed.append(sample[0])
                if confirmed!=[longest,longest] and read_number_views()!=longest:
                    raise RuntimeError('对手战力末位复核不一致，停止')
            return longest
    agreed=[value for value,count in Counter(values).items() if count>=2]
    if len(agreed)==1:
        if len(candidates)>1:
            # Caption scales can repeat the same middle-digit omission. Let
            # independent numeric-only double reads prove ANY existing valid
            # candidate, rather than requiring the caption majority to win.
            confirmed=read_number_views()
            if confirmed not in candidates:
                raise RuntimeError('对手战力局部识别不一致，停止')
            return confirmed
        return agreed[0]
    # Alphabetic captions (e.g. 1066s9) yield no numeric candidate at all.
    # Use the SAME two original-pixel numeric views here too, before the
    # lossy binary mask. Existing valid candidates must still agree.
    numeric=read_number_views()
    if numeric is not None and (not values or numeric in values):return numeric
    # Retain the legacy masked view only when it does not contradict the
    # independently confirmed original-pixel reading.
    rgb=region[:,:,::-1].astype('float32')
    white=(np.min(rgb,axis=2)>205)&((np.max(rgb,axis=2)-np.min(rgb,axis=2))<35)
    ys,xs=np.where(white)
    if len(xs):
        digits=white[ys.min():ys.max()+1,xs.min():xs.max()+1]
        add(ocr.read(glyph_image(digits,3),only_rec=True),only_number=True)
    # No reliable numeric OCR anywhere: independent shape evidence may recover
    # the value. Never overwrite a numeric candidate, conflict or low-score number.
    if not values and not numeric_seen:
        template_value=read_white_power(image,item)
        if template_value is not None:return template_value
    agreed=[value for value,count in Counter(values).items() if count>=2]
    if len(agreed)!=1:raise RuntimeError('对手战力局部识别不一致，停止')
    if (len(set(values))>1 or numeric is not None) and numeric!=agreed[0]:
        raise RuntimeError('对手战力局部识别不一致，停止')
    return agreed[0]
