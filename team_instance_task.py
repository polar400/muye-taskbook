"""Isolated entry prototype. Never starts a dungeon or claims an unverified arrival."""
from pathlib import Path
import re
import time
from adapters.local_ocr import ReadOnlyController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JTemplateMatch

ASSETS = Path(__file__).resolve().parent / 'resources/local/team_instance'

class TeamInstanceTask:
    def __init__(self, flow, timeout=30):
        self.f = flow
        self.timeout = timeout
        self.sent = set()
        self.matcher = None
        self.clock = time.monotonic
        self.sleep = time.sleep

    def template(self, names, roi):
        if self.f.image is None or self.f.image.shape != (1015,1920,3):
            raise RuntimeError('组队副本需要1920×1015校准截图')
        if self.matcher is None:
            self.resource = Resource()
            if not self.resource.post_image(ASSETS).wait().succeeded:
                raise RuntimeError('组队副本模板加载失败')
            self.controller = ReadOnlyController()
            self.controller.post_connection().wait()
            self.matcher = Tasker()
            self.matcher.bind(self.resource, self.controller)
        x,y,r,b = roi
        image = self.f.image[y:b,x:r].copy()
        self.controller.image = image
        results = []
        for name in names:
            detail = self.matcher.post_recognition('TemplateMatch', JTemplateMatch(
                template=[name+'.png'],threshold=[.9]),image).wait().get()
            if detail:
                for node in detail.nodes:
                    if not node.recognition:
                        continue
                    for item in node.recognition.filtered_results:
                        bx,by,w,h = list(item.box)
                        box = [x+bx,y+by,w,h]
                        if not any(abs(box[0]-m['box'][0])<25 and abs(box[1]-m['box'][1])<25 for m in results):
                            results.append(dict(box=box, score=float(item.score), template=name))
        if len(results)>1:
            raise RuntimeError('组队副本定位不唯一：'+str(names))
        return results[0] if results else None

    def words(self, pattern, roi):
        x,y,r,b = roi
        return [m for m in self.f.items if m.get('score',0)>=.8
                and x<=m['box'][0]<r and y<=m['box'][1]<b
                and re.fullmatch(pattern,re.sub(r'\s+','',m['text']))]

    def blocked(self):
        return bool(self.words(r'确定|确认|取消|购买|支付', (480,200,1440,810)))

    def limited(self):
        return None if self.blocked() else self.template(['limited_active'], (250,30,950,140))

    def row(self):
        return self.template(['team_row_blue','team_row_plain','team_row_yellow'], (260,180,470,720)) if self.limited() else None

    def selected(self):
        # The provided screenshot highlights the team row but still shows another
        # activity at right. Highlight alone must NEVER authorize Participate.
        return bool(self.row() and (self.template(['team_detail'],(1140,130,1540,210))
                    or len(self.words('组队副本',(1140,130,1540,210))) == 1))

    def participate(self):
        return self.template(['participate','participate_live'],(1200,650,1470,750)) if self.selected() else None

    def kunai(self):
        if self.blocked() or self.limited():
            return None
        if not (self.f.ocr.match(self.f.image,'entry_survival') and self.f.ocr.match(self.f.image,'entry_ranked')):
            return None
        return self.template(['kunai','kunai_live'],(0,100,270,400))

    def limited_tab(self):
        if self.blocked():
            return None
        # Tab geometry is authorized only inside the known activity panel.
        if not self.words('活动周历',(1350,50,1560,130)):
            return None
        found = self.words('限时活动',(480,40,710,130))
        return found[0] if len(found)==1 else None

    def wait(self, reader):
        deadline = self.clock()+self.timeout
        while True:
            start = self.clock()
            self.f.checkpoint()
            deadline += self.clock()-start
            self.f.observe()
            value = reader()
            if self.clock()>deadline:
                raise TimeoutError('组队副本等待超时；未重放点击')
            if value:
                return value
            self.sleep(.2)

    def click(self, label, reader):
        if label in self.sent:
            raise RuntimeError('组队副本拒绝重复点击：'+label)
        self.f.log('组队副本：等待'+label)
        try:
            target = self.wait(reader)
        except TimeoutError as error:
            raise TimeoutError('组队副本等待超时：'+label+'；未重放点击') from error
        if label in ('苦无入口','限时活动','组队副本条目','参加','全部副本','进入所选关卡','确认进入挑战'):
            guard=getattr(self,'entry_allowed',None)
            if guard:guard()
        if label=='进入所选关卡':
            begin=getattr(self,'before_challenge',None)
            if begin:begin()
        self.sent.add(label)
        self.f.log('组队副本：'+label)
        self.f.click_item(target)

    def home_visible(self):
        from team_instance_challenge import Challenge
        from team_instance_settlement import Settlement
        if self.blocked() or Settlement(self).title() or Challenge(self).panel() or self.limited():return False
        return bool(self.f.ocr.match(self.f.image,'entry_survival') and self.f.ocr.match(self.f.image,'entry_ranked'))

    def return_home(self):
        from team_instance_challenge import Challenge
        self.f.observe()
        if Challenge(self).panel():
            self.click('关闭组队副本',lambda:self.template(['dungeon_close'],(1500,40,1750,180)) if Challenge(self).panel() else None)
        stable=0
        def home():
            nonlocal stable
            stable=stable+1 if self.home_visible() else 0
            return stable>=2
        self.wait(home)

    def run(self):
        self.f.observe()
        from team_instance_settlement import Settlement
        settlement=Settlement(self)
        if settlement.title():return settlement.run()
        from team_instance_challenge import Challenge
        challenge=Challenge(self)
        if challenge.panel():
            return challenge.run(self.f.cfg['teamInstanceName'],self.f.cfg['teamInstanceDifficulty']) if self.f.cfg.get('teamInstanceName') else 'opened'
        self.open_panel()
        if self.f.cfg.get('teamInstanceName'):
            return challenge.run(self.f.cfg['teamInstanceName'],self.f.cfg['teamInstanceDifficulty'])
        return 'opened'

    def open_panel(self):
        from team_instance_challenge import Challenge
        challenge=Challenge(self)
        self.f.observe()
        if challenge.panel():return
        if not self.limited():
            if not self.limited_tab():
                self.click('苦无入口',self.kunai)
            self.f.observe()
            if not self.limited():
                self.click('限时活动',self.limited_tab)
        self.wait(self.limited)
        self.click('组队副本条目',self.row)
        self.click('参加',self.participate)
        self.wait(challenge.panel)

def run_team_instance(flow):
    from team_instance_daily import is_open,run_daily
    if flow.cfg.get('teamInstanceName'):return run_daily(flow)
    if not is_open():
        flow.log('组队副本未开放：北京时间08:00—24:00，当前跳过')
        return 'closed'
    task=TeamInstanceTask(flow)
    result=task.run()
    if result=='completed':task.return_home()
    return result

def validate_team_instance_config(cfg):
    from team_instance_challenge import LEVELS,DIFFICULTIES
    tasks = cfg.get('tasks',[])
    if 'team_instance' not in tasks:
        return
    from team_instance_daily import daily_limit
    daily_limit(cfg)
    if cfg.get('teamInstanceName') is not None:
        if cfg['teamInstanceName'] not in LEVELS or cfg.get('teamInstanceDifficulty') not in DIFFICULTIES:
            raise ValueError('请选择有效的组队副本名称与难度')
    if cfg.get('backend','本地后台（免API）') != '本地后台（免API）':
        raise ValueError('组队副本目前仅支持本地后台（免API）')
    if tasks.count('team_instance') != 1:
        raise ValueError('组队副本不能重复加入任务队列')
    if not cfg.get('teamInstanceName') and tasks[-1] != 'team_instance':
        raise ValueError('请选择组队副本关卡与难度；仅打开界面模式须放在队列最后')
