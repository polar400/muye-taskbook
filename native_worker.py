"""Native local worker: stdin pause/resume/stop, compatible APP_EVENT output."""
import ctypes
import json
from pathlib import Path
import sys
import threading
import time
import os
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from ranked_pipeline import run_ranked_pipeline
from arena_task import run_arena, validate_arena_config
from team_instance_task import run_team_instance, validate_team_instance_config
from welfare_task import run_welfare
from survival_plan import survival_plan
from failure_archive import RunFailureTracker, exception_details, run_id, clean
ROOT=Path(__file__).resolve().parent
paused=threading.Event();stopped=threading.Event()
tracker=None;window=None;flow=None

def emit(kind,message,**extra):
    event=dict(kind=kind,message=message,**extra)
    if tracker:
        tracker.observe(event)
    print('APP_EVENT '+json.dumps(event,ensure_ascii=False),flush=True)

def commands():
    for line in sys.stdin:
        line=line.strip()
        if line=='pause':paused.set()
        elif line=='resume':paused.clear()
        elif line=='stop':stopped.set()

def checkpoint():
    if stopped.is_set():raise RuntimeError('已停止')
    if paused.is_set():emit('paused','已暂停')
    while paused.is_set() and not stopped.is_set():time.sleep(.1)
    if stopped.is_set():raise RuntimeError('已停止')

def main():
    global tracker,window,flow
    # The worker runs separately from the GUI. Importing its helpers must not
    # change a caller's process DPI mode (including GUI regression tests).
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    cfg=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    tracker=RunFailureTracker(ROOT,cfg.get('runId') or run_id(),cfg.get('backend','本地后台（免API）'),(os.getenv('MIDSCENE_MODEL_API_KEY',''),))
    if cfg.get('diagnostic'):
        tracker.task_id='diagnostic'
    tasks={t['id']:t['label'] for t in json.loads((ROOT/'resources/tasks.json').read_text(encoding='utf-8'))['tasks']}
    for task in cfg['tasks']:
        if task not in tasks:raise RuntimeError('未知任务 '+task)
    if not cfg.get('diagnostic'):
        validate_arena_config(cfg)
        validate_team_instance_config(cfg)
    if 'survival' in cfg['tasks'] and not cfg.get('diagnostic'):survival_plan(cfg)
    if 'ranked' in cfg['tasks'] and not cfg.get('diagnostic'):
        from ranked_policy import ranked_options
        ranked_options(cfg)
    if cfg.get('preview'):
        emit('task','启动校准：流程预览，运行时统一游戏区域1920×1015',id='startup',status='preview')
        for task in cfg['tasks']:
            checkpoint();emit('task',tasks[task]+'：本地流程预览，未操作游戏',id=task,status='preview')
        emit('done','本地流程预览完成，未操作游戏');return
    window=BackgroundWindow(cfg['gameHwnd'])
    if cfg.get('diagnostic'):image=window.capture()
    else:
        checkpoint();emit('task','启动校准：运行中',id='startup',status='running')
        try:image=window.calibrate(checkpoint,lambda message:emit('log',message))
        except Exception:
            emit('task','启动校准：未完成，后续任务停止',id='startup',status='failed');raise
        emit('task','启动校准：完成',id='startup',status='done')
    path=ROOT/'verification/background-latest.png';window.save(image,path)
    ocr=LocalOCR()
    if cfg.get('diagnostic'):
        data=ocr.read(image)
        (ROOT/'verification/background-ocr.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        emit('log',f'后台连接成功，游戏区域 {image.shape[1]}×{image.shape[0]}；截图：{path}')
        emit('log','识别文字：'+' / '.join(x['text'] for x in data))
        emit('done','后台截图与本地OCR检查完成，未点击游戏');return
    flow=LocalFlows(window,ocr,cfg,checkpoint,emit)
    flow.team_hold_cancelled=lambda:paused.is_set() or stopped.is_set()
    for task in cfg['tasks']:
        checkpoint();emit('task',tasks[task]+'：后台运行中',id=task,status='running')
        try:
            result=run_welfare(flow) if task=='welfare' else run_team_instance(flow) if task=='team_instance' else run_arena(flow) if task=='arena' else run_ranked_pipeline(flow) if task=='ranked' else flow.run(task)
            if task=='welfare' and result!='completed':
                raise RuntimeError('福利大厅：领取与返回主页尚未确认，已停止后续任务')
            if task=='team_instance' and result not in ('opened','challenge_requested','completed','daily_completed','closed'):
                raise RuntimeError('组队副本：已发送参加，但目标界面尚未验证；已停止，请检查游戏画面')
        except Exception:
            emit('task',tasks[task]+'：未完成',id=task,status='failed');raise
        accepted=task=='escort' and result=='accepted'
        skipped=task=='ranked' and result=='skipped'
        if task=='welfare':
            emit('task','福利大厅：已检查每日福利与在线礼包，已确认返回主页',id=task,status='done')
            continue
        if task=='team_instance':
            if result=='closed':
                emit('task','组队副本：不在08:00—24:00开放时段，已停止追加或跳过',id=task,status='skipped')
                continue
            if result=='daily_completed':
                emit('task','组队副本：本次挑战已收尾（设置次数或剩余奖励上限），已确认回到主页',id=task,status='done')
                continue
            if result=='completed':
                emit('task','组队副本：上下各翻一张，已返回主页',id=task,status='done')
                continue
            emit('task','组队副本：已确认进入所选挑战，战斗结果未验证' if result=='challenge_requested' else '组队副本：界面已打开（仅入口）',id=task,status='accepted' if result=='challenge_requested' else 'done')
            continue
        emit('task',tasks[task]+('：竞技场界面已打开（本阶段目标）' if task=='arena' and result=='opened' else '：已接取，交付流程待补充' if accepted else '：次数为0，已跳过并返回主页' if skipped else '：完成'),id=task,status='accepted' if accepted else 'skipped' if skipped else 'done')
    emit('done','本次后台流程结束；押镖接取不代表交付完成')

def report_error(error):
    details=exception_details(error,tracker.secrets if tracker else ())
    if tracker:
        details['taskId']='worker' if tracker.finished and not tracker.failed else tracker.task_id
        if flow is not None and flow.image is not None:
            try:
                snapshot=ROOT/'verification'/('failure-'+tracker.run+'-'+tracker.task_id+'.png')
                window.save(flow.image,snapshot)
                details.update(screenshot=str(snapshot),evidenceNote='失败时保存本任务最后一次已捕获画面；不保证为异常发生的同一瞬间')
            except Exception as capture_error:
                details['evidenceNote']='截图保存失败：'+clean(str(capture_error),tracker.secrets)
        if tracker.task_id=='ranked' and getattr(flow,'ranked_number_evidence',None):
            try:
                from ranked_numbers import save_evidence
                evidence=save_evidence(ROOT/'verification','failure-'+tracker.run+'-ranked',
                                       flow.ranked_number_evidence,flow.ranked_number_crops)
                details['evidenceNote']=details.get('evidenceNote','')+'；最近一次数字读取诊断（不一定与最后截图同帧）：'+str(evidence)
                emit('log','排位数字识别诊断已保存：'+str(evidence))
            except Exception as evidence_error:
                emit('log','排位数字诊断保存失败：'+clean(str(evidence_error),tracker.secrets))
        try:tracker.failure(str(error),stopped.is_set(),details)
        except Exception as archive_error:emit('log','错误归档失败：'+clean(str(archive_error),tracker.secrets))
    emit('error',str(error),manual=stopped.is_set(),failure=details)

if __name__=='__main__':
    threading.Thread(target=commands,daemon=True).start()
    try:main()
    except Exception as e:
        report_error(e);sys.exit(1)
