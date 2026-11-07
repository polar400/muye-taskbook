"""Wanted task: one automatic run, verified zero or user-approved absent entry."""
import re
import time
from PIL import Image
import numpy as np


class WantedTask:
    def __init__(self,flow):
        self.f=flow
        self.sent=set()
        self.clock=time.monotonic
        self.sleep=time.sleep
        self.paused=0
        self.original_checkpoint=flow.checkpoint
        self.absent_frames=0
        self.idle_since=None;self.idle_reference=None;self.idle_frames=0

    def checkpoint(self):
        start=self.clock()
        try:self.original_checkpoint()
        finally:self.paused+=self.clock()-start

    def now(self):return self.clock()-self.paused

    def matches(self,name,roi):
        h,w=self.f.image.shape[:2]
        left,top,right,bottom=roi
        x,y=int(w*left),int(h*top)
        region=self.f.image[y:int(h*bottom),x:int(w*right)].copy()
        return [dict(m,box=[m['box'][0]+x,m['box'][1]+y,*m['box'][2:]])
                for m in self.f.ocr.match(region,name,threshold=.9)]

    def button(self,name,roi):
        matches=self.matches(name,roi)
        if len(matches)>1:raise RuntimeError('通缉任务按钮不唯一：'+name)
        return matches[0] if matches else None

    def central_words(self):
        h,w=self.f.image.shape[:2]
        return [m for m in self.f.items if w*.25<m['box'][0]<w*.75
                and h*.2<m['box'][1]<h*.8]

    def confirmation(self):
        h,w=self.f.image.shape[:2]
        words=[m for m in self.central_words() if m['box'][1]>h*.3]
        region=self.f.image[int(h*.3):int(h*.8),int(w*.25):int(w*.75)].copy()
        # Read the actual dialog, not the automatic-completion button behind it.
        local=self.f.ocr.read(region)
        local=[dict(m,box=[m['box'][0]+int(w*.25),m['box'][1]+int(h*.3),*m['box'][2:]]) for m in local]
        words=words+local
        text=' '.join(m['text'] for m in words)
        if re.search(r'元宝|点券|购买|支付|花费|消耗',text):
            raise RuntimeError('通缉自动完成出现消耗提示，停止并保留画面')
        # The real game asks about solo EXP loss, without saying "自动完成".
        # Match its local meaning, so unrelated/background text cannot qualify it.
        local_text=re.sub(r'\s+','',''.join(m['text'] for m in local))
        solo_warning=all(re.search(pattern,local_text) for pattern in (
            r'单人状态',r'通缉任务',r'无法获得双倍经验',r'是否继续'))
        if not re.search(r'自动\s*完成',text) and not solo_warning:return None
        buttons=[]
        for m in words:
            if re.fullmatch(r'是',m['text'].strip()) and m.get('score',1)>=.8:
                if not any(abs(m['box'][0]-b['box'][0])<25 and abs(m['box'][1]-b['box'][1])<25 for b in buttons):buttons.append(m)
        if len(buttons)>1:raise RuntimeError('通缉自动完成确认“是”不唯一')
        if solo_warning and buttons:
            negatives=[m for m in local if re.fullmatch(r'否',m['text'].strip()) and m.get('score',1)>=.8]
            if len(negatives)!=1:return None
            yes,no=buttons[0]['box'],negatives[0]['box']
            if no[0]<=yes[0]+yes[2] or abs(no[1]-yes[1])>max(yes[3],no[3]):return None
        return buttons[0] if buttons else None

    def panel_count(self):
        if any(re.fullmatch(r'是|否|确定|确认',m['text'].strip()) for m in self.central_words()):return None
        if not self.button('wanted_title',(.32,.06,.68,.22)):return None
        anchor=self.button('wanted_counter',(.35,.19,.62,.32))
        if anchor is None:return None
        x,y,w,h=anchor['box']
        # Crop relative to the verified caption; never a fixed input position.
        region=self.f.image[max(0,y-20):y+48,x+w+15:x+w+86].copy()
        if region.size==0:return None
        values=[]
        for scale in (2,3):
            resized=np.array(Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale)))
            words=self.f.ocr.read(resized,only_rec=True)
            if len(words)==1 and words[0].get('score',0)>=.9 and re.fullmatch(r'[0-5]',words[0]['text'].strip()):
                values.append(int(words[0]['text'].strip()))
        if len(set(values))>1:raise RuntimeError('通缉任务剩余次数识别冲突')
        return values[0] if len(values)==2 else None

    def selected_row(self):
        # The selected right-hand detail has decorative lettering which the
        # OCR detector can omit entirely. Verify its actual art in the same ROI.
        if self.button('wanted_detail_title',(.6,.12,.82,.22)) is not None:return True
        h,w=self.f.image.shape[:2]
        words=[m for m in self.f.items if m['box'][0]>w*.6 and h*.12<m['box'][1]<h*.35]
        if any(re.fullmatch(r'通缉任务',m['text'].strip()) and m.get('score',1)>=.8 for m in words):return True
        region=self.f.image[int(h*.12):int(h*.25),int(w*.6):int(w*.82)].copy()
        for scale in (1,2):
            image=region if scale==1 else np.array(Image.fromarray(region).resize((region.shape[1]*2,region.shape[0]*2)))
            if any(re.fullmatch(r'通缉任务',m['text'].strip()) and m.get('score',1)>=.8 for m in self.f.ocr.read(image)):return True
        return False

    def completed_activity_close(self):
        # User-approved terminal page: selected Daily tab, intact adjacent
        # Strong/Quiz rows in the vacated list slot, and no Wanted entry.
        if any(re.fullmatch(r'是|否|确定|确认',m['text'].strip()) for m in self.central_words()):return None
        if self.button('wanted_daily_selected',(.12,.02,.4,.16)) is None:return None
        if self.button('wanted_daily_completed_rows',(.14,.3,.3,.49)) is None:return None
        if self.button('wanted_row',(.14,.16,.3,.74)) is not None:return None
        h,w=self.f.image.shape[:2]
        if any('通缉' in m['text'] and w*.14<m['box'][0]<w*.3 and h*.16<m['box'][1]<h*.74 for m in self.f.items):return None
        if self.button('wanted_detail_title',(.6,.12,.82,.22)) is not None:return None
        return self.button('close',(.8,0,.9,.13))

    def activity_completed(self):
        close=self.completed_activity_close()
        self.absent_frames=self.absent_frames+1 if close else 0
        return self.absent_frames>=2

    def home_visible(self):
        return True if (self.button('wanted_title',(.32,.06,.68,.22)) is None
                        and self.button('wanted_daily_selected',(.12,.02,.4,.16)) is None
                        and self.button('close',(.8,0,.9,.13)) is None
                        and self.f.ocr.match(self.f.image,'entry_survival')
                        and self.f.ocr.match(self.f.image,'entry_ranked')) else None

    def autopath_visible(self):
        # Decorative gold lettering is often omitted or read as only 动寻.
        # Presence is enough to reset the timer; this is not a click target.
        roi=(.36,.08,.6,.2)
        if self.matches('wanted_autopath',roi):return True
        h,w=self.f.image.shape[:2]
        words=[m['text'] for m in self.f.items if m.get('score',0)>=.8
               and w*roi[0]<m['box'][0]<w*roi[2] and h*roi[1]<m['box'][1]<h*roi[3]]
        return bool(re.search(r'自动寻路',re.sub(r'\s+','',''.join(words))))

    def idle_home_completed(self):
        # This terminal is authorized only AFTER this run sent automatic
        # completion and its confirmation. Initial home is never completion.
        h,w=self.f.image.shape[:2]
        quests=[m for m in self.f.items if m['box'][0]>w*.8 and h*.4<m['box'][1]<h*.9]
        text=' '.join(m['text'] for m in quests)
        panel=any('任务列表' in m['text'] and m.get('score',1)>=.8 for m in quests)
        panel=panel or sum(bool(re.search(r'主线|支线|通缉',m['text'])) and m.get('score',1)>=.8 for m in quests)>=2
        eligible=('确认免费自动完成（是）' in self.sent and not self.autopath_visible()
                  and self.home_visible() and panel
                  and not re.search(r'通缉|自动',text)
                  and not any(re.fullmatch(r'是|否|确定|确认',m['text'].strip()) for m in self.central_words()))
        if not eligible:
            self.idle_since=None;self.idle_reference=None;self.idle_frames=0;return False
        scene=self.f.image[int(h*.32):int(h*.72),int(w*.32):int(w*.66),::-1]
        fingerprint=np.array(Image.fromarray(scene).convert('L').resize((32,24)),dtype='int16')
        if self.idle_reference is None or np.abs(fingerprint-self.idle_reference).mean()>1.5:
            self.idle_reference=fingerprint;self.idle_since=self.now();self.idle_frames=1;return False
        self.idle_frames+=1
        return self.idle_frames>=3 and self.now()-self.idle_since>=10

    def complete_from_activity(self):
        self.click('关闭已完成日常活动',self.completed_activity_close)
        self.wait('确认返回木叶村',self.home_visible)
        self.f.log('通缉任务：日常活动列表已无通缉条目，按用户规则确认已完成并返回主页，继续下一任务')

    def wait(self,label,reader,seconds=30):
        self.f.emit('node','通缉任务 · '+label,id='wanted',node=label,status='running')
        deadline=self.now()+seconds
        while True:
            self.f.observe()
            if self.now()>deadline:raise TimeoutError('通缉任务等待超时：'+label+'；未重复发送点击，已保留最后画面')
            result=reader()
            if result is not None and result is not False:return result
            self.checkpoint();self.sleep(.2)

    def click(self,stage,reader):
        if stage in self.sent:raise RuntimeError('通缉任务输入已发送，拒绝重复：'+stage)
        target=self.wait(stage,reader)
        self.sent.add(stage)  # An uncertain send must never be replayed.
        self.f.log('通缉任务：'+stage+'，发送一次后台点击')
        self.f.click_item(target)

    def run(self):
        self.f.checkpoint=self.checkpoint
        try:return self.execute()
        finally:self.f.checkpoint=self.original_checkpoint

    def execute(self):
        self.f.observe()
        initial=self.panel_count()
        if initial is None and self.button('wanted_title',(.32,.06,.68,.22)) is not None:
            initial=self.wait('复核已有通缉面板次数',self.panel_count)
        if initial is None:
            daily=lambda:self.button('wanted_daily',(.12,.02,.4,.16))
            if daily() is None:
                self.f.home()
                self.click('苦无活动入口',lambda:self.button('wanted_kunai',(0,.14,.1,.3)))
            self.click('日常活动',daily)
            def row_or_completed():
                if self.button('wanted_row',(.14,.16,.3,.74)) is not None:
                    self.absent_frames=0;return 'row'
                return 'completed' if self.activity_completed() else None
            if self.wait('确认通缉条目或已完成活动列表',row_or_completed)=='completed':
                return self.complete_from_activity()
            self.click('通缉任务条目',lambda:self.button('wanted_row',(.14,.16,.3,.74)))
            def participate():
                return self.button('wanted_participate',(.6,.6,.8,.78)) if self.selected_row() else None
            self.click('参与通缉任务',participate)
            initial=self.wait('等待通缉任务面板',self.panel_count)
        if initial:
            def auto():
                return self.button('wanted_auto',(.6,.2,.75,.32)) if self.panel_count() is not None else None
            self.click('自动完成',auto)
            self.click('确认免费自动完成（是）',self.confirmation)
            self.f.log('通缉任务：已确认自动完成，由游戏自动接取后续任务，等待完成并返回主界面')
        last=initial;zero_frames=0
        def finished():
            nonlocal last,zero_frames
            if self.activity_completed():return 'activity'
            if self.idle_home_completed():return 'home'
            count=self.panel_count()
            if count is None:zero_frames=0;return None
            if count>last:raise RuntimeError('通缉任务剩余次数异常增加，停止')
            last=count
            zero_frames=zero_frames+1 if count==0 else 0
            return True if zero_frames>=2 else None
        terminal=self.wait('等待全部通缉任务完成（今日余下次数0、活动条目消失或主界面稳定）',finished,1800)
        if terminal=='activity':return self.complete_from_activity()
        if terminal=='home':
            self.f.log('通缉任务：主页连续10秒未出现自动寻路中且状态稳定，继续下一任务');return
        self.click('关闭已完成通缉面板',lambda:self.button('wanted_close',(.75,.12,.86,.24)) if self.panel_count()==0 else None)
        self.wait('确认返回木叶村',self.home_visible)
        self.f.log('通缉任务：已确认今日余下次数0并返回主页')


def run_wanted(flow):return WantedTask(flow).run()
