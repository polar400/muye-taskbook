"""Additive wanted-task settings, using the application's existing widgets."""
from tkinter import ttk


def show_wanted_task(ui,mode):
    ui.task_hint.set('自动完成通缉；次数0、条目消失或主页连续10秒无自动寻路且稳定后继续。')
    ui.plan_summary_label.pack_forget()
    text=('苦无活动入口 → 日常活动 → 通缉任务 → 参与 → 自动完成 → 是。\n\n'
          '由游戏自动接取并完成后续任务。确认次数0或活动条目消失后关闭面板；自动完成后，若主界面连续10秒未出现“自动寻路中”，且无通缉提示、状态稳定，也会继续下一任务。')
    ttk.Label(ui.task_fields,text=text,wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(0,16))
    ttk.Label(ui.task_fields,text='运行方式：本地后台（免API）',wraplength=530).pack(anchor='w',pady=6)
    if mode=='advanced':
        ttk.Label(ui.task_fields,text='每个页面最多等待30秒；自动完成全部任务最多等待30分钟，暂停期间不计时。\n自动完成及“是”各点击一次；保留次数校验但不逐条显示递减。自动寻路重新出现、接任务、移动或弹窗会重置10秒计时。',
                  wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=8)
    ui.wrap_labels(ui.task_fields,max(100,ui.task_canvas.winfo_width()-8))
