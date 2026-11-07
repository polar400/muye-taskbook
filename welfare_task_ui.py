"""Welfare settings within the existing daily-task UI."""
from tkinter import ttk


def show_welfare_task(ui, mode):
    ui.plan_summary_label.pack_forget()
    ui.task_hint.set('领取当前可领的每日福利与在线礼包，检查完后关闭福利大厅。')
    ttk.Label(ui.task_fields, text='每日福利', font=('Microsoft YaHei UI', 11)).pack(anchor='w', pady=(0, 6))
    ttk.Label(ui.task_fields, text='按月卡 → 大月卡 → 勋章每日礼包的顺序检查，再查看上忍、中忍、下忍的勋章礼包。',
              wraplength=530, justify='left', foreground='#667586').pack(anchor='w', pady=(0, 12))
    ttk.Label(ui.task_fields, text='在线礼包', font=('Microsoft YaHei UI', 11)).pack(anchor='w', pady=(0, 6))
    ttk.Label(ui.task_fields, text='从左到右领取当前可领礼包；检查完毕后点击右上角关闭，并确认返回主页。',
              wraplength=530, justify='left', foreground='#667586').pack(anchor='w', pady=(0, 12))
    ttk.Label(ui.task_fields, text='只点击可领取按钮；充值、购买、激活勋章、灰色按钮等非领取状态都跳到下一项，不等待在线时长。',
              wraplength=530, justify='left').pack(anchor='w', pady=6)
    ttk.Label(ui.task_fields, text='运行方式：本地后台（免API）。本任务无需额外参数。',
              wraplength=530, foreground='#667586').pack(anchor='w', pady=6)
    if mode == 'advanced':
        ttk.Label(ui.task_fields, text='福利页面确认后，没有可点击的领取按钮就继续下一项。领取点击不重发；按钮一直未变化或页面无法识别时停止。检查完关闭福利大厅，确认返回主页后继续后续任务。',
                  wraplength=530, justify='left', foreground='#667586').pack(anchor='w', pady=8)
    ui.wrap_labels(ui.task_fields, max(100, ui.task_canvas.winfo_width()-8))
