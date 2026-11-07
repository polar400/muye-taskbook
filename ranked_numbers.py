"""Ranked numeric-region readers and one evidence arbiter. No game input."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image
import numpy as np


def ink(rgb,threshold):
    rgb=rgb.astype('int16')
    return (rgb.min(axis=2)>threshold)&(np.ptp(rgb,axis=2)<35)


def opponent_region(image,button):
    """Find numeric ink above a verified challenge text/button, not a caption."""
    if image.shape[:2]!=(1015,1920):raise RuntimeError('排位数字画面尺寸未校准')
    x,y,w,h=button['box'];cx=round(x+w/2)
    left,top,right,bottom=cx-18,y-40,cx+100,y-7
    if not (0<=left<right<=1920 and 550<top<bottom<=1015):raise RuntimeError('排位数字区域超出挑战面板')
    rgb=image[top:bottom,left:right,::-1]
    ys,xs=np.where(ink(rgb,205))
    if not len(xs):raise RuntimeError('排位对手数字区域没有完整白色字形')
    box=[left+int(xs.min()),top+int(ys.min()),left+int(xs.max())+1,top+int(ys.max())+1]
    a,b,r,d=box
    if not 12<=d-b<=14 or not 20<=r-a<=100:
        raise RuntimeError('排位对手数字区域字形或边界异常')
    # Bright pixels locate the word, but are not its complete outline. A
    # narrow 4 can have only its stem above 205, losing the diagonal when
    # cropped here. Recover the nearby 170-level ink from original pixels,
    # bounded to two horizontal/one vertical pixels inside the numeric ROI.
    al,bt,rr,db=max(left,a-2),max(top,b-1),min(right,r+2),min(bottom,d+1)
    outline=image[bt:db,al:rr,::-1]
    oy,ox=np.where(ink(outline,170))
    box=[al+int(ox.min()),bt+int(oy.min()),al+int(ox.max())+1,bt+int(oy.max())+1]
    a,b,r,d=box
    patch=image[b:d,a:r,::-1].copy()
    if not 12<=d-b<=14 or not 20<=r-a<=100 or ink(patch,190).mean()>.8:
        raise RuntimeError('排位对手数字区域字形或边界异常')
    return patch,box


@lru_cache(maxsize=1)
def digit_bank():
    """Load only source pixel references whose source and crop hashes agree."""
    manifest=json.loads((ROOT/'resources/local/ranked_numbers/bank.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=1:raise RuntimeError('排位数字字形库版本无效')
    bank=[]
    for source in manifest['sources']:
        path=ROOT/source['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            raise RuntimeError('排位数字字形来源校验失败')
        with Image.open(path) as im:
            for ref in manifest['templates']:
                if ref['sourceId']!=source['id']:continue
                rgb=np.array(im.crop(ref['box']).convert('RGB'))
                if hashlib.sha256(rgb.tobytes()).hexdigest()!=ref['pixelSha256']:
                    raise RuntimeError('排位数字裁片校验失败')
                bank.append((ref['digit'],rgb))
    if {d for d,_ in bank}!=set('0123456789'):raise RuntimeError('排位数字字形库不完整')
    return tuple(bank)


@lru_cache(maxsize=8)
def kernels(threshold,height):
    """Keep native masks and render bounded antialiased size variants."""
    grouped={}
    for digit,rgb in digit_bank():
        mask=ink(rgb,threshold);ys,xs=np.where(mask)
        if not len(xs):continue
        mask=mask[:,xs.min():xs.max()+1]
        expected=mask.shape[1]*height/mask.shape[0]
        for width in range(max(3,round(expected)-1),round(expected)+2):
            resized=np.array(Image.fromarray(mask).resize((width,height),Image.Resampling.NEAREST))
            # A cut between touching glyphs can include one column of the
            # neighbour's antialiased ink. Represent that boundary explicitly
            # without stretching the glyph or discarding any of its pixels.
            # Extra ink still counts against IoU; all acceptance gates remain.
            for left,right in ((0,0),(1,0),(0,1)):
                padded=np.pad(resized,((0,0),(left,right)))
                grouped.setdefault(width+left+right,[]).append((int(digit),padded))
        # Resampling binary masks loses faint diagonal strokes (notably 4).
        # Resize the verified source pixels before thresholding as well. The
        # bright-ink ROI can differ from the line height by one pixel, so align
        # only the adjacent heights; do not expand the search arbitrarily.
        original=Image.fromarray(rgb[:,xs.min():xs.max()+1])
        for glyph_height in (height-1,height,height+1):
            expected=original.width*glyph_height/original.height
            for width in range(max(3,round(expected)-1),round(expected)+2):
                mask=ink(np.array(original.resize((width,glyph_height),Image.Resampling.BICUBIC)),threshold)
                for offset in range(abs(height-glyph_height)+1):
                    aligned=(mask[offset:offset+height] if glyph_height>height else
                             np.pad(mask,((offset,height-glyph_height-offset),(0,0))))
                    for left,right in ((0,0),(1,0),(0,1)):
                        padded=np.pad(aligned,((0,0),(left,right)))
                        grouped.setdefault(width+left+right,[]).append((int(digit),padded))
    # Multiple source variants can render the same mask. Score those pixels
    # once to bound the enlarged matching arrays without changing candidates.
    result={}
    for width,values in grouped.items():
        unique=list({(digit,mask.tobytes()):(digit,mask) for digit,mask in values}.values())
        result[width]=(np.array([d for d,_ in unique]),np.stack([m for _,m in unique]))
    return result


def shape_candidates(rgb,threshold):
    """Match alternative cuts through touching digits, with bounded whole-word DP."""
    mask=ink(rgb,threshold);height,width=mask.shape
    if not 12<=height<=14 or not 20<=width<=100 or not mask.any() or mask.mean()>.8:return []
    scores={}
    for w,(labels,templates) in kernels(threshold,height).items():
        if w>width:continue
        windows=np.lib.stride_tricks.sliding_window_view(mask,(height,w))[0]
        intersection=(windows[:,None]&templates[None]).sum(axis=(2,3))
        union=windows.sum(axis=(1,2))[:,None]+templates.sum(axis=(1,2))[None]-intersection
        overlap=intersection/np.maximum(1,union)
        scores[w]=np.stack([overlap[:,labels==d].max(axis=1) if np.any(labels==d)
                            else np.zeros(len(windows)) for d in range(10)],axis=1)
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
                # The font is fixed-pitch; a narrow 1 legitimately leaves up
                # to six blank columns before the next glyph's ink.
                if end-x<=6:keep((end,length),previous)
                continue
            for w,overlaps in scores.items():
                if x+w>width:continue
                for digit,score in enumerate(overlaps[x]):
                    if score<.65:continue
                    keep((x+w,length+1),[(cost+1-score,text+str(digit),min(minimum,float(score)))
                                         for cost,text,minimum in previous])
    return sorted((float(cost),text,minimum) for length in range(4,10)
                  for cost,text,minimum in paths.get((width,length),[]))


def shape_reading(rgb):
    # Compare the antialiased outline and the brighter core. A 200-only core
    # can erase the diagonal of a calibrated 12px 4 and turn it into a 1.
    # Both views must still meet the same IoU/lead gates and agree in value.
    def read_view(threshold):
        candidates=shape_candidates(rgb,threshold)
        view={'threshold':threshold,'candidates':[{'cost':c,'text':t,'minimumIoU':m} for c,t,m in candidates[:2]]}
        if candidates:
            cost,text,minimum=candidates[0]
            view.update(value=int(text),meanIoU=1-cost/len(text),minimumIoU=minimum,
                        lead=candidates[1][0]-cost if len(candidates)>1 else 1.)
        return view
    def usable(view):
        return ('value' in view and view['meanIoU']>=.8 and view['minimumIoU']>=.65
                and not view['candidates'][0]['text'].startswith('0'))
    views=[read_view(threshold) for threshold in (170,190)]
    qualified=[v for v in views if usable(v) and v['lead']>=.08]
    value=qualified[0]['value'] if len(qualified)==2 and qualified[0]['value']==qualified[1]['value'] else None
    # Resolve only an agreeing, otherwise good pair with one weak runner-up
    # margin. Keep both original observations, including the weak margin.
    # A midpoint must pass the unchanged gates and corroborating numeric OCR
    # is mandatory. Disagreement, ties, missing/poor ink never take this path.
    if (value is None and len(qualified)==1 and all(usable(v) and v['lead']>0 for v in views)
            and views[0]['value']==views[1]['value']):
        middle=read_view(180);views.append(middle)
        if usable(middle) and middle['lead']>=.08 and middle['value']==views[0]['value']:
            return {'value':middle['value'],'views':views,'midpointConfirmed':True,'requiredOCRReadings':2}
    return {'value':value,'views':views}


class NumberRecognitionError(RuntimeError):
    def __init__(self,message,evidence,rgb=None):
        evidence.setdefault('reason',str(message))
        super().__init__(message);self.evidence=evidence;self.rgb=rgb


def arbitrate(observations,shape):
    valid=[o['value'] for o in observations if o.get('value') is not None]
    values=set(valid);visual=shape.get('value')
    if len(values)>1:return None,'数字OCR纯数字读数冲突'
    if visual is not None and values and visual not in values:return None,'数字OCR与字形证据冲突'
    if visual is not None and len(valid)<shape.get('requiredOCRReadings',0):
        return None,'灰度边界复核需要两路有效数字OCR一致'
    if visual is not None and values:return visual,'数字OCR与字形一致'
    if visual is not None:
        if min(v['meanIoU'] for v in shape['views'])>=.9 and min(v['minimumIoU'] for v in shape['views'])>=.75:
            return visual,'两种字形掩码高质量一致，OCR未读出纯数字'
    return None,'数字证据不足或字形候选不唯一'


def read_opponent(image,button,ocr):
    evidence={'buttonBox':list(button['box']),'observations':[],'value':None}
    try:rgb,box=opponent_region(image,button)
    except RuntimeError as error:raise NumberRecognitionError(str(error),evidence) from error
    evidence['numericBox']=box
    try:shape=shape_reading(rgb)
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        raise NumberRecognitionError('排位数字字形库不可用：'+str(error),evidence,rgb) from error
    evidence['shape']=shape
    # Every path reads the same isolated original pixels. No caption parsing,
    # binary OCR, character substitution, or path-dependent early majority.
    x,y,r,b=box
    padded=image[max(0,y-2):min(image.shape[0],b+2),max(0,x-2):min(image.shape[1],r+2),::-1].copy()
    for horizontal in (1.,1.25):
        for scale in (3,4):
            view=Image.fromarray(padded).resize((round(padded.shape[1]*scale*horizontal),padded.shape[0]*scale))
            words=ocr.read(np.array(view)[:,:,::-1].copy(),only_rec=True)
            observation={'horizontal':horizontal,'scale':scale,'words':words,'value':None}
            if len(words)==1 and words[0].get('score',0)>=.8 and re.fullmatch(r'[1-9][0-9]{3,8}',words[0]['text'].strip()):
                observation['value']=int(words[0]['text'].strip())
            evidence['observations'].append(observation)
        value,reason=arbitrate(evidence['observations'],shape)
        # Never spend more OCR views to erase an established numeric conflict.
        if value is not None or '冲突' in reason:break
    evidence.update(value=value,reason=reason)
    if value is None:raise NumberRecognitionError('对手战力无法可靠识别：'+reason,evidence,rgb)
    return evidence


def save_evidence(root,prefix,evidence,crops):
    """Save the final failed observation once, preserving any earlier evidence."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    for serial in range(1000):
        folder=root/(prefix+'-numbers'+('' if serial==0 else '-'+str(serial)))
        try:folder.mkdir()
        except FileExistsError:continue
        break
    else:raise RuntimeError('排位数字诊断目录无法唯一创建')
    data=json.loads(json.dumps(evidence))
    for index,(record,rgb) in enumerate(zip(data['opponents'],crops),1):
        if rgb is None:continue
        name=f'opponent-{index}.png';Image.fromarray(rgb).save(folder/name)
        record['crop']=name;record['cropSha256']=hashlib.sha256((folder/name).read_bytes()).hexdigest()
    path=folder/'evidence.json'
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return path
