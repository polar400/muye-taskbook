"""Arena stage one: navigate to the panel, inspect it, and stop before battle."""
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import ReadOnlyController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JTemplateMatch

ASSETS=ROOT/'resources/local/arena'


class ArenaTask:
    def __init__(self,flow):
        self.f=flow
        self.sent=set()
        self.clock=time.monotonic
        self.sleep=time.sleep
        self.paused=0
        self.original_checkpoint=flow.checkpoint
        self.matcher=None
        self.popup_events=[];self.pending_popup=None;self.popup_absent_frames=0
        self.popup_revision=0

    def checkpoint(self):
        start=self.clock()
        try:self.original_checkpoint()
        finally:self.paused+=self.clock()-start

    def now(self):return self.clock()-self.paused

    def matches(self,name,roi):
        image=self.f.image
        if image is None or image.shape!=(1015,1920,3):
            raise RuntimeError('竞技场需要校准后的1920×1015游戏截图')
        if self.matcher is None:
            self.resource=Resource()
            if not self.resource.post_image(ASSETS).wait().succeeded:
                raise RuntimeError('竞技场模板加载失败')
            self.controller=ReadOnlyController()
            self.controller.post_connection().wait()
            self.matcher=Tasker()
            self.matcher.bind(self.resource,self.controller)
        left,top,right,bottom=roi
        x,y=int(1920*left),int(1015*top)
        region=image[y:int(1015*bottom),x:int(1920*right)]
        result=[]
        self.controller.image=region
        detail=self.matcher.post_recognition('TemplateMatch',JTemplateMatch(
            template=[name+'.png'],threshold=[.9]),region).wait().get()
        if detail:
            for node in detail.nodes:
                if not node.recognition:continue
                for item in node.recognition.filtered_results:
                    bx,by,tw,th=list(item.box)
                    if not any(abs(x+bx-m['box'][0])<25 and abs(y+by-m['box'][1])<25 for m in result):
                        result.append(dict(box=[x+bx,y+by,tw,th],score=float(item.score),template=name))
        return result

    def button(self,name,roi):
        found=self.matches(name,roi)
        if len(found)>1:raise RuntimeError('竞技场定位不唯一：'+name)
        return found[0] if found else None

    def blocked(self):
        if self.popup():return True
        central=[m for m in self.f.items if 480<m['box'][0]<1440 and 200<m['box'][1]<810
                 and m.get('score',0)>=.8]
        return any(re.fullmatch(r'确定|确认|是|否|取消',m['text'].strip()) for m in central)

    def popup(self):
        """Only the two supplied arena dialogs; never a generic confirmation."""
        titles=[]
        for kind in ('trial','victory'):
            title=self.button('popups/'+kind+'_title',(.33,.1,.7,.28))
            if title:titles.append((kind,title))
        if len(titles)>1:raise RuntimeError('竞技场弹窗标题冲突，停止')
        if not titles:return None
        kind,title=titles[0]
        if any(m.get('score',0)>=.85 and 480<m['box'][0]<1440 and 200<m['box'][1]<810
               and re.search(r'元宝|点券|购买|支付|花费|消耗|扣除',m['text']) for m in self.f.items):
            raise RuntimeError('竞技场弹窗出现消耗提示，停止')
        target=self.button('popups/'+('trial_skip' if kind=='trial' else 'victory_confirm'),(.4,.64,.7,.82))
        return dict(kind=kind,title=title,button=target)

    def remember_popup(self,popup):
        event=dict(kind=popup['kind'],button=popup['button'],status='sending',cleared=False)
        self.popup_events.append(event);self.pending_popup=event;self.popup_absent_frames=0
        return event

    def handle_popup(self,allow_victory=True,deadline=None):
        popup=self.popup()
        if self.pending_popup:
            if popup and popup['kind']==self.pending_popup['kind']:
                self.popup_absent_frames=0;return True  # Already sent; never replay.
            if popup is None:
                self.popup_absent_frames+=1
                if self.popup_absent_frames<2:return True
            self.pending_popup['cleared']=True;self.pending_popup=None;self.popup_absent_frames=0
        if not popup or (popup['kind']=='victory' and not allow_victory):return False
        if not popup['button']:return True
        # A pause or disappearing dialog must not reuse the previous target.
        self.checkpoint();self.f.observe();fresh=self.popup()
        if deadline is not None and self.now()>deadline:
            raise TimeoutError('竞技场弹窗发送前已超时；未发送点击')
        if not fresh or fresh['kind']!=popup['kind'] or not fresh['button']:return True
        event=self.remember_popup(fresh)
        self.f.log('竞技场：'+('新增试用忍者，点击蓝色跳过' if fresh['kind']=='trial' else '战斗胜利，点击确定'))
        self.f.click_item(fresh['button']);event['status']='sent'
        return True

    def home_icon(self):
        if self.blocked():return None
        # Recheck the home identity on the same fresh frame used for input.
        if not (self.f.ocr.match(self.f.image,'entry_survival')
                and self.f.ocr.match(self.f.image,'entry_ranked')):return None
        found=[]
        for name in ('home_entry_catalog','home_entry_user'):
            for match in self.matches(name,(.4,0,.85,.32)):
                if not any(abs(match['box'][0]-m['box'][0])<25
                           and abs(match['box'][1]-m['box'][1])<25 for m in found):found.append(match)
        if len(found)>1:raise RuntimeError('竞技场定位不唯一：主界面竞技场图标')
        return found[0] if found else None

    def panel(self):
        if self.blocked():return None
        # Four independent regions; a home icon alone is insufficient.
        names=(('ranked_battle',(.19,.84,.37,.98)),('casual_battle',(.36,.84,.52,.98)),
               ('score_label',(.03,.25,.19,.33)),('task_header',(.04,.34,.19,.43)))
        controls={name:self.button(name,roi) for name,roi in names}
        if not all(controls.values()):return None
        words=[dict(m) for m in self.f.items if m.get('score',0)>=.8
               and 80<m['box'][0]<335 and 340<m['box'][1]<790]
        return dict(page='arena',modes=['段位战斗','休闲战斗'],controls=controls,
                    leftTaskWords=words,taskActionsEnabled=False)

    def wait(self,label,reader,seconds=30,allow_victory=True):
        self.f.emit('node','竞技场 · '+label,id='arena',node=label,status='running')
        deadline=self.now()+seconds
        while True:
            self.checkpoint()
            self.f.observe()
            if self.now()>deadline:raise TimeoutError('竞技场等待超时：'+label+'；未重复发送点击')
            if self.handle_popup(allow_victory,deadline=deadline):
                self.popup_revision+=1
                self.sleep(.2);continue
            result=reader()
            if result is not None and result is not False:return result
            self.sleep(.2)

    def click(self,label,reader,allow_victory=True):
        if label in self.sent:raise RuntimeError('竞技场拒绝重复输入：'+label)
        target=self.wait(label,reader,allow_victory=allow_victory)
        self.sent.add(label)
        popup=self.popup() if not allow_victory else None
        event=self.remember_popup(popup) if popup and popup['kind']=='victory' else None
        self.f.log('竞技场：'+label+'，发送一次后台点击')
        self.f.click_item(target)
        if event:event['status']='sent'

    def stable_panel(self):
        stable=0;revision=self.popup_revision
        def read():
            nonlocal stable,revision
            if revision!=self.popup_revision:stable=0;revision=self.popup_revision
            state=self.panel()
            stable=stable+1 if state else 0
            return state if stable>=2 else None
        return self.wait('确认竞技场界面（段位／休闲／左侧任务）',read)

    def run(self):
        self.f.checkpoint=self.checkpoint
        try:
            self.wait('检查竞技场入口弹窗',lambda:True)
            if not self.panel():
                if self.blocked():raise RuntimeError('竞技场入口存在待处理弹窗，停止')
                self.f.home()
                self.click('主界面竞技场图标',self.home_icon)
            state=self.stable_panel()
            self.f.arena_evidence=dict(state,popupEvents=self.popup_events)
            self.f.log('竞技场界面已打开：段位战斗、休闲战斗、左侧任务区域已确认；本阶段停留在此界面')
            return 'opened'
        finally:self.f.checkpoint=self.original_checkpoint


def validate_arena_config(cfg):
    if 'arena' not in cfg.get('tasks',[]):return
    if cfg.get('backend','本地后台（免API）')!='本地后台（免API）':
        raise ValueError('竞技场目前使用本地后台（免API）')
    if cfg['tasks'][-1]!='arena' or cfg['tasks'].count('arena')!=1:
        raise ValueError('竞技场结束后停留在界面，请将它放在本次队列最后')
    if 'arenaMode' in cfg:
        if cfg['arenaMode'] not in ('段位战斗','排位战斗','休闲战斗','日常模式'):raise ValueError('请选择段位、休闲或日常模式')
        from arena_settings import battle_limit
        battle_limit(cfg)
        seconds=cfg.get('battleSeconds',900)
        if isinstance(seconds,bool) or not isinstance(seconds,int) or not 30<=seconds<=3600:
            raise ValueError('竞技场单场超时应为30至3600秒')


def run_arena(flow):
    validate_arena_config(flow.cfg)
    arena=ArenaTask(flow)
    result=arena.run()
    if 'arenaMode' not in flow.cfg:return result  # Explicit entry-only diagnostics.
    from arena_daily import run_daily
    mode='段位战斗' if flow.cfg['arenaMode']=='排位战斗' else flow.cfg['arenaMode']
    return run_daily(arena,mode)
