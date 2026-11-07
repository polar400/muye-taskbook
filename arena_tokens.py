"""Read arena protection tokens and enforce the opt-in daily-mode policy."""
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
import numpy as np
from PIL import Image

DAILY_MODE='日常模式'
DAILY_LABEL='日常模式（战令用完转休闲）'


class TokenReader:
    def __init__(self,ocr,matcher):
        self.ocr=ocr;self.matcher=matcher;self.evidence=None

    def read(self,image):
        labels=[m for m in self.matcher.match(image,'war_label') if m['score']>=.95]
        self.evidence=dict(labels=labels,views=[])
        if len(labels)!=1:return None
        x,y,w,h=labels[0]['box'];left=x+w+7;right=left+18;top=y+3;bottom=y+h-2
        if right>image.shape[1] or y+h>image.shape[0]:return None
        crop=image[top:bottom,left:right].copy()
        self.evidence['digitBox']=[left,top,right-left,bottom-top]
        values=[]
        for scale,invert in ((3,False),(4,False),(4,True)):
            view=np.array(Image.fromarray(crop).resize((crop.shape[1]*scale,crop.shape[0]*scale)))
            if invert:view=255-view
            words=self.ocr.read(view,only_rec=True)
            self.evidence['views'].append(dict(scale=scale,invert=invert,words=words))
            if len(words)!=1 or words[0].get('score',0)<.95:return None
            value=re.sub(r'\s+','',words[0]['text'])
            if not re.fullmatch(r'[0-3]',value):return None
            values.append(int(value))
        return values[0] if len(set(values))==1 else None


class TokenPolicy:
    def __init__(self,clock):
        self.clock=clock;self.deadline=clock()+3600;self.casual=False;self.remaining=None

    def check_time(self):
        if not self.casual and self.clock()>=self.deadline:
            raise TimeoutError(f'日常模式耗令阶段已到60分钟，停止；最后确认战令{self.remaining}，尚未确认用完')

    def observe(self,value):
        if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=3:
            raise RuntimeError('战令数无法可靠读取，不开始段位匹配')
        self.remaining=value
        if value==0:self.casual=True

    def verify_result(self,before,result,after):
        if result not in ('victory','defeat'):raise RuntimeError('战令核对缺少明确胜败')
        expected=before-1 if result=='defeat' else before
        if after!=expected:raise RuntimeError(f'段位战令消耗不符：{before}→{after}，应为{expected}；停止')
        self.observe(after)

    def mode(self):return '休闲战斗' if self.casual else '段位战斗'
