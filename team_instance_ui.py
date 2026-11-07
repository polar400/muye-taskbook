"""Team-instance entry settings, isolated from other task panels."""
from tkinter import ttk
from team_instance_challenge import LEVELS,DIFFICULTIES

def show_team_instance(ui,mode):
    ui.plan_summary_label.pack_forget()
    ui.task_hint.set('按所选关卡与难度挑战；达到本次设定次数后关闭副本窗口，确认回到主页。')
    text = ('木叶村主页 → 苦无图标 → 限时活动 → 组队副本 → 参加。\n\n'
            '开放时间：北京时间08:00—24:00。非开放时段跳过，不点击灰色入口。\n\n'
            '按本次次数挑战所选关卡，确认自动与二倍速；结算上下各翻一张。达到次数后点击副本右上角叉号退出并确认主页。\n\n'
            '请使用本地后台。完成后返回主页，继续队列中的下一项任务；如同时选择竞技场，请将竞技场放在最后。')
    if mode=='advanced':
        text += '\n\n每步最多等待30秒；识别不确定时停止，不重复点击参加。'
    ttk.Label(ui.task_fields,text=text,wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(0,16))
    ui.field(ui.task_fields,'关卡名称',ui.team_instance_name,values=list(LEVELS))
    ui.field(ui.task_fields,'关卡难度',ui.team_instance_difficulty,values=list(DIFFICULTIES))
    ui.field(ui.task_fields,'本次挑战次数',ui.team_instance_daily_count,spin=(1,5))
    ttk.Label(ui.task_fields,text='默认1次，最多5次。每次启动重新计数，以游戏本日／本周剩余奖励次数为上限；友情组队次数仅显示。重启时接续的战斗或结算计入本次1场。',wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(8,8))
    ui.wrap_labels(ui.task_fields,max(100,ui.task_canvas.winfo_width()-8))
