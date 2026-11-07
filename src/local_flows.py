"""Explicit local task states. Unrecognized states fail without foreground fallback."""
import re
import random
import time
from pathlib import Path
from PIL import Image
from survival_plan import survival_plan
from ranked_vision import read_red_power, read_ranked_remaining
from ranked_numbers import read_opponent, NumberRecognitionError
from ranked_policy import ranked_options
from wanted_task import run_wanted

def normalized(text):return re.sub(r'\s+','',text).replace('：',':').replace('；',':').replace(';',':').replace('／','/')

def remaining(items,pattern):
    values=[]
    for item in items:
        match=re.search(pattern,normalized(item['text']))
        if match:values.append(int(match.group(1)))
    if len(set(values))!=1:raise RuntimeError('无法可靠读取剩余次数')
    return values[0]

def select_opponent(own,opponents,tolerance):
    if own<=0 or not opponents:raise RuntimeError('无法读取我方和对手战力')
    nearest=min(opponents,key=lambda x:abs(x['power']-own))
    return nearest if abs(nearest['power']-own)/own<=tolerance/100 else random.choice(opponents)

class LocalFlows:
    def wanted(self):return run_wanted(self)

    def __init__(self,window,ocr,cfg,checkpoint,emit):
        self.window=window;self.ocr=ocr;self.cfg=cfg;self.checkpoint=checkpoint;self.emit=emit
        self.items=[];self.image=None

    def log(self,text):self.emit('log',text)
    def capture_ready(self):
        deadline=None
        while True:
            self.checkpoint()
            try:return self.window.capture()
            except RuntimeError as error:
                if str(error)!='游戏截图为黑屏或未加载':raise
                if deadline is None:
                    deadline=time.monotonic()+3
                    self.log('游戏切换时截图暂未加载，短暂重试；不发送点击')
                if time.monotonic()>=deadline:raise
                time.sleep(.15)
    def observe(self):
        self.image=self.capture_ready();self.items=self.ocr.read(self.image)
        self.window.save(self.image,Path(__file__).resolve().parents[1]/'verification/background-latest.png')
        return self.items
    def hits(self,pattern):return [x for x in self.items if re.search(pattern,normalized(x['text']))]
    def click_item(self,item,delay=.6):
        self.checkpoint();x,y,w,h=item['box'];self.window.click(x+w//2,y+h//2)
        if delay:time.sleep(delay)
    def click_text(self,pattern,delay=.6):
        matches=self.hits(pattern)
        if len(matches)!=1:raise RuntimeError('无法唯一定位按钮：'+pattern)
        self.click_item(matches[0],delay=delay)
    def wait(self,predicate,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.observe()
            if predicate():return
            for _ in range(5):self.checkpoint();time.sleep(.2)
        raise RuntimeError('等待界面状态超时，已保存最后截图')
    def wait_text(self,pattern,seconds=30):self.wait(lambda:bool(self.hits(pattern)),seconds)
    def confirm(self,guard=None):
        self.observe()
        if self.hits(r'购买|支付|花费|消耗.*(?:元宝|点券)'):raise RuntimeError('遇到付费提示，停止操作')
        if guard is not None and not guard():raise RuntimeError('弹窗状态已变化，停止确认')
        buttons=self.hits(r'^(?:确定|确认|是)$')
        if len(buttons)>1:raise RuntimeError('弹窗确认按钮不唯一，停止')
        if len(buttons)!=1:
            h,w=self.image.shape[:2]
            for left,top,right,bottom in [(.35,.4,.65,.65),(.3,.3,.7,.72)]:
                x=int(w*left);y=int(h*top)
                dialog=self.image[y:int(h*bottom),x:int(w*right)].copy()
                words=self.ocr.read(dialog)
                if any(re.search(r'购买|支付|花费|消耗.*(?:元宝|点券)',normalized(m['text'])) for m in words):raise RuntimeError('遇到付费提示，停止操作')
                buttons=[dict(m,box=[m['box'][0]+x,m['box'][1]+y,*m['box'][2:]]) for m in words
                         if re.fullmatch(r'确定|确认|是',normalized(m['text']))]
                if len(buttons)>1:raise RuntimeError('弹窗确认按钮不唯一，停止')
                if len(buttons)==1:break
        if len(buttons)!=1:raise RuntimeError('弹窗确认按钮无法唯一识别，停止')
        self.click_item(buttons[0])
    def home(self):
        self.observe()
        if self.ocr.match(self.image,'entry_survival') and self.ocr.match(self.image,'entry_ranked'):return
        raise RuntimeError('请从木叶村主界面开始；当前页面无法可靠识别')
    def close_panel(self,check_home=True):
        self.observe();h,w=self.image.shape[:2]
        matches=[m for m in self.ocr.match(self.image,'close') if m['box'][0]>w*.65 and m['box'][1]<h*.2]
        if len(matches)!=1:raise RuntimeError('无法唯一定位游戏面板关闭图标')
        self.click_item(matches[0])
        if check_home:self.home()
    def enter(self,label):
        self.home()
        template={'生存演习':'entry_survival','强者降临':'entry_strong','排位战':'entry_ranked'}[label]
        buttons=self.ocr.match(self.image,template)
        if len(buttons)!=1:raise RuntimeError('入口图标无法唯一识别：'+label)
        self.click_item(buttons[0])
    def auto(self):
        self.log('立即检测战斗自动状态，等待控制按钮出现')
        end=time.monotonic()+30;clicked_auto=False;clicked_speed=False;next_ocr=0
        self._settlement_scan_at=0
        while time.monotonic()<end:
            self.image=self.capture_ready()
            if self.battle_settlement():
                self.log('已出现战斗结算，跳过自动和倍速，准备确认')
                return 'settled'
            h,w=self.image.shape[:2];top=int(h*.65)
            controls=self.image[top:,:].copy()
            def matches(name):
                found=self.ocr.match(controls,name)
                return [dict(m,box=[m['box'][0],m['box'][1]+top,*m['box'][2:]]) for m in found]
            on=matches('auto_on')
            off=[] if on else matches('auto_off')
            if len(on)>1 or len(off)>1:raise RuntimeError('自动按钮位置不唯一，停止')
            speed2=matches('speed2')
            speed1=[] if speed2 else matches('speed1')
            if len(speed1)>1 or len(speed2)>1:raise RuntimeError('倍速按钮位置不唯一，停止')
            # Inspect both buttons in this frame, then click them consecutively.
            if off and not clicked_auto:
                self.click_item(off[0],delay=0);clicked_auto=True
                self.log('已点击绿色自动，等待红色取消')
            if speed1 and not clicked_speed and (on or off):
                self.click_item(speed1[0],delay=0);clicked_speed=True
                self.log('已点击一倍速，等待二倍速')
            if on and len(speed2)==1:
                self.log('已确认自动开启、二倍速')
                self.window.save(self.image,Path(__file__).resolve().parents[1]/'verification/background-latest.png')
                return
            # Art templates first; OCR only the control strip as a fallback.
            if time.monotonic()>=next_ocr:
                words=self.ocr.read(controls)
                self.items=[dict(m,box=[m['box'][0],m['box'][1]+top,*m['box'][2:]]) for m in words]
                next_ocr=time.monotonic()+.75
                if not on and not clicked_auto and len(self.hits(r'^自动$'))==1:
                    self.click_text(r'^自动$',delay=0);clicked_auto=True
                    self.log('已点击绿色自动，等待红色取消')
                active=bool(on or len(self.hits(r'^取消$'))==1)
                if active and len(self.hits(r'^[xX×]2$'))==1:
                    self.log('已确认自动开启、二倍速');return
                ready=bool(on or off or self.hits(r'^(自动|取消)$'))
                if ready and not clicked_speed and len(self.hits(r'^[xX×]1$'))==1:
                    self.click_text(r'^[xX×]1$',delay=0);clicked_speed=True
                    self.log('已点击一倍速，等待二倍速')
            self.checkpoint();time.sleep(.1)
        self.window.save(self.image,Path(__file__).resolve().parents[1]/'verification/background-latest.png')
        raise RuntimeError('战斗控制按钮等待超时：未确认自动开启与二倍速，已保存截图')

    def battle_settlement(self):
        h,w=self.image.shape[:2];x=int(w*.25);y=int(h*.18)
        center=self.image[y:int(h*.76),x:int(w*.75)].copy()
        victory=bool(self.ocr.match(center,'victory'))
        now=time.monotonic()
        if not victory and now<getattr(self,'_settlement_scan_at',0):return False
        self._settlement_scan_at=now+.75
        words=self.ocr.read(center)
        confirm=[m for m in words if re.fullmatch(r'确定|确认',normalized(m['text']))]
        stats=any('战斗统计' in normalized(m['text']) for m in words)
        return len(confirm)==1 and (victory or stats)

    def battle(self):
        state=self.auto()
        if state!='settled':self.wait_text(r'^(确定|确认)$',self.cfg.get('battleSeconds',900))
        victory=bool(self.ocr.match(self.image,'victory'))
        self.confirm();return victory
    def run(self,task):return getattr(self,task)()

    def survival_reset_state(self):
        """Read reset availability explicitly; unknown is never treated as zero."""
        from survival_reset import read_survival_reset
        return read_survival_reset(self)

    def survival_reset(self):
        count,button=self.survival_reset_state()
        self.log(f'生存演习剩余重置次数 {count}')
        if not self.cfg.get('reset'):
            self.log('已关闭每日重置，保留当前进度');return
        if count==0:return
        self.observe();fresh_count,fresh_button=self.survival_reset_state()
        x,y,w,h=button['box'];fx,fy,fw,fh=fresh_button['box']
        if fresh_count!=count or abs(x+w/2-fx-fw/2)>25 or abs(y+h/2-fy-fh/2)>25:
            raise RuntimeError('生存演习重置按钮已变化，停止；不发送重置')
        button=fresh_button
        self.log('执行每日重置');self.click_item(button);self.observe()
        if self.hits(r'^(确定|确认|是)$'):self.confirm()
        def reset_done():
            try:return self.survival_reset_state()[0]==0
            except RuntimeError:return False
        self.wait(reset_done)
        self._survival_reset_done=True
        self.log('已确认剩余重置次数为0，重新读取积分与关卡次数')

    def wait_survival_ready(self):
        self.log('等待生存演习积分和重置次数稳定，复核首次显示的0次')
        signature=None;since=0;samples=0;last_error=''
        def ready():
            nonlocal signature,since,samples,last_error
            try:
                points=self.survival_points();count,_=self.survival_reset_state()
            except RuntimeError as error:
                signature=None;samples=0;last_error=str(error);return False
            current=(points,count);now=time.monotonic()
            if current!=signature:signature=current;since=now;samples=1;return False
            samples+=1
            # A newly opened panel can briefly show a cached 0 before the
            # server's reset availability arrives. Positive availability is
            # actionable sooner; zero must persist across several snapshots.
            return samples>=2 and now-since>=(3 if count==0 else .5)
        try:self.wait(ready,30)
        except RuntimeError as error:
            if '等待界面状态超时' not in str(error):raise
            raise RuntimeError('等待生存演习积分和重置次数稳定超时'+('：'+last_error if last_error else '')) from error

    def survival_candidate(self):
        coords,_=self.survival_layout()
        grades,limits=survival_plan(self.cfg)
        used=getattr(self,'_survival_used',{})
        import numpy as np
        # Evaluate in priority order so unreadable lower tiers cannot block SS.
        for grade,x,y,cx,cy in coords:
            if grade not in grades or (limits is not None and used.get(grade,0)>=limits[grade]):continue
            crop=self.image[y:y+24,x:x+21]
            rgb=Image.fromarray(crop[:,:,::-1]).resize((84,96))
            numeric=np.array(rgb)[:,:,::-1].copy()
            # The game's glyphs can shift a few pixels even at a fixed canvas
            # size. Keep the 4x scale but search around the calibrated digit.
            margin=4
            nearby=self.image[y-margin:y+24+margin,x-margin:x+21+margin]
            nearby_rgb=Image.fromarray(nearby[:,:,::-1]).resize((116,128))
            search=np.array(nearby_rgb)[:,:,::-1].copy()
            values=[str(v) for v in range(6) if self.ocr.match(search,f'digit_{v}',threshold=.95)]
            if len(values)>1:raise RuntimeError(f'{grade}剩余次数模板冲突，停止')
            if values:text=values[0]
            else:
                words=self.ocr.read(numeric,only_rec=True)
                text=''.join(normalized(i['text']) for i in words)
                if not re.fullmatch(r'[0-5]',text):raise RuntimeError(f'{grade}剩余次数未识别，停止')
            count=int(text);self.log(f'{grade}剩余挑战次数 {count}')
            if count>0:return (grade,count,cx,cy)
        raise RuntimeError('所选等级的游戏次数或计划场数已耗尽，积分未满；请在生存演习高级设置增加场数或勾选其他等级')

    def survival_layout(self):
        layouts={
            (990,1894):([('SS',798,30,864,85),('S',1300,174,1370,227),('A',697,337,755,391),('B',1175,459,1240,518),('C',1090,641,1155,703)],(914,807,1068,848)),
            (1015,1920):([('SS',810,42,878,103),('S',1308,190,1390,248),('A',710,357,778,410),('B',1188,482,1250,536),('C',1105,658,1163,714)],(928,833,1080,875))}
        layout=layouts.get(self.image.shape[:2])
        if layout is None:raise RuntimeError('当前生存面板尺寸未校准，请固定游戏窗口尺寸')
        return layout

    def survival_points(self):
        captions=self.hits('演习积分')
        if len(captions)!=1:raise RuntimeError('积分无法可靠识别')
        # A prefix match would turn "80/2]0" into the invalid ratio 80/2.
        match=re.fullmatch(r'演习积分:(\d+)/(\d+)',normalized(captions[0]['text']))
        if match and captions[0].get('score',1)>=.8:
            points,goal=map(int,match.groups())
        else:
            _,box=self.survival_layout()
            x,y,r,b=box
            import numpy as np
            source=Image.fromarray(self.image[y:b,x:r,::-1])
            readings=[]
            for scale in (2,3):
                crop=source.resize(((r-x)*scale,(b-y)*scale))
                words=self.ocr.read(np.array(crop)[:,:,::-1].copy(),only_rec=True)
                if len(words)!=1 or words[0].get('score',0)<.85:
                    raise RuntimeError('积分数字区域无法可靠识别')
                text=normalized(words[0]['text'])
                if not re.fullmatch(r'\d+/\d+',text):raise RuntimeError('积分数字区域无法可靠识别')
                readings.append(tuple(map(int,text.split('/'))))
            if readings[0]!=readings[1]:raise RuntimeError('积分数字区域双读冲突，停止')
            points,goal=readings[0]
        if goal<=0 or points>goal:raise RuntimeError('积分数值无效')
        return points,goal

    def dismiss_survival_reward_popup(self):
        popups=self.ocr.match(self.image,'reward_popup',threshold=.9)
        if len(popups)>1:raise RuntimeError('奖励弹窗识别不唯一，停止')
        if not popups:return False
        self.log('关闭恭喜获得弹窗，点击确定')
        self.confirm()
        return True

    def survival_rewards_finished(self):
        # Reward/confirmation overlays may appear after the first post-click
        # frame. Process them during polling, before inspecting stamps behind.
        if self.hits(r'领取奖励后.*无法.*更改.*演习难度.*确认领取'):
            self.confirm();return False
        if self.dismiss_survival_reward_popup():return False
        return bool(self.hits('已领取|领取成功') or len(self.ocr.match(self.image,'claimed',threshold=.88))>=6)

    def survival(self):
        grades,limits=survival_plan(self.cfg)
        self._survival_used={}
        self.log('生存演习挑战计划：'+' → '.join(g+(f'（最多{limits[g]}场）' if limits is not None else '') for g in grades))
        self.observe()
        if self.hits(r'领取奖励后.*无法.*更改.*演习难度.*确认领取'):
            self.log('确认遗留的生存演习领奖弹窗')
            self.confirm();self.observe()
        if self.dismiss_survival_reward_popup():
            self.wait(self.survival_rewards_finished,15)
            self.log('已确认积分奖励领取完成');self.close_panel();return
        if self.hits('演习积分'):
            self.log('继续当前生存演习面板')
        elif self.battle_settlement():
            self.log('处理遗留战斗结算，确认后继续生存演习')
            self.confirm();self.wait_text('演习积分')
        else:
            self.enter('生存演习');self.wait_text('演习积分')
        self.wait_survival_ready()
        self.survival_reset()
        last=None
        for _ in range(30):
            self.observe();points,goal=self.survival_points()
            self.log(f'生存演习积分 {points}/{goal}')
            if points>=goal:
                if self.dismiss_survival_reward_popup():
                    self.wait(self.survival_rewards_finished,15)
                    self.log('已确认积分奖励领取完成');self.close_panel();return
                if self.cfg.get('reset') and not getattr(self,'_survival_reset_done',False):
                    self.wait_survival_ready()
                    count,_=self.survival_reset_state()
                    if count==1:
                        self.log('退出前复核发现剩余重置1次，先重置再判断积分')
                        self.survival_reset();last=None;continue
                    points,goal=self.survival_points()
                    if points<goal:continue
                stamps=self.ocr.match(self.image,'claimed',threshold=.88)
                if len(stamps)>=6:self.log('可见积分奖励已领取');self.close_panel();return
                self.click_text(r'^(一?键领取)$');self.observe()
                if self.hits('领取.*无法|无法.*难度'):self.confirm();self.observe()
                if self.hits(r'^(确定|确认)$'):self.confirm();self.observe()
                # Claimed stamps require a dedicated template before declaring completion.
                self.wait(self.survival_rewards_finished,15)
                self.log('已确认积分奖励领取完成')
                self.close_panel();return
            candidate=self.survival_candidate()
            if last and last==(points,candidate):raise RuntimeError('战斗后积分及次数均未改变')
            last=(points,candidate)
            self.log(f'选择 {candidate[0]}，进入开战界面')
            from survival_start import start_survival_battle
            self.window.click(candidate[2],candidate[3]);start_survival_battle(self)
            self.battle()
            self._survival_used[candidate[0]]=self._survival_used.get(candidate[0],0)+1
            self.wait_text('演习积分')
        raise RuntimeError('生存演习达到循环上限')

    def strong_panel_buttons(self):
        h,w=self.image.shape[:2]
        buttons={}
        for grade,name in [('天级','strong_sky'),('夜叉级','strong_yaksha'),('阿修罗级','strong_asura')]:
            matches=[m for m in self.ocr.match(self.image,name) if m['box'][1]>h*.6 and m['box'][1]<h*.9]
            if len(matches)!=1:raise RuntimeError('强者降临三个难度选项未完整且唯一识别')
            buttons[grade]=matches[0]
        boxes=[b['box'] for b in buttons.values()]
        if not boxes[0][0]<boxes[1][0]<boxes[2][0] or max(b[1] for b in boxes)-min(b[1] for b in boxes)>h*.05:
            raise RuntimeError('强者降临三个难度选项位置不一致')
        return buttons

    def strong_reward_state(self):
        buttons=self.strong_panel_buttons()
        # Anchor to the sky icon: isolate the ordinary reward count on the left,
        # never the organization/cooperation count on the right.
        x,y,bw,bh=buttons['天级']['box'];scale=bw/158
        left=x+round(364*scale);top=y+round(117*scale)
        right=left+round(45*scale);bottom=top+round(43*scale)
        h,w=self.image.shape[:2]
        if not (0<=left<right<=w and 0<=top<bottom<=h):raise RuntimeError('强者降临普通奖励次数区域超出画面')
        crop=self.image[top:bottom,left:right].copy()
        values=[value for value in (0,1) if self.ocr.match(crop,f'strong_count{value}',threshold=.95)]
        if len(values)>1:raise RuntimeError('强者降临普通奖励次数模板冲突，停止')
        if values:count=values[0]
        else:
            import numpy as np
            rgb=Image.fromarray(crop[:,:,::-1]).resize((crop.shape[1]*3,crop.shape[0]*3))
            words=self.ocr.read(np.array(rgb)[:,:,::-1].copy(),only_rec=True)
            text=''.join(normalized(item['text']) for item in words)
            if not re.fullmatch(r'\d{1,2}',text):raise RuntimeError('强者降临普通奖励次数数字无法可靠识别')
            count=int(text)
        full_counts=[]
        for item in self.hits(r'普通奖励次数:?(\d+)'):
            full_counts.append(int(re.search(r'普通奖励次数:?(\d+)',normalized(item['text'])).group(1)))
        if any(value!=count for value in full_counts):raise RuntimeError('强者降临普通奖励次数识别冲突，停止')
        return count,buttons

    def wait_strong_ready(self):
        last=None;result=None;last_error=''
        def ready():
            nonlocal last,result,last_error
            try:result=self.strong_reward_state()
            except RuntimeError as error:
                last=None;last_error=str(error);return False
            count=result[0]
            stable=last==count;last=count
            return stable
        self.log('等待强者降临三个难度与普通奖励次数完整显示')
        try:self.wait(ready,30)
        except RuntimeError as error:
            if '等待界面状态超时' not in str(error):raise
            raise RuntimeError('强者降临面板识别超时'+('：'+last_error if last_error else '：普通奖励次数未稳定')) from error
        return result

    def strong_start_button(self):
        h,w=self.image.shape[:2]
        buttons=self.hits(r'^进入战斗$')
        if not buttons:buttons=self.ocr.match(self.image,'strong_enter',threshold=.9)
        buttons=[b for b in buttons if w*.2<b['box'][0]<w*.6 and h*.4<b['box'][1]<h*.8]
        if len(buttons)>1:raise RuntimeError('强者降临进入战斗按钮不唯一')
        return buttons[0] if buttons else None

    def strong(self):
        grade=self.cfg.get('difficulty','阿修罗级')
        if grade not in ('天级','夜叉级','阿修罗级'):raise RuntimeError('强者降临难度无效')
        self.observe()
        try:self.strong_panel_buttons()
        except RuntimeError:self.enter('强者降临')
        else:self.log('继续当前强者降临面板')
        count,buttons=self.wait_strong_ready()
        self.log(f'本周可用普通奖励次数 {count}；所选难度 {grade}')
        if count==0:self.log('本周普通奖励次数为0，跳过');self.close_panel();return
        self.log('点击强者降临难度 '+grade)
        self.click_item(buttons[grade])
        self.wait(lambda:self.strong_start_button() is not None,15)
        start=self.strong_start_button()
        self.log('点击强者降临进入战斗')
        self.click_item(start,delay=0)
        victory=self.battle();self.observe()
        if self.hits('查看分数'):self.click_text('查看分数');self.wait_text(r'^(确定|确认)$');self.confirm()
        self.home()
        if not victory:raise RuntimeError('战斗结算已处理，但未确认胜利，不能报告完成')

    def ranked_panel_visible(self):
        """Shared, read-only panel gate for entry, waits, scope and return.

        A counter caption is neither necessary nor sufficient on its own:
        require the ranked title, an independent control and a readable count.
        Power and all five opponents are validated later by ranked_state.
        """
        h,w=self.image.shape[:2]
        # A visible background panel must not qualify through a modal dialog.
        if any(re.fullmatch(r'确定|确认|取消|是|否',normalized(item['text']))
               and w*.3<item['box'][0]<w*.7 and h*.2<item['box'][1]<h*.8
               for item in self.items):return False
        if self.ranked_server_state() not in ('本服','连服'):return False
        control=any(normalized(item['text'])=='调整阵容' and item.get('score',1)>=.8
                    and item['box'][0]<w*.25 and h*.15<item['box'][1]<h*.35
                    for item in self.items)
        if not control:
            state,_=self.ranked_refresh_state()
            if state not in ('ready','cooldown'):return False
        try:read_ranked_remaining(self.image,self.items,self.ocr,normalized)
        except RuntimeError:return False  # Unknown/conflicting count is not a page hit.
        return True

    def ranked_state(self):
        h,w=self.image.shape[:2]
        self.ranked_number_evidence=None;self.ranked_number_crops=[]
        count=read_ranked_remaining(self.image,self.items,self.ocr,normalized)
        if count==0:return count,None,[]
        own=read_red_power(self.image,self.ocr)
        buttons=sorted([b for b in self.hits(r'^挑战$') if b['box'][1]>h*.55],key=lambda b:b['box'][0])
        if len(buttons)!=5:raise RuntimeError('未完整识别五个排位战挑战按钮')
        centers=[b['box'][0]+b['box'][2]/2 for b in buttons]
        if any(b-a<w*.08 for a,b in zip(centers,centers[1:])):
            raise RuntimeError('未唯一定位五个排位战挑战按钮')
        opponents=[];records=[];errors=[]
        for index,button in enumerate(buttons,1):
            try:record=read_opponent(self.image,button,self.ocr)
            except NumberRecognitionError as error:
                record=error.evidence;errors.append(f'第{index}位：{error}')
            records.append(record)
            box=record.get('numericBox')
            crop=self.image[box[1]:box[3],box[0]:box[2],::-1].copy() if box else None
            self.ranked_number_crops.append(crop)
            if record.get('value') is not None:opponents.append({'power':record['value'],'button':button})
        self.ranked_number_evidence={'version':1,'reader':'ranked_numbers','stage':'ranked_state',
                                    'observedAt':time.time(),'imageShape':list(self.image.shape),'opponents':records}
        if errors:raise RuntimeError('排位战对手数字未可靠确认；'+'；'.join(errors))
        return count,own,opponents

    def wait_ranked_ready(self):
        previous=None;result=None;error=''
        def ready():
            nonlocal previous,result,error
            if not self.ranked_panel_visible():
                previous=None;error='排位面板证据未完整确认';return False
            try:result=self.ranked_state()
            except RuntimeError as e:previous=None;error=str(e);return False
            count,own,opponents=result
            current=(count,own,tuple(sorted(o['power'] for o in opponents)))
            stable=previous==current;previous=current
            return stable
        self.log('复核排位战剩余次数、红色我方战力和五名对手战力')
        try:self.wait(ready,30)
        except RuntimeError as e:
            if '等待界面状态超时' not in str(e):raise
            raise RuntimeError('排位战面板识别超时：'+(error or '战力或次数未稳定')) from e
        return result

    def ranked_server_state(self):
        h,w=self.image.shape[:2]
        title=self.image[:int(h*.18),int(w*.35):int(w*.6)].copy()
        found=[server for server,name in [('本服','ranked_title_local'),('连服','ranked_title_cross')]
               if self.ocr.match(title,name,threshold=.9)]
        if not found:
            words=self.ocr.read(title)
            for item in words:
                text=normalized(item['text'])
                if re.fullmatch(r'本服(?:排行(?:榜)?)?',text):found.append('本服')
                if re.fullmatch(r'[联连]服(?:排行(?:榜)?)?',text):found.append('连服')
        if len(set(found))>1:raise RuntimeError('排位战本服/连服标题识别冲突')
        return found[0] if found else None

    def ranked_server_button(self,server):
        h,w=self.image.shape[:2];left=int(w*.8)
        region=self.image[:int(h*.1),left:].copy()
        name='ranked_local' if server=='本服' else 'ranked_cross'
        buttons=self.ocr.match(region,name,threshold=.9)
        if len(buttons)!=1:raise RuntimeError('无法唯一定位排位战'+server+'切换按钮')
        b=buttons[0];return dict(b,box=[b['box'][0]+left,b['box'][1],*b['box'][2:]])

    def ensure_ranked_server(self,server):
        self.observe()
        if self.ranked_server_state()==server:
            self.log('已确认排位战挑战范围：'+server);return
        self.click_item(self.ranked_server_button(server))
        stable=0
        def ready():
            nonlocal stable
            stable=stable+1 if self.ranked_panel_visible() and self.ranked_server_state()==server else 0
            return stable>=2
        self.wait(ready,30)
        self.log('已切换并确认排位战挑战范围：'+server)

    def ranked_battle_result(self):
        """Return only an explicit result, never infer defeat from missing victory."""
        h,w=self.image.shape[:2]
        center=self.image[int(h*.18):int(h*.6),int(w*.25):int(w*.75)].copy()
        results=set()
        if self.ocr.match(center,'victory',threshold=.9):results.add('victory')
        if self.ocr.match(center,'defeat',threshold=.9):results.add('defeat')
        for item in self.ocr.read(center):
            text=normalized(item['text'])
            if re.fullmatch(r'胜利|战斗胜利|挑战成功|胜',text):results.add('victory')
            if re.fullmatch(r'失败|战斗失败|挑战失败|战败|败北|败',text):results.add('defeat')
        # A settled battle's explicit 0 HP also supplies a local result when
        # the large decorative outcome character cannot be transcribed.
        def health(left,right):
            region=self.image[int(h*.04):int(h*.105),int(w*left):int(w*right)].copy()
            values=[]
            for item in self.ocr.read(region):
                match=re.fullmatch(r'(\d{1,7})/(\d{1,7})',normalized(item['text']))
                if match:
                    current,total=map(int,match.groups())
                    if 0<=current<=total and total>100:values.append(current)
            return values[0] if len(set(values))==1 else None
        own,enemy=health(.06,.35),health(.64,.94)
        if own==0 and enemy is not None and enemy>0:results.add('defeat')
        if enemy==0 and own is not None and own>0:results.add('victory')
        if len(results)!=1:raise RuntimeError('排位战胜负无法可靠识别，已保留结算；不会猜测战败或刷新')
        return results.pop()

    def ranked_refresh_state(self):
        h,w=self.image.shape[:2];left=int(w*.8);top=int(h*.8)
        region=self.image[top:,left:].copy()
        words=self.ocr.read(region)
        text=' '.join(normalized(m['text']) for m in words)
        # Cooldown takes priority even if the blue button still matches.
        if re.search(r'冷却|(?:\d{1,2}:\d{2})|(?:\d+分\d*秒)|(?:\d+秒)',text):return 'cooldown',None
        buttons=self.ocr.match(region,'ranked_refresh',threshold=.9)
        if not buttons:buttons=[m for m in words if normalized(m['text'])=='刷新对手']
        if len(buttons)>1:raise RuntimeError('刷新对手按钮不唯一')
        if not buttons:return 'unknown',None
        b=buttons[0]
        return 'ready',dict(b,box=[b['box'][0]+left,b['box'][1]+top,*b['box'][2:]])

    def refresh_ranked_after_defeat(self):
        self.observe()
        state,button=self.ranked_refresh_state()
        if state=='cooldown':
            self.log('刷新对手正在冷却，继续按原规则挑战');return
        if state!='ready':raise RuntimeError('无法确认刷新对手按钮或冷却状态，停止')
        _,_,old_opponents=self.wait_ranked_ready()
        old_powers=tuple(o['power'] for o in old_opponents)
        previous=None
        self.log('排位战战败，点击刷新对手');self.click_item(button)
        def resolved():
            nonlocal previous
            # Some clients display a dialog only after pressing a cooling
            # button. Dismiss its free acknowledgement, then continue.
            if self.hits(r'元宝|点券|付费|购买|支付|花费'):
                raise RuntimeError('刷新对手出现付费提示，停止')
            cooldown=self.hits(r'冷却|刷新.*(?:稍后|等待|秒|分钟)')
            if cooldown:
                if self.hits(r'^(确定|确认)$'):self.confirm();self.observe()
                self.log('刷新对手正在冷却，继续按原规则挑战');return True
            state,_=self.ranked_refresh_state()
            if state=='cooldown' and self.ranked_panel_visible():return True
            if not self.ranked_panel_visible():return False
            try:_,_,opponents=self.ranked_state()
            except RuntimeError:return False
            powers=tuple(o['power'] for o in opponents)
            changed=powers!=old_powers and powers==previous
            previous=powers
            return changed
        # Confirm cooldown or a stable changed opponent list before the
        # next challenge rereads all five opponents.
        self.wait(resolved,15)
        self.log('刷新检查结束，重新读取当前对手')

    def ranked_end_battle_button(self):
        """Locate the star button inside the battle controls, away from retreat."""
        h,w=self.image.shape[:2];left=int(w*.84);top=int(h*.82)
        region=self.image[top:,left:].copy()
        # The full star sprite includes moving combat scenery. Prefer its
        # stable white label and reconstruct the hit area relative to that
        # moving anchor; these offsets are internal artwork geometry.
        anchors=self.ocr.match(region,'ranked_end_label',threshold=.9)
        buttons=[dict(m,box=[m['box'][0]-68,m['box'][1]-10,127,103]) for m in anchors]
        if not buttons:buttons=self.ocr.match(region,'end_battle',threshold=.9)
        if not buttons:
            buttons=[m for m in self.ocr.read(region)
                     if re.fullmatch(r'结束战斗',normalized(m['text']))]
        if len(buttons)>1:raise RuntimeError('右下角结束战斗按钮不唯一，停止')
        if not buttons:return None
        button=buttons[0]
        return dict(button,box=[button['box'][0]+left,button['box'][1]+top,*button['box'][2:]])

    def finish_ranked_battle(self):
        button=None
        self._settlement_scan_at=0
        def ready():
            nonlocal button
            if self.battle_settlement():return True
            button=self.ranked_end_battle_button()
            return button is not None
        self.log('等待排位战右下角结束战斗按钮或战斗结算')
        try:self.wait(ready,120)
        except RuntimeError as error:
            if '等待界面状态超时' not in str(error):raise
            raise RuntimeError('排位战结束战斗按钮识别超时，已保存最后截图') from error
        if button is not None:
            self.log('已定位右下角星形结束战斗按钮，发送后台点击')
            self.click_item(button)
            self.wait_text(r'^(确定|确认)$',self.cfg.get('battleSeconds',900))
        else:self.log('排位战已出现结算，准备确认')
        result=self.ranked_battle_result()
        self.log('排位战结算：'+('胜利' if result=='victory' else '失败'))
        self.confirm()
        self.wait(self.ranked_panel_visible)
        self.log('排位战结算已确认，已返回挑战面板')
        return result

    def ranked(self):
        server,limit=ranked_options(self.cfg)
        self.observe()
        pending=None;completed=0
        if self.ranked_panel_visible():self.log('继续当前排位战面板')
        elif self.ranked_end_battle_button() is not None or self.battle_settlement():
            self.log('继续当前排位战战斗或结算')
            pending=self.finish_ranked_battle();completed=1
        else:self.enter('排位战')
        self.ensure_ranked_server(server)
        self.log('排位战计划：'+server+'，'+(f'最多{limit}场' if limit else '用完剩余次数'))
        last=None
        for _ in range(30):
            count,own,opponents=self.wait_ranked_ready()
            self.log(f'排位战剩余次数 {count}')
            if last is not None and count>=last:raise RuntimeError('挑战次数未减少')
            if count==0 or limit and completed>=limit:
                self.log(f'排位战本轮已挑战{completed}场，剩余{count}次')
                self.close_panel();return 'skipped' if completed==0 else None
            if pending=='defeat':
                before_refresh=count
                self.refresh_ranked_after_defeat()
                count,own,opponents=self.wait_ranked_ready()
                if count!=before_refresh:raise RuntimeError('刷新后挑战次数变化异常，停止')
                pending=None
            picked=select_opponent(own,opponents,self.cfg.get('tolerance',20))
            self.log(f'我方战力 {own}，五名对手 '+ ' / '.join(str(o['power']) for o in opponents))
            self.log(f'选择对手 {picked["power"]}，战力差 {abs(picked["power"]-own)/own:.1%}');self.click_item(picked['button'])
            pending=self.finish_ranked_battle();completed+=1;last=count
        raise RuntimeError('排位战达到循环上限')

    def hosting_computer_button(self):
        h,w=self.image.shape[:2]
        # This entrance belongs to the player panel, below the badge. Search
        # actual artwork within that panel instead of clicking a fixed point.
        left=top=0;right=int(w*.42);bottom=int(h*.25)
        badges=[m for m in self.hits(r'^中忍勋章$')
                if m['box'][0]<right and m['box'][1]<bottom]
        if len(badges)>1:raise RuntimeError('中忍勋章位置不唯一，停止定位托管入口')
        if badges:
            x,y,bw,bh=badges[0]['box']
            left=max(0,x);top=max(0,y+bh)
            right=min(right,x+bw+int(max(40,bw*.5)))
            bottom=min(bottom,y+bh+int(max(80,bh*4)))
        region=self.image[top:bottom,left:right].copy()
        buttons=[dict(m,box=[m['box'][0]+left,m['box'][1]+top,*m['box'][2:]])
                 for m in self.ocr.match(region,'computer')]
        if badges:
            buttons=[m for m in buttons if m['box'][0]+m['box'][2]/2>=x+bw*.5]
        if len(buttons)>1:raise RuntimeError('中忍勋章下方托管小电脑图标不唯一，停止')
        return buttons[0] if buttons else None

    def hosting_activation_dialog(self):
        h,w=self.image.shape[:2];x=int(w*.33);y=int(h*.36)
        region=self.image[y:int(h*.65),x:int(w*.66)].copy()
        words=self.ocr.read(region)
        texts=[normalized(m['text']) for m in words]
        if not any('首次进入托管状态' in t for t in texts):return None
        if any(re.search(r'购买|支付|花费|元宝|点券|不足|不够',t) for t in texts):
            raise RuntimeError('首次托管提示包含购买、付费或卡不足，停止')
        if not any(re.search(r'消耗托管卡(?:[xX×*])?1(?=[，,。]|有效期|$)',t) for t in texts):
            # The gold x1 glyph is often transcribed as 11. Verify the full
            # card x1 artwork rather than interpreting 11 as one card.
            card=self.ocr.match(region,'hosting_card1',threshold=.95)
            if len(card)!=1:raise RuntimeError('首次托管未确认仅消耗1张托管卡，停止')
        if not any('是否确认进入托管状态' in t for t in texts):return None
        buttons=[m for m in words if re.fullmatch(r'确定|确认',normalized(m['text']))]
        cancel=[m for m in words if normalized(m['text'])=='取消']
        if len(buttons)!=1 or len(cancel)!=1:
            raise RuntimeError('首次托管弹窗确认与取消按钮未唯一识别，停止')
        return dict(buttons[0],box=[buttons[0]['box'][0]+x,buttons[0]['box'][1]+y,*buttons[0]['box'][2:]])

    def wait_hosting_started(self,seconds=30):
        end=time.monotonic()+seconds;confirmed=False
        while time.monotonic()<end:
            self.observe()
            button=self.hosting_activation_dialog()
            if button is not None:
                if not confirmed:
                    self.log('首次开启托管：确认消耗1张托管卡')
                    self.click_item(button,delay=0);confirmed=True
            elif self.hits(r'^托管中$'):
                self.log('已确认进入托管中状态');return
            self.checkpoint();time.sleep(.2)
        raise RuntimeError('等待进入托管超时：未确认托管中状态，已保存最后截图')

    def hosting(self):
        self.observe()
        activation=self.hosting_activation_dialog()
        if activation is None and not self.hits(r'^托管中$'):
            settings=bool(self.hits(r'^托管设置$|^托管日志$')) and len(self.hits(r'^开始托管$'))==1
            if not settings:
                self.home();button=self.hosting_computer_button()
                if button is None:
                    self.log('等待中忍勋章下方托管小电脑图标加载')
                    self.wait(lambda:self.hosting_computer_button() is not None,15)
                    button=self.hosting_computer_button()
                if button is None:raise RuntimeError('托管小电脑图标未识别，停止操作')
                self.log('已定位中忍勋章下方的托管小电脑图标')
                self.click_item(button);self.wait_text(r'^开始托管$')
            self.log('点击开始托管，检查首次确认或直接托管状态')
            self.click_text(r'^开始托管$',delay=0)
        elif activation is not None:
            self.log('检测到遗留的首次托管确认弹窗，继续处理')
        self.wait_hosting_started()
        # Establish completion against the current run, not an older log entry.
        if self.hits('托管结束'):raise RuntimeError('日志中含旧的托管结束记录，无法确认本轮状态')
        self.wait(lambda:bool(self.hits('托管结束')),self.cfg.get('hostingMinutes',90)*60)
        if self.hits('温泉|泡温泉'):
            self.close_panel(check_home=False);self.observe()
            if self.hits(r'^(确认|确定)$'):self.confirm();self.observe()
        if self.hits(r'^离开$'):
            self.click_text(r'^离开$');self.observe()
            if self.hits(r'^(确认|确定)$'):self.confirm()
        self.home()

    def escort(self):
        self.home();self.click_text('组队副本');self.wait_text('押镖劫掠')
        activity=self.hits('押镖劫掠')[0]
        buttons=[b for b in self.hits('参加') if abs(b['box'][1]-activity['box'][1])<60]
        if len(buttons)!=1:raise RuntimeError('无法定位押镖活动的参加按钮')
        self.click_item(buttons[0]);self.wait_text('今日剩余完成次数')
        grade=self.cfg.get('escortGrade','SS')
        if grade not in ('SS','S'):raise RuntimeError('押镖等级无效')
        limit=self.cfg.get('escortRefreshLimit',4);previous=None
        for refreshed in range(limit+1):
            self.observe();count=remaining(self.items,r'今日剩余完成次数:?(\d+)/3')
            if count>3:raise RuntimeError('押镖次数识别异常')
            if count==0:self.close_panel();return 'skipped'
            # Grade artwork needs exact template calibration, not a guessed OCR substring.
            tiers=self.ocr.match(self.image,'escort_'+grade)
            if tiers:
                tier=min(tiers,key=lambda t:t['box'][1])
                buttons=[b for b in self.hits(r'^押送$') if abs(b['box'][1]-tier['box'][1])<80]
                if len(buttons)!=1:raise RuntimeError('无法定位对应等级的押送按钮')
                self.click_item(buttons[0]);self.wait(lambda:not self.hits('今日剩余完成次数') and bool(self.hits('押送中|押送物品|押镖')),30)
                self.log(f'{grade}任务已接取，交付步骤待补充');return 'accepted'
            other='S' if grade=='SS' else 'SS'
            alternatives=self.ocr.match(self.image,'escort_'+other)
            if len(alternatives)!=3:raise RuntimeError('没有完整识别三行押镖等级，不会盲目刷新')
            free=remaining(self.items,r'免费刷新[（(]?(\d+)')
            if previous is not None and free>=previous:raise RuntimeError('刷新次数未减少')
            if free==0 or refreshed>=limit:raise RuntimeError('没有所选等级，免费刷新次数或设置上限已用完')
            def ready():
                timers=self.hits(r'剩余.*时间:?(\d+):(\d+)')
                if len(timers)!=1:return False
                match=re.search(r'剩余.*时间:?(\d+):(\d+)',normalized(timers[0]['text']))
                return int(match.group(1))==0 and int(match.group(2))==0 and bool(self.hits('免费刷新'))
            self.wait(ready,600)
            self.click_text('免费刷新');previous=free
