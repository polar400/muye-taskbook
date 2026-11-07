"""Arena mode and bounded battle settings."""
from tkinter import ttk


def show_arena_task(ui,mode):
    ui.task_hint.set('有奖励先领取；未满足条件交给人工；按所选模式和场数上限战斗。')
    ui.plan_summary_label.pack_forget()
    text=('木叶村主界面 → 竞技场图标 → 竞技场界面。\n\n'
          '有可领取的左侧任务奖励就领取；条件未满足时跳过，降低难度由人工处理。'
          '每场开启自动，胜败结算点击确定并返回后计为1场。'
          '达到上限后领取可领奖励，停留在竞技场。\n\n'
          + ('运行方式：本地后台（免API）。在小工具中独立运行，不加入每日任务队列。'
             if getattr(ui,'arena_standalone',False) else
             '运行方式：本地后台（免API）。请将竞技场放在本次队列最后。'))
    ttk.Label(ui.task_fields,text=text,wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(0,16))
    if mode=='common':
        ttk.Label(ui.task_fields,text='匹配模式').pack(anchor='w',pady=(0,6))
        for label,value in (('段位战斗（排位）','段位战斗'),('休闲战斗','休闲战斗'),
                            ('日常模式（战令用完转休闲）','日常模式')):
            ttk.Radiobutton(ui.task_fields,text=label,value=value,variable=ui.arena_mode).pack(anchor='w',pady=4)
        ui.field(ui.task_fields,'战斗场数上限',ui.arena_limit,spin=(1,100))
        ttk.Label(ui.task_fields,text='1—100场，默认3场。胜负均计数；三种模式共用上限，任务领完也继续至上限。',
                  wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(4,8))
        ttk.Label(ui.task_fields,text='日常模式：按实际剩余战令优先打段位，战令归零后锁定休闲；段位与休闲合计达到场数上限即停，即使还有战令也不追加。耗令阶段最多60分钟，暂停不计时。\n手动模式保持所选模式；日常模式战令未知或消耗异常时停止。',
                  wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(4,0))
    if mode=='advanced':
        ttk.Label(ui.task_fields,text='每个页面最多等待30秒，单场沿用战斗超时设置；暂停不计时。领取后必须确认任务变化。\n条件未满足不悬停、不降级；不调整阵容或倍速。识别未知、付费提示或输入结果不确定时停止，不重复匹配。',
                  wraplength=530,foreground='#667586').pack(anchor='w',pady=8)
    ui.wrap_labels(ui.task_fields,max(100,ui.task_canvas.winfo_width()-8))
