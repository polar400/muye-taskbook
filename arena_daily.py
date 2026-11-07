"""Arena battles with a shared count limit and opportunistic task rewards."""
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import uuid

from adapters.local_ocr import ReadOnlyController
import numpy as np
from PIL import Image
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JTemplateMatch
from arena_tokens import DAILY_MODE,TokenPolicy,TokenReader
from arena_settings import battle_limit

ROOT=Path(__file__).resolve().parent


def norm(text):return re.sub(r'\s+','',text).replace('：',':').replace('／','/')


class DailyVision:
    def __init__(self,ocr,image_dir=None):
        self.ocr=ocr;self.resource=Resource()
        if not self.resource.post_image(image_dir or ROOT/'resources/local/arena_daily/image').wait().succeeded:
            raise RuntimeError('竞技场日常模板加载失败')
        self.controller=ReadOnlyController();self.controller.post_connection().wait()
        self.tasker=Tasker();self.tasker.bind(self.resource,self.controller)

    def match(self,image,name):
        self.controller.image=image
        detail=self.tasker.post_recognition('TemplateMatch',JTemplateMatch(
            template=([name+'.png','lower_highlight.png'] if name=='lower' else [name+'.png']),
            threshold=[.9]),image).wait().get()
        found=[]
        if detail:
            for node in detail.nodes:
                if not node.recognition:continue
                for item in node.recognition.filtered_results:
                    box=list(item.box)
                    if not any(abs(box[0]-m['box'][0])<18 and abs(box[1]-m['box'][1])<18 for m in found):
                        found.append(dict(box=box,score=float(item.score)))
        return found

    def read(self,image,origin=(0,0)):
        """Read only the task strip. Count zero never overrides visible cards."""
        states={name:self.match(image,name) for name in ('eligible','unmet','claim','lower')}
        bars=[]
        for name,progress in (('progress_zero',0),('progress_zero_unmet',0),
                              ('progress_zero_lower',0),('progress_done',1)):
            for bar in self.match(image,name):
                x,y,w,h=bar['box']
                old=next((b for b in bars if abs(x-b['box'][0])<20 and abs(y-b['box'][1])<15),None)
                if old:
                    if old['progress']!=progress:raise RuntimeError('竞技场任务进度模板冲突')
                else:bars.append(dict(bar,progress=progress))
        cards=[];used=set()
        for bar in sorted(bars,key=lambda b:b['box'][1]):
            x,y,w,h=bar['box'];candidates=[]
            for name,buttons in states.items():
                for button in buttons:
                    bx,by,bw,bh=button['box']
                    if 5<=y-by<=80 and abs((bx+bw/2)-(x+w/2))<65:
                        candidates.append((name,button))
            if len(candidates)!=1:return None
            name,button=candidates[0]
            used.add((name,tuple(button['box'])))
            state='unmet' if name=='lower' else name
            if (state=='claim')!=(bar['progress']==1):return None
            left=max(0,x-130);right=min(image.shape[1],x+w+12)
            top=max(0,y-140);bottom=max(0,y-50)
            words=self.ocr.read(image[top:bottom,left:right].copy())
            description=''.join(norm(m['text']) for m in sorted(words,key=lambda m:m['box'][1])
                                if m.get('score',0)>=.8)
            if not description:
                crop=image[top:bottom,left:right].copy()
                enlarged=np.array(Image.fromarray(crop).resize((crop.shape[1]*2,crop.shape[0]*2)))
                words=self.ocr.read(enlarged)
                description=''.join(norm(m['text']) for m in sorted(words,key=lambda m:m['box'][1])
                                    if m.get('score',0)>=.85)
            if not description:return None
            ox,oy=origin
            cards.append(dict(index=len(cards),description=description,state=state,
                              progress=bar['progress'],hovered=name=='lower',
                              button=dict(button,box=[button['box'][0]+ox,button['box'][1]+oy,*button['box'][2:]])))
        if any((name,tuple(button['box'])) not in used for name,buttons in states.items() for button in buttons):return None
        headers=self.match(image,'header')
        if len(headers)!=1:return None
        x,y,w,h=headers[0]['box'];region=image[max(0,y-5):y+h+6,max(0,x-110):x+w+6].copy()
        counts=[]
        for scale in (2,3):
            view=np.array(Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale)))
            words=self.ocr.read(view,only_rec=True)
            if len(words)==1 and words[0].get('score',0)>=.9:
                match=re.fullmatch(r'剩余([0-6])个任务可挑战[。.]?',norm(words[0]['text']))
                if match:counts.append(int(match.group(1)))
        count=counts[0] if len(counts)==2 and len(set(counts))==1 else None
        if count==0 and cards:count=None
        if count==0 and not cards:
            body=self.ocr.read(image[min(image.shape[0],y+h+8):].copy())
            if any(re.search(r'胜利|条件|领取|降低|[01]/1',norm(m['text'])) for m in body):return None
        if not cards and count!=0:return None
        if count is not None and count<len(cards):return None
        return dict(remaining=count,cards=cards)


def board_key(board):
    return (board['remaining'],tuple((c['description'],c['state'],c['progress']) for c in board['cards']))


def next_action(board):
    for card in board['cards']:
        if card['state']=='claim':return 'claim',card
        if card['state'] not in ('unmet','eligible'):raise RuntimeError('竞技场任务状态未知，停止')
    return 'battle',None


class ArenaDaily:
    def __init__(self,arena,mode):
        self.a=arena;self.f=arena.f;self.mode=mode;self.vision=None
        self.sequence=0;self.events=[];self.battles=0
        self.battle_limit=battle_limit(self.f.cfg)
        self.tokens=TokenPolicy(self.a.now) if mode==DAILY_MODE else None
        self.token_reader=None;self.token_reads=[]
        self.folder=ROOT/'verification'/('arena-daily-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])

    def record(self,stage,**data):
        self.events.append(dict(stage=stage,**data))
        self.f.log('竞技场日常：'+stage)

    def board(self):
        self.check_budget()
        if not self.a.panel():return None
        if self.vision is None:self.vision=DailyVision(self.f.ocr)
        return self.vision.read(self.f.image[350:790,90:342].copy(),(90,350))

    def check_budget(self):
        if self.tokens:self.tokens.check_time()

    def read_tokens(self):
        self.check_budget()
        if not self.a.panel():return None
        if self.token_reader is None:
            matcher=DailyVision(self.f.ocr,ROOT/'resources/local/arena_tokens/image')
            self.token_reader=TokenReader(self.f.ocr,matcher)
        image=self.f.image
        value=self.token_reader.read(image[110:190,960:1152].copy())
        self.token_reads.append(dict(value=value,evidence=self.token_reader.evidence))
        return value

    def stable_tokens(self):
        last=None;frames=0
        def read():
            nonlocal last,frames
            self.check_budget()
            if not self.a.panel():return None
            value=self.read_tokens()
            if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=3:
                raise RuntimeError('战令数无法可靠读取，停止，不默认还有3个')
            frames=frames+1 if value==last else 1;last=value
            return dict(count=value) if frames>=2 else None
        count=self.a.wait('连续两帧确认实际战令',read)['count']
        self.record('确认实际战令',count=count)
        return count

    def stable(self,label='读取左侧日常任务',predicate=lambda b:True):
        last=None;frames=0
        def read():
            nonlocal last,frames
            board=self.board()
            if board is None or not predicate(board):last=None;frames=0;return None
            key=board_key(board);frames=frames+1 if key==last else 1;last=key
            return board if frames>=2 else None
        return self.a.wait(label,read)

    def act(self,label,reader,allow_victory=True):
        self.sequence+=1
        def checked():
            self.check_budget()
            return reader()
        self.a.click(str(self.sequence)+' · '+label,checked,allow_victory=allow_victory)
        self.record(label)

    def fresh_card(self,expected,index,state,hovered=False):
        board=self.board()
        if board is None:return None
        if board_key(board)!=board_key(expected):raise RuntimeError('竞技场任务在输入前变化，停止并重新核对')
        card=board['cards'][index]
        if card['state']!=state or (hovered and not card['hovered']):return None
        return card['button']

    def claim(self,board,card):
        self.act('领取已完成任务',lambda:self.fresh_card(board,card['index'],'claim'))
        old=Counter(c['description'] for c in board['cards'] if c['state']=='claim')
        def changed(new):
            if board['remaining'] is not None and new['remaining'] is not None:
                if new['remaining']>board['remaining']:raise RuntimeError('领取后任务数异常增加')
                return new['remaining']<board['remaining']
            current=Counter(c['description'] for c in new['cards'] if c['state']=='claim')
            return current[card['description']]<old[card['description']]
        return self.stable('确认领取后任务减少或该领取项消失',changed)

    def lower_dialog(self):
        image=self.f.image;h,w=image.shape[:2];x=int(w*.25);y=int(h*.18)
        words=self.f.ocr.read(image[y:int(h*.8),x:int(w*.75)].copy())
        words=[dict(m,box=[m['box'][0]+x,m['box'][1]+y,*m['box'][2:]]) for m in words if m.get('score',0)>=.85]
        body=''.join(norm(m['text']) for m in words)
        if re.search(r'元宝|点券|购买|支付|花费|消耗|扣除',body):raise RuntimeError('降低难度出现消耗提示，停止')
        if not re.search(r'降低.{0,8}难度|任务.{0,8}降级',body):return None
        buttons=[m for m in words if norm(m['text'])=='确定']
        if len(buttons)>1:raise RuntimeError('降低难度确认按钮不唯一')
        return buttons[0] if len(buttons)==1 else None

    def lower(self,board,card):
        raise RuntimeError('竞技场任务降低难度已停用，请人工处理')

    def settlement(self):
        popup=self.a.popup()
        if popup:
            return dict(result='victory',button=popup['button']) if popup['kind']=='victory' and popup['button'] else None
        image=self.f.image;h,w=image.shape[:2];x=int(w*.25);y=int(h*.18)
        region=image[y:int(h*.8),x:int(w*.75)].copy()
        results=set()
        for name in ('victory','defeat'):
            if self.f.ocr.match(region,name,threshold=.9):results.add(name)
        words=self.f.ocr.read(region)
        for m in words:
            if m.get('score',0)<.85:continue
            text=norm(m['text'])
            if re.fullmatch(r'胜利|战斗胜利|挑战成功|胜',text):results.add('victory')
            if re.fullmatch(r'失败|战斗失败|挑战失败|战败|败北|败',text):results.add('defeat')
        buttons=[dict(m,box=[m['box'][0]+x,m['box'][1]+y,*m['box'][2:]]) for m in words
                 if m.get('score',0)>=.85 and norm(m['text']) in ('确定','确认')]
        if len(results)>1:raise RuntimeError('竞技场胜负证据冲突')
        if len(buttons)>1 and results:raise RuntimeError('竞技场结算确定按钮不唯一')
        if len(results)==1 and len(buttons)==1:return dict(result=results.pop(),button=buttons[0])
        return None

    def auto(self):
        if self.a.popup():return {}
        image=self.f.image;h=image.shape[0];top=int(h*.65)
        region=image[top:].copy();found={}
        for state in ('on','off'):
            matches=self.f.ocr.match(region,'auto_'+state,threshold=.9)
            if len(matches)>1:raise RuntimeError('竞技场自动按钮不唯一')
            if matches:found[state]=dict(matches[0],box=[matches[0]['box'][0],matches[0]['box'][1]+top,*matches[0]['box'][2:]])
        if len(found)>1:raise RuntimeError('竞技场自动状态冲突')
        return found

    def fight(self,board,mode=None,token_baseline=None):
        match_mode=mode or self.mode
        def chosen():
            if self.battles>=self.battle_limit:raise RuntimeError('已达到竞技场战斗场数上限，未发送匹配')
            current=self.board()
            if current is None:return None
            if board_key(current)!=board_key(board):raise RuntimeError('匹配前日常任务已变化，停止')
            if next_action(current)[0]=='claim':raise RuntimeError('尚有可领取任务，未发送匹配')
            if self.tokens and match_mode=='段位战斗':
                self.check_budget()
                value=self.read_tokens()
                if value is None or token_baseline is None or value!=token_baseline or value<=0:
                    raise RuntimeError('段位匹配前战令未知、为0或已变化，未发送匹配')
            state=self.a.panel()
            return state['controls']['ranked_battle' if match_mode=='段位战斗' else 'casual_battle']
        self.act('匹配'+match_mode,chosen)
        seconds=self.f.cfg.get('battleSeconds',900);deadline=self.a.now()+seconds;auto_sent=False
        result=None
        while self.a.now()<=deadline:
            self.check_budget()
            self.f.observe()
            if self.a.handle_popup(allow_victory=False,deadline=deadline):
                self.a.sleep(.2);continue
            result=self.settlement()
            if result:break
            controls=self.auto()
            if 'off' in controls and not auto_sent:
                def button():
                    if self.settlement():return None
                    return self.auto().get('off')
                # Input is based on this fresh frame; never toggle it twice.
                self.f.observe();current=self.settlement()
                if current:result=current;break
                target=button()
                if target:
                    auto_sent=True;self.record('点击自动战斗一次')
                    self.f.click_item(target)
            self.f.checkpoint();self.a.sleep(.2)
        if not result:raise TimeoutError('竞技场匹配／战斗结算超时，不重发匹配或自动')
        expected=result['result']
        def confirm():
            current=self.settlement()
            if not current:return None
            if current['result']!=expected:raise RuntimeError('结算胜负在确定前变化')
            return current['button']
        self.act('结算确定（'+expected+'）',confirm,allow_victory=False)
        self.a.stable_panel();self.battles+=1
        self.record('已返回竞技场，先检查可领取奖励',result=expected,matchMode=match_mode,
                    battles=self.battles,battleLimit=self.battle_limit)
        return expected

    def run(self):
        original=self.f.checkpoint
        def checkpoint():
            self.a.checkpoint();self.check_budget()
        self.f.checkpoint=checkpoint
        self.folder.mkdir(parents=True,exist_ok=False)
        outcome='failed'
        try:
            board=self.stable()
            while True:
                self.check_budget()
                action,card=next_action(board)
                self.record('任务决策：'+action,board=board)
                if action=='claim':board=self.claim(board,card)
                elif self.battles>=self.battle_limit:
                    outcome='battle_limit_done'
                    self.f.arena_evidence=dict(board=board,battles=self.battles,
                        battleLimit=self.battle_limit,result=outcome)
                    self.record('已达战斗场数上限，可领取奖励已处理，停留竞技场')
                    return outcome
                else:
                    baseline=None;match_mode=self.mode
                    if self.tokens:
                        if not self.tokens.casual:
                            baseline=self.stable_tokens();self.tokens.observe(baseline)
                        match_mode=self.tokens.mode()
                    result=self.fight(board,match_mode,baseline)
                    if self.tokens and match_mode=='段位战斗':
                        after=self.stable_tokens();self.tokens.verify_result(baseline,result,after)
                        self.record('核对段位战令消耗',before=baseline,after=after,result=result)
                        if self.tokens.casual:self.record('战令归零，本次锁定休闲，不再返回段位')
                    board=self.stable()
        finally:
            self.f.checkpoint=original
            (self.folder/'report.json').write_text(json.dumps(dict(result=outcome,mode=self.mode,battles=self.battles,
                battleLimit=self.battle_limit,automaticLowering=False,
                popupEvents=self.a.popup_events,
                tokensRemainingLastVerified=self.tokens.remaining if self.tokens else None,
                casualLocked=self.tokens.casual if self.tokens else None,tokenReads=self.token_reads,
                events=self.events),ensure_ascii=False,indent=2),encoding='utf-8')
            if self.f.image is not None:self.f.window.save(self.f.image,self.folder/'last.png')


def run_daily(arena,mode):return ArenaDaily(arena,mode).run()
