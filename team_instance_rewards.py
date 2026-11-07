"""Read the three reward numbers relative to the team panel footer label."""
import re
from PIL import Image
from adapters.local_ocr import LocalOCR
import numpy as np

def single_week_crop(image,x,y):
    region=image[y:y+34,x+127:x+164]
    blue,green,red=(region[:,:,i].astype('int16') for i in range(3))
    orange=(red>150)&(green>60)&(green<210)&(blue<90)&(red>green+40)
    rows,columns=np.where(orange)
    # Inspect the whole two-digit region first; never clip a second digit.
    if len(columns)<6 or columns.max()-columns.min()>14 or columns.max()>=26:return None
    return image[y+2:y+32,x+129:x+153].copy()

def read_number(ocr,crop,maximum):
    values=[]
    for scale in (2,3):
        image=np.array(Image.fromarray(crop).resize((crop.shape[1]*scale,crop.shape[0]*scale),Image.Resampling.BICUBIC))
        items=ocr.read(image,only_rec=True)
        if len(items)!=1 or items[0].get('score',0)<.9:return None
        text=items[0]['text'].strip()
        if not re.fullmatch(r'0|[1-9][0-9]?',text):return None
        value=int(text)
        if value>maximum:return None
        values.append(value)
    return values[0] if values[0]==values[1] else None

def read_frame(task):
    from team_instance_challenge import Challenge
    if not Challenge(task).panel():return None
    anchor=task.template(['reward_label'],(0,0,1920,1015))
    if not anchor:return None
    x,y,w,h=anchor['box']
    values=[]
    for left,right,maximum in ((129,160,20),(297,323,5),(544,569,5)):
        crop=task.f.image[y+3:y+31,x+left:x+right].copy()
        value=read_number(task.f.ocr,crop,maximum)
        if value is None and maximum==20:
            # The fixed narrow padding depresses confidence for the real "15"
            # glyph pair. Retry the same number with wider surrounding pixels;
            # keep the confidence, range and two-scale agreement requirements.
            crop=task.f.image[y:y+34,x+127:x+164].copy()
            value=read_number(task.f.ocr,crop,maximum)
        if value is None and maximum==20:
            crop=single_week_crop(task.f.image,x,y)
            if crop is not None:value=read_number(task.f.ocr,crop,maximum)
        if value is None:return None
        values.append(value)
    return tuple(values)

def read_rewards(task):
    task.f.log('组队副本：等待底部本周、本日、友情奖励次数稳定识别')
    last=None
    def read():
        nonlocal last
        value=read_frame(task)
        stable=value is not None and value==last
        last=value
        return value if stable else None
    try:return task.wait(read)
    except TimeoutError as exc:
        raise TimeoutError('组队副本奖励次数读取超时；未获得连续两帧可信数值，未进入挑战') from exc
