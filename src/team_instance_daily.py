"""Per-run challenge budget, capped by the current game's reward counters."""
from datetime import datetime, timezone, timedelta

BEIJING=timezone(timedelta(hours=8))
def now_beijing():return datetime.now(BEIJING)
def is_open(now=None):return (now or now_beijing()).astimezone(BEIJING).hour>=8

def daily_limit(cfg):
    # Keep the persisted key for compatibility; its meaning is now per run.
    value=cfg.get('teamInstanceDailyCount',1)
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=5:
        raise ValueError('组队副本本次挑战次数须为1至5')
    return value

def battle_visible(flow):
    controls=flow.image[int(flow.image.shape[0]*.65):].copy()
    automatic=flow.ocr.match(controls,'auto_on')+flow.ocr.match(controls,'auto_off')
    speed=flow.ocr.match(controls,'speed1')+flow.ocr.match(controls,'speed2')
    return len(automatic)==1 and len(speed)==1

def run_daily(flow,clock=now_beijing,task_factory=None,quota_reader=None):
    from team_instance_task import TeamInstanceTask
    from team_instance_settlement import Settlement,finish_challenge
    from team_instance_rewards import read_rewards
    task_factory=task_factory or TeamInstanceTask
    quota_reader=quota_reader or read_rewards
    limit=daily_limit(flow.cfg);completed=0
    start=clock().astimezone(BEIJING)
    task=task_factory(flow)
    flow.observe()
    if Settlement(task).title():
        Settlement(task).run();completed=1
        flow.log('组队副本：接续结算，计入本次1场')
    elif battle_visible(flow):
        finish_challenge(task);completed=1
        flow.log('组队副本：接续战斗及结算，计入本次1场')
    while completed<limit:
        current=clock().astimezone(BEIJING)
        if current.date()!=start.date() or not is_open(current):
            if completed:task.return_home()
            flow.log('组队副本当前未开放；不再开启挑战')
            return 'closed'
        task=task_factory(flow)
        def entry_allowed():
            current=clock().astimezone(BEIJING)
            if current.date()!=start.date() or not is_open(current):
                raise RuntimeError('组队副本已关闭；未发送新的入口操作')
        task.entry_allowed=entry_allowed
        task.open_panel()
        rewards=quota_reader(task)
        flow.log(f'组队副本剩余奖励：本周{rewards[0]}，本日{rewards[1]}，友情组队{rewards[2]}')
        limit=min(limit,completed+rewards[0],completed+rewards[1])
        if completed>=limit:break
        flow.log(f'组队副本：本次已完成{completed}/{limit}，开始下一场')
        if task.run()!='completed':raise RuntimeError('未确认本场结算，停止后续挑战')
        completed+=1
        flow.log(f'组队副本：本次已完成{completed}/{limit}')
    task.return_home()
    return 'daily_completed'
