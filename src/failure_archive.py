"""Durable per-task incidents, conservative matching and legacy log import."""
from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import traceback
import uuid

LABELS={'startup':'启动校准','worker':'运行环境','diagnostic':'后台连接检查',
        'survival':'生存演习','strong':'强者降临','hosting':'游戏内托管','ranked':'排位战','escort':'押镖（接取）'}
BEIJING=timezone(timedelta(hours=8))
LABELS.update({'wanted':'通缉任务'})

def now():return datetime.now(BEIJING).isoformat(timespec='seconds')
def run_id():return datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:12]
def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]

def clean(text,secrets=()):
    text=str(text)
    for secret in secrets:
        if secret:text=text.replace(secret,'[已隐藏]')
    text=re.sub(r'(?i)(bearer\s+)[\w.\-]+',r'\1[已隐藏]',text)
    return re.sub(r'(?i)((?:api[_ -]?key|password|access[_ -]?token)\s*["\']?\s*[:=]\s*["\']?)[^\s,"\'}]+',r'\1[已隐藏]',text)

def classify(message,step=''):
    # The evidence note describes preservation, not a screenshot malfunction.
    symptom=re.sub(r'已(?:保留|保存)最后截图','',message)
    rules=[('count_progress','检查次数减少',r'次数未减少'),
           # A combined read-stage label may mention remaining count; classify
           # a specific power error before matching that enclosing stage label.
           ('own_power','读取我方战力',r'我方战力'),('opponent_power','读取对手战力',r'对手战力'),
           ('remaining_count','读取剩余次数',r'剩余次数|剩余.*次数.*(?:识别|读取|可靠)'),
           ('panel_close','关闭游戏面板',r'关闭图标|面板关闭'),('automatic_battle','设置自动与倍速',r'自动.*(?:按钮|开启)|二倍速|倍速.*按钮'),
           ('payment_guard','核对付费提示',r'付费|购买|支付|元宝|点券'),
           ('capture','获取游戏画面',r'截图|黑屏|最小化'),
           ('timeout','等待界面状态',r'超时')]
    for category,canonical,pattern in rules:
        if re.search(pattern,symptom):return category,canonical
    category='recognition' if re.search(r'识别|定位|读取',message) else 'runtime'
    stable=re.sub(r'\d+(?:\.\d+)?','#',re.sub(r'\s+','',step or message))
    return category,stable or '未知'

def exception_details(error,secrets=()):
    frames=traceback.extract_tb(error.__traceback__)
    source={'file':frames[-1].filename,'line':frames[-1].lineno,'function':frames[-1].name} if frames else None
    return {'source':source,'exceptionType':type(error).__name__,
            'traceback':clean(''.join(traceback.format_exception(error)),secrets)}

def atomic_json(path,data):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)
    finally:
        if temp.exists():temp.unlink()

def md(text):return str(text).replace('|','\\|').replace('\n',' / ')

class FailureArchive:
    def __init__(self,root):
        self.root=Path(root).resolve();self.folder=self.root/'出错任务'
        self.folder.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            if not (self.folder/'统计.json').exists():
                db.execute('BEGIN IMMEDIATE')
                self.export([json.loads(row[0]) for row in db.execute('SELECT payload FROM incidents ORDER BY rowid')])

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.folder/'记录.sqlite3',timeout=10)
        try:
            with db:yield db
        finally:db.close()

    def records(self):
        with self.connect() as db:return [json.loads(row[0]) for row in db.execute('SELECT payload FROM incidents ORDER BY rowid')]

    def refresh(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.export([json.loads(row[0]) for row in db.execute('SELECT payload FROM incidents ORDER BY rowid')])

    def review(self,task_id):
        records=[r for r in self.records() if r['taskId']==task_id and r['status']=='error']
        if not records:return '历史复盘：'+LABELS.get(task_id,task_id)+'暂无错误记录'
        groups=Counter((r['category'],r['step']) for r in records)
        types='；'.join(f'{step} {count}次' for (_,step),count in groups.items())
        return f'历史复盘：{LABELS.get(task_id,task_id)}已有{len(records)}次错误，{types}；仅提示历史，不自动重试'

    def record(self,record,screenshot=None):
        record=dict(record)
        record['taskId']=record['taskId'] if record['taskId'] in LABELS else 'worker'
        record['taskName']=LABELS[record['taskId']]
        record.setdefault('occurredAt',now());record.setdefault('source',None)
        record.setdefault('traceback',None);record.setdefault('lastStep','未知')
        record.setdefault('context',[]);record.setdefault('backend','未知')
        category,step=classify(record['error'],record.get('step',''))
        record['category']=category if record['status']=='error' else 'manual_stop'
        record['step']=step if record['status']=='error' else (record.get('step') or '人工停止')
        record['signature']=digest('|'.join((record['taskId'],record['step'],record['category'])))
        task_folder=self.folder/record['taskName'];task_folder.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT payload FROM incidents WHERE id=?',(record['id'],)).fetchone()
            if existing:return json.loads(existing[0])
            records=[json.loads(row[0]) for row in db.execute('SELECT payload FROM incidents ORDER BY rowid')]
            similar=[r for r in records if r['status']=='error' and record['status']=='error' and r['signature']==record['signature']]
            record['similarIds']=[r['id'] for r in similar]
            record['similarCount']=len(similar)
            record['screenshot']=None
            if screenshot:
                source=Path(screenshot).resolve()
                if source.is_relative_to(self.root) and source.is_file():
                    evidence=task_folder/'证据';evidence.mkdir(exist_ok=True)
                    destination=evidence/(record['id']+source.suffix)
                    shutil.copyfile(source,destination)
                    record['screenshot']=str(destination.relative_to(self.root))
            db.execute('INSERT INTO incidents VALUES (?,?)',(record['id'],json.dumps(record,ensure_ascii=False)))
            records.append(record)
            self.export(records)
        return record

    def export(self,records):
        tasks=[]
        for task_id,label in LABELS.items():
            entries=[r for r in records if r['taskId']==task_id]
            if not entries:continue
            errors=[r for r in entries if r['status']=='error']
            groups={}
            for error in errors:
                group=groups.setdefault(error['signature'],{'category':error['category'],'step':error['step'],'count':0,'first':error['occurredAt'],'last':error['occurredAt'],'ids':[]})
                group['count']+=1;group['last']=error['occurredAt'];group['ids'].append(error['id'])
            task={'taskId':task_id,'taskName':label,'errorCount':len(errors),
                  'interruptionCount':len(entries)-len(errors),'types':list(groups.values())}
            tasks.append(task)
            folder=self.folder/label;details=folder/'记录';details.mkdir(parents=True,exist_ok=True)
            lines=[f'# {label} — 出错任务统计','',f'程序错误 **{len(errors)} 次**；人工中断 **{len(entries)-len(errors)} 次**（不计入错误）。',
                   '', '同类型仅为“疑似同类”，不表示根因已确认；旧日志缺失的代码位置和截图记为未知。','',
                   '| 时间（北京时间） | 状态 | 出错步骤 | 错误内容 | 同类历史 | 详情 |','| --- | --- | --- | --- | --- | --- |']
            for entry in entries:
                atomic_json(details/(entry['id']+'.json'),entry)
                state='出错' if entry['status']=='error' else '人工中断'
                source=entry.get('source')
                location=f"{source.get('file','未知')}:{source.get('line','未知')}（{source.get('function','未知函数')}）" if source else '未知（未保留代码位置）'
                report=[f'# {label} — {state}记录','',f"时间：{entry['occurredAt']}（北京时间）",f"运行编号：{entry['runId']}",
                        f"出错步骤：{entry['step']}",f"最后执行日志：{entry['lastStep']}",f'代码位置：{location}',
                        f"疑似同类历史：{entry['similarCount']}次（未确认根因相同）",'', '## 错误内容','',entry['error'],'',
                        '## 证据','',entry.get('evidenceNote','未知')]
                if entry.get('logOrigin'):report.append(f"原日志：{entry['logOrigin']['file']}，第{entry['logOrigin']['line']}行")
                if entry.get('screenshot'):
                    image_path=(self.root/entry['screenshot']).as_posix()
                    report.extend(['',f'![最后捕获画面](<{image_path}>)'])
                else:report.append('截图：未知')
                report.extend(['','## 异常堆栈','', '````text',entry.get('traceback') or '未知（历史日志或退出事件没有堆栈）','````','',
                               '## 相关日志','', '````text'])
                report.extend(f"[{item['at']}] {item['message']}" for item in entry['context'])
                report.extend(['````','',f"[机器可读记录]({entry['id']}.json)"])
                (details/(entry['id']+'.md')).write_text('\n'.join(report)+'\n',encoding='utf-8')
                lines.append(f"| {entry['occurredAt']} | {state} | {md(entry['step'])} | {md(entry['error'])} | {entry['similarCount']}次 | [记录](记录/{entry['id']}.md) |")
            (folder/'任务统计.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        summary={'version':1,'updatedAt':now(),'errorCount':sum(t['errorCount'] for t in tasks),
                 'interruptionCount':sum(t['interruptionCount'] for t in tasks),'tasks':tasks}
        atomic_json(self.folder/'统计.json',summary)
        lines=['# 出错任务','', '按任务统计程序错误；人工停止单独记录。运行记录仅显示本次过程；此处独立保存最近15日的故障资料。','',
               '| 任务 | 程序错误 | 人工中断 | 疑似错误类型 |','| --- | --- | --- | --- |']
        for task in tasks:
            label=task['taskName'];lines.append(f"| [{label}]({label}/任务统计.md) | {task['errorCount']} | {task['interruptionCount']} | {len(task['types'])} |")
        (self.folder/'汇总.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

class RunFailureTracker:
    def __init__(self,root,run,backend='未知',secrets=()):
        self.archive=FailureArchive(root);self.run=run if re.fullmatch(r'[\w-]+',run) else digest(run);self.backend=backend;self.secrets=secrets
        self.task_id='worker';self.last_step='未知';self.context=deque(maxlen=80)
        self.finished=False;self.failed=False;self.recorded=False

    def observe(self,event):
        kind=event['kind'];message=clean(event.get('message',''),self.secrets)
        if kind=='task':
            status=event.get('status')
            if status=='running':
                self.task_id=event.get('id','worker');self.context.clear();self.last_step='任务开始'
                self.finished=False;self.failed=False;self.recorded=False
            elif status=='failed':self.task_id=event.get('id',self.task_id);self.failed=True
            elif status in ('done','preview','accepted','skipped'):self.finished=True
        if kind in ('log','node') and message:self.last_step=message
        if message:self.context.append({'at':now(),'kind':kind,'message':message})

    def failure(self,message,manual=False,metadata=None):
        metadata=metadata or {}
        task_id=metadata.get('taskId') or ('worker' if self.finished and not self.failed else self.task_id)
        record={'id':digest(self.run+'|'+task_id),'runId':self.run,'taskId':task_id,
                'status':'interrupted' if manual else 'error','error':clean(message,self.secrets),
                'lastStep':self.last_step,'context':list(self.context),'backend':self.backend,
                'step':metadata.get('step',''),'source':metadata.get('source'),
                'exceptionType':metadata.get('exceptionType'),'traceback':clean(metadata.get('traceback',''),self.secrets) or None,
                'logOrigin':metadata.get('logOrigin'),'evidenceNote':metadata.get('evidenceNote','截图未知，未使用可能属于其他运行的旧截图')}
        result=self.archive.record(record,metadata.get('screenshot'))
        self.recorded=True
        return result

    def event(self,event,manual=False):
        self.observe(event)
        if event['kind'] in ('error','interrupted') and not self.recorded:return self.failure(event.get('message','未知错误'),manual or event.get('manual',False) or event.get('message')=='已停止' or event['kind']=='interrupted',event.get('failure'))
        if event['kind']=='exit' and not self.recorded:
            if manual:return self.failure('用户主动停止运行',True)
            if event.get('message')!='0' or self.failed:return self.failure('工作进程异常退出，退出码 '+str(event.get('message')),metadata={'step':self.last_step})
        return None

def import_log(root,path,secrets=()):
    path=Path(path);archive=FailureArchive(root);before=len(archive.records())
    labels={label:key for key,label in LABELS.items()};active=None;pending=False;run=None
    date=path.stem if re.fullmatch(r'\d{4}-\d{2}-\d{2}',path.stem) else None
    def save(message,line,manual=False):
        nonlocal active,pending
        if active is None:return
        archive.record({'id':digest((run or 'import|'+path.name+'|'+str(active['start']))+'|'+active['taskId']),
                        'runId':run or 'legacy-'+path.name+'-'+str(active['start']),
                        'taskId':active['taskId'],'status':'interrupted' if manual else 'error',
                        'error':clean(message,secrets),'occurredAt':active['lastTime'],
                        'lastStep':active['lastStep'],'context':active['context'][-80:],
                        'logOrigin':{'file':str(path.resolve()),'line':line},'evidenceNote':'历史日志未保留当时截图与代码堆栈，位置和截图未知'})
        active=None;pending=False
    for line_number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        match=re.match(r'^\[(\d{2}:\d{2}:\d{2})\] (.*)$',line)
        if not match:continue
        clock,message=match.groups();timestamp=f'{date}T{clock}+08:00' if date else '未知日期 '+clock
        if message.startswith('运行编号：'):
            if pending:save('任务未完成，错误详情缺失',line_number-1)
            active=None;run=message.split('：',1)[1];continue
        task=re.fullmatch(r'(.+?)：(后台)?运行中',message)
        if task and task[1] in labels:
            if pending:save('任务未完成，错误详情缺失',line_number-1)
            active={'taskId':labels[task[1]],'start':line_number,'lastTime':timestamp,'lastStep':'任务开始','context':[]}
            pending=False
        if active:
            active['lastTime']=timestamp
            active['context'].append({'at':timestamp,'kind':'legacy','message':clean(message,secrets)})
            if re.match(r'^'+re.escape(LABELS[active['taskId']])+r'：(?:未完成|失败)',message):pending=True;continue
            if message in ('已停止','执行已停止','用户主动停止运行'):save(message,line_number,True);continue
            if pending:save(message,line_number);continue
            if message==LABELS[active['taskId']]+'：完成':active=None;continue
            active['lastStep']=clean(message,secrets)
        if message=='设置已保存':run=None
    if pending:save('任务未完成，日志终止且错误详情缺失',line_number)
    return len(archive.records())-before
