"""Mission Desk Tk presentation. All game execution stays in App and its workers."""
from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

PAPER = '#f4f1ea'
SURFACE = '#fcfbf7'
SIDEBAR = '#eceee4'
INK = '#292d28'
MUTED = '#5e6b52'
LINE = '#cbd1bf'
ACCENT = '#ae4428'
DARK = '#2b302a'
LIGHT = '#edf1e3'
SANS = 'Microsoft YaHei UI'
SERIF = 'SimSun'


def queue_resize(ui, key, callback):
    """Latest-value, 50ms batches: sustained resizing still gets regular updates."""
    pending = getattr(ui, '_resize_pending', None)
    if pending is None:
        pending = ui._resize_pending = {}
    if key in pending:
        pending[key][1] = callback
        return
    def flush():
        _, latest = pending.pop(key)
        latest()
    pending[key] = [ui.after(50, flush), callback]


def bind_width(ui, widget, callback):
    last_width = None
    def changed(event):
        nonlocal last_width
        if event.widget is not widget or event.width == last_width:
            return
        last_width = event.width
        queue_resize(ui, str(widget), lambda: callback(last_width))
    widget.bind('<Configure>', changed)


def update_scrollregion(ui):
    region = ui.task_canvas.bbox('all')
    old = tuple(map(int, ui.task_canvas.cget('scrollregion').split()))
    if region is not None and tuple(region) != old:
        ui.task_canvas.configure(scrollregion=region)


def configure_styles(ui):
    style = ttk.Style(ui)
    style.theme_use('clam')
    style.configure('.', font=(SANS, 10), background=PAPER, foreground=INK)
    style.configure('TFrame', background=PAPER)
    style.configure('TLabel', background=PAPER, foreground=INK)
    style.configure('TButton', padding=(10, 6), background=SURFACE, bordercolor=LINE,
                    lightcolor=SURFACE, darkcolor=SURFACE, relief='flat')
    style.map('TButton', background=[('active', '#e6eadc')], foreground=[('disabled', '#858d7c')])
    style.configure('Primary.TButton', background=ACCENT, foreground='#fffaf0',
                    bordercolor=ACCENT, padding=(18, 9))
    style.map('Primary.TButton', background=[('disabled', '#ccb5a3'), ('active', '#92371f')],
              foreground=[('disabled', '#f7f3e9')])
    style.configure('TCheckbutton', background=PAPER, padding=2)
    style.map('TCheckbutton', background=[('active', PAPER)])
    style.configure('Row.TCheckbutton', background='#eeeee5', font=(SANS, 10), padding=2)
    style.map('Row.TCheckbutton', background=[('active', '#eeeee5')])
    style.configure('ActiveRow.TCheckbutton', background=SURFACE, font=(SANS, 10), padding=2)
    style.map('ActiveRow.TCheckbutton', background=[('active', SURFACE)])
    ui.check_off = tk.PhotoImage(width=16, height=16)
    ui.check_on = tk.PhotoImage(width=16, height=16)
    ui.check_off.put('#a9b29a', to=(0, 0, 16, 16))
    ui.check_off.put(SURFACE, to=(1, 1, 15, 15))
    ui.check_on.put(INK, to=(0, 0, 16, 16))
    for x, y in ((3, 7), (4, 8), (5, 9), (6, 10), (7, 9), (8, 8), (9, 7), (10, 6), (11, 5)):
        ui.check_on.put('#fffaf0', to=(x, y, x + 2, y + 2))
    style.element_create('MissionCheck.indicator', 'image', ui.check_off, ('selected', ui.check_on))
    layout = [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
        ('MissionCheck.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.label', {'side': 'left', 'sticky': 'nswe'})]})]
    for name in ('TCheckbutton', 'Row.TCheckbutton', 'ActiveRow.TCheckbutton'):
        style.layout(name, layout)
    style.configure('TCombobox', padding=5, fieldbackground=SURFACE, arrowsize=14,
                    bordercolor=LINE)
    style.map('TCombobox', fieldbackground=[('readonly', SURFACE)])
    style.configure('TSpinbox', padding=5, fieldbackground=SURFACE, arrowsize=12,
                    bordercolor=LINE)
    style.configure('TEntry', padding=5, fieldbackground=SURFACE, bordercolor=LINE)
    style.configure('TNotebook', background=PAPER, borderwidth=0)
    style.layout('TNotebook.Tab', [])
    style.configure('TPanedwindow', background=PAPER)
    style.configure('Log.TFrame', background=DARK)
    style.configure('Log.TLabel', background=DARK, foreground=LIGHT)
    style.configure('Log.TButton', background='#394333', foreground=LIGHT,
                    bordercolor='#647357', padding=(8, 5), font=(SANS, 9))
    style.map('Log.TButton', background=[('active', '#4b5b40')])
    style.configure('Log.TCheckbutton', background=DARK, foreground=LIGHT,
                    font=(SANS, 9), padding=2)
    style.map('Log.TCheckbutton', background=[('active', DARK)])


def section(parent, numeral, title):
    heading = ttk.Frame(parent)
    heading.pack(fill='x', pady=(0, 10))
    ttk.Label(heading, text=numeral, foreground=MUTED, font=(SERIF, 10)).pack(side='left', padx=(0, 8))
    ttk.Label(heading, text=title, font=(SERIF, 15, 'bold')).pack(side='left')
    ttk.Separator(parent).pack(fill='x', pady=(0, 8))
    return heading


def update_navigation(ui):
    selected = ui.notebook.select()
    for panel, button, line in ui.nav_buttons:
        active = str(panel) == selected
        button.configure(bg=INK if active else SIDEBAR,
                         fg='#faf7ed' if active else MUTED,
                         activebackground=INK if active else '#e0e5d6',
                         activeforeground='#faf7ed' if active else INK)
        line.configure(bg=ACCENT if active else SIDEBAR)


def update_task_focus(ui):
    for key, row in ui.task_rows.items():
        active = key == ui.selected.get()
        color = SURFACE if active else '#eeeee5'
        row.configure(bg=color, highlightbackground='#a9b798' if active else PAPER)
        ui.task_handles[key].configure(bg=color, highlightbackground=color)
        ui.task_checks[key].configure(style='ActiveRow.TCheckbutton' if active else 'Row.TCheckbutton')
        ui.gears[key].configure(bg=color, activebackground=color,
                               text='编辑中' if active else '参数')
        ui.task_state_labels[key].configure(bg=color)


def update_summary(ui, *_):
    selected = [key for key in ui.task_order if ui.selection[key].get()]
    ui.selection_summary.set(f'{len(selected):02d} / {len(ui.task_order):02d} 已选')
    terminal = {'完成', '已跳过', '已接取，待交付', '预览完成', '未完成', '失败', '已停止'}
    returned = sum(ui.statuses[key].get() in terminal for key in selected)
    ui.queue_summary.set(f'{returned:02d} / {len(selected):02d}')
    state = ui.status.get()
    ui.run_dot.configure(fg=ACCENT if any(word in state for word in ('失败', '停止', '异常')) else '#526b47')
    ui.backend_caption.set('运行方式 / ' + ui.backend.get())
    ui.preview_caption.set('流程预览 · 不操作游戏' if ui.preview.get() else '真实任务 · 开始前请确认游戏窗口')


def build_log_view(ui, parent, title, compact=False):
    shell = ttk.Frame(parent, style='Log.TFrame', padding=14 if compact else 22)
    shell.pack(fill='both', expand=True)
    heading = ttk.Frame(shell, style='Log.TFrame')
    heading.pack(fill='x', pady=(0, 13))
    ttk.Label(heading, text='叁  运行记录' if compact else title, style='Log.TLabel',
              font=(SERIF, 15 if compact else 19)).pack(side='left')
    ttk.Label(heading, text='本地事件', style='Log.TLabel', foreground='#bdcdae',
              font=(SANS, 8)).pack(side='right')
    ttk.Label(shell, textvariable=ui.status, style='Log.TLabel', foreground='#c4d1b6',
              wraplength=240, font=(SANS, 9)).pack(anchor='w', fill='x', pady=(0, 8))
    ttk.Label(shell, textvariable=ui.step_status, style='Log.TLabel', wraplength=240,
              font=(SANS, 10)).pack(anchor='w', fill='x', pady=(0, 12))
    toolbar = ttk.Frame(shell, style='Log.TFrame')
    toolbar.pack(fill='x', pady=(0, 8))
    ttk.Checkbutton(toolbar, text='自动跟随', variable=ui.follow_logs,
                    style='Log.TCheckbutton').pack(side='left')
    ttk.Button(toolbar, text='日志目录', command=ui.open_logs,
               style='Log.TButton').pack(side='right')
    ttk.Button(shell, text='出错任务统计', command=ui.open_failures,
               style='Log.TButton').pack(anchor='e', pady=(0, 8))
    text = tk.Text(shell, width=1, height=1, font=(SANS, 10), wrap='word', bg=DARK,
                   fg=LIGHT, selectbackground='#637850', selectforeground='#ffffff',
                   insertbackground=LIGHT, relief='flat', bd=0, padx=2, pady=8,
                   state='disabled', highlightthickness=0)
    text.pack(fill='both', expand=True)
    ui.log_views.append(text)
    bind_width(ui, shell, lambda width: ui.wrap_labels(shell, max(100, width - 30)))
    return text


def build(ui, tasks):
    configure_styles(ui)
    ui.configure(bg=PAPER)
    ui.selection_summary = tk.StringVar()
    ui.queue_summary = tk.StringVar()
    ui.backend_caption = tk.StringVar()
    ui.preview_caption = tk.StringVar()
    ui.nav_buttons = []

    sidebar = tk.Frame(ui, width=174, bg=SIDEBAR, padx=14)
    sidebar.pack(side='left', fill='y')
    sidebar.pack_propagate(False)
    brand = tk.Frame(sidebar, bg=SIDEBAR)
    brand.pack(fill='x', pady=(26, 23))
    tk.Label(brand, text='忍', bg=INK, fg='#faf7ed', font=(SERIF, 23), padx=6).pack(anchor='w')
    tk.Label(brand, text='木叶任务簿', bg=SIDEBAR, fg=INK,
             font=(SERIF, 16, 'bold')).pack(anchor='w', pady=(9, 2))
    tk.Label(brand, text='NARUTO ONLINE', bg=SIDEBAR, fg=MUTED,
             font=('Arial', 7)).pack(anchor='w')
    tk.Frame(sidebar, height=1, bg=LINE).pack(fill='x', pady=(0, 18))
    tk.Label(sidebar, text='工作台 / WORKSPACE', bg=SIDEBAR, fg=MUTED,
             font=(SANS, 8)).pack(anchor='w', pady=(0, 12))

    main = ttk.Frame(ui)
    main.pack(side='left', fill='both', expand=True)
    top = ttk.Frame(main, padding=(16, 12))
    top.pack(fill='x')
    ttk.Label(top, text='火影忍者online  /  每日任务助手', font=(SANS, 10)).pack(side='left')
    ttk.Button(top, textvariable=ui.backend_caption,
               command=lambda: ui.notebook.select(ui.settings_panel)).pack(side='right')
    ttk.Separator(main).pack(fill='x')
    footer = ttk.Frame(main, padding=(12, 5))
    footer.pack(side='bottom', fill='x')
    ttk.Label(footer, text='本地后台：可遮挡，不能最小化 · 识别不清即停止',
              foreground=MUTED, font=(SANS, 8)).pack(side='left')
    ttk.Label(footer, text='木叶任务簿 / v0.2', foreground=MUTED,
              font=(SANS, 8)).pack(side='right')
    ui.notebook = ttk.Notebook(main)
    ui.notebook.pack(fill='both', expand=True)
    ui.task_panel = ttk.Frame(ui.notebook)
    ui.log_panel = ttk.Frame(ui.notebook, padding=16)
    ui.help_panel = ttk.Frame(ui.notebook, padding=24)
    ui.settings_panel = ttk.Frame(ui.notebook, padding=24)
    pages = ((ui.task_panel, '任务面板'), (ui.log_panel, '运行记录'),
             (ui.help_panel, '小工具'), (ui.settings_panel, '设置'))
    for index, (panel, label) in enumerate(pages, 1):
        ui.notebook.add(panel, text=label)
        item = tk.Frame(sidebar, bg=SIDEBAR)
        item.pack(fill='x', pady=4)
        line = tk.Frame(item, width=2, bg=SIDEBAR)
        line.pack(side='left', fill='y')
        button = tk.Button(item, text=f'{index:02d}  {label}', anchor='w', padx=9, pady=10,
                           bg=SIDEBAR, fg=MUTED, relief='flat', bd=0,
                           font=(SANS, 10), command=lambda page=panel: ui.notebook.select(page))
        button.pack(fill='x')
        ui.nav_buttons.append((panel, button, line))
    ui.notebook.bind('<<NotebookTabChanged>>', ui.update_nav)
    tk.Label(sidebar, text='日\n常\n有\n序', bg=SIDEBAR, fg='#79856a',
             font=(SERIF, 23)).pack(side='bottom', anchor='w', padx=9, pady=(15, 24))

    hero = ttk.Frame(ui.task_panel, padding=(16, 13, 16, 11))
    hero.pack(fill='x')
    date = datetime.date.today()
    ttk.Label(hero, text=f'{date:%m / %d}', foreground=ACCENT,
              font=('Georgia', 24)).pack(side='right', padx=4)
    ttk.Label(hero, text='DAILY MISSION DESK', foreground=MUTED, font=('Arial', 8)).pack(anchor='w')
    ttk.Label(hero, text='今日委托。', font=(SERIF, 27, 'bold')).pack(anchor='w', pady=(2, 0))

    command = tk.Frame(ui.task_panel, bg=SURFACE, highlightthickness=1,
                       highlightbackground=LINE, padx=14, pady=10)
    command.pack(fill='x', padx=12)
    accent = tk.Frame(command, width=3, bg=ACCENT)
    accent.place(x=-14, y=-10, relheight=1, height=20)
    controls = tk.Frame(command, bg=SURFACE)
    controls.pack(side='right')
    buttons = tk.Frame(controls, bg=SURFACE)
    buttons.pack(anchor='e')
    ui.pause_button = ttk.Button(buttons, text='暂停', state='disabled', command=ui.pause, width=5)
    ui.pause_button.pack(side='left', padx=(0, 6))
    ui.stop_button = ttk.Button(buttons, text='停止', state='disabled', command=ui.stop, width=5)
    ui.stop_button.pack(side='left', padx=(0, 8))
    ui.start_button = ttk.Button(buttons, text='开始执行', style='Primary.TButton', command=ui.start)
    ui.start_button.pack(side='left')
    ui.preview_button = ttk.Checkbutton(controls, text='流程预览（不操作游戏）', variable=ui.preview)
    ui.preview_button.pack(anchor='e', pady=(7, 0))
    summary = tk.Frame(command, bg=SURFACE, padx=18)
    summary.pack(side='right', fill='y')
    tk.Label(summary, textvariable=ui.queue_summary, bg=SURFACE, fg=INK,
             font=('Georgia', 17)).pack(pady=(0, 1))
    tk.Label(summary, text='流程已返回 / 已选', bg=SURFACE, fg=MUTED, font=(SANS, 8)).pack()
    current = tk.Frame(command, bg=SURFACE)
    current.pack(side='left', fill='both', expand=True)
    ui.run_dot = tk.Label(current, text='●', bg=SURFACE, fg='#526b47', font=(SANS, 8))
    ui.run_dot.pack(anchor='w')
    state = tk.Label(current, textvariable=ui.status, bg=SURFACE, fg=INK,
                     font=(SANS, 11, 'bold'), justify='left', anchor='w', wraplength=400)
    state.pack(fill='x')
    tk.Label(current, textvariable=ui.preview_caption, bg=SURFACE, fg=MUTED,
             font=(SANS, 8), anchor='w', justify='left', wraplength=400).pack(fill='x', pady=(3, 0))
    def wrap_status(width):
        width = max(100, width)
        if int(state.cget('wraplength')) != width:
            state.configure(wraplength=width)
    bind_width(ui, current, wrap_status)

    body = ttk.Frame(ui.task_panel, padding=(10, 17, 10, 8))
    body.pack(fill='both', expand=True)
    ui.panes = ttk.Panedwindow(body, orient='horizontal')
    ui.panes.pack(fill='both', expand=True)
    left = ttk.Frame(ui.panes, padding=(0, 0, 9, 0))
    right = ttk.Frame(ui.panes, padding=(10, 0, 10, 0))
    ui.daily_log_panel = ttk.Frame(ui.panes, padding=(10, 0, 0, 0))
    ui.panes.add(left, weight=29)
    ui.panes.add(right, weight=39)
    ui.panes.add(ui.daily_log_panel, weight=32)
    heading = section(left, '壹', '任务队列')
    ttk.Label(heading, textvariable=ui.selection_summary, foreground=MUTED,
              font=(SANS, 8)).pack(side='right')
    tools = ttk.Frame(left)
    tools.pack(fill='x', pady=(0, 8))
    ttk.Label(tools, text='拖动排序 · 右键调整', foreground=MUTED, font=(SANS, 8)).pack(side='left')
    ttk.Button(tools, text='全选', width=4, command=lambda: ui.select_all(True)).pack(side='right')
    ttk.Button(tools, text='清空', width=4, command=lambda: ui.select_all(False)).pack(side='right', padx=(0, 4))
    ui.task_list = ttk.Frame(left)
    ui.task_list.pack(fill='x')
    ui.gears, ui.task_rows, ui.task_handles = {}, {}, {}
    ui.task_checks, ui.task_state_labels = {}, {}
    for key in ui.task_order:
        row = tk.Frame(ui.task_list, bg='#eeeee5', highlightthickness=1,
                       highlightbackground=PAPER, padx=5, pady=4)
        row.pack(fill='x', pady=3)
        ui.task_rows[key] = row
        handle = tk.Canvas(row, width=18, height=26, bg='#eeeee5', highlightthickness=0,
                            takefocus=True, cursor='hand2')
        handle.pack(side='left', padx=(0, 3))
        for x in (6, 12):
            for y in (7, 13, 19):
                handle.create_oval(x-1, y-1, x+1, y+1, fill=MUTED, outline='')
        ui.task_handles[key] = handle
        handle.bind('<ButtonPress-1>', lambda event, task=key: ui.begin_task_drag(event, task))
        handle.bind('<B1-Motion>', ui.update_task_drag)
        handle.bind('<ButtonRelease-1>', ui.end_task_drag)
        handle.bind('<Escape>', lambda event: ui.cancel_task_drag())
        handle.bind('<Alt-Up>', lambda event, task=key: ui.move_task(task, -1))
        handle.bind('<Alt-Down>', lambda event, task=key: ui.move_task(task, 1))
        handle.bind('<Button-3>', lambda event, task=key: ui.task_order_menu(event, task))
        check = ttk.Checkbutton(row, text=dict(tasks)[key], variable=ui.selection[key], style='Row.TCheckbutton')
        check.pack(side='left')
        ui.task_checks[key] = check
        gear = tk.Button(row, text='参数', font=(SANS, 8), fg=MUTED, bg='#eeeee5',
                          activebackground=SURFACE, activeforeground=ACCENT, bd=0,
                          padx=3, pady=4, relief='flat', command=lambda task=key: ui.show_task(task))
        gear.pack(side='right')
        ui.gears[key] = gear
        status = tk.Label(row, textvariable=ui.statuses[key], bg='#eeeee5', fg=MUTED,
                          font=(SANS, 8), anchor='e')
        status.pack(anchor='e', side='right', padx=(3, 3))
        ui.task_state_labels[key] = status
    ui.task_drop_line = tk.Frame(ui.task_list, bg=ACCENT, height=2)
    ttk.Label(left, text='✓ 启动校准（本地后台自动）\n游戏区域 1920×1015', foreground=MUTED,
              font=(SANS, 8), wraplength=220).pack(anchor='w', pady=(12, 0))

    section(right, '贰', '任务参数')
    ui.task_title = ttk.Label(right, font=(SERIF, 17, 'bold'))
    ui.task_title.pack(anchor='w', pady=(6, 13))
    tabs = ttk.Frame(right)
    tabs.pack(fill='x', pady=(0, 13))
    ui.task_tab_buttons = {}
    for mode, label in (('common', '常规设置'), ('advanced', '高级设置')):
        frame = tk.Frame(tabs, bg=PAPER, highlightthickness=1, highlightbackground=LINE)
        frame.pack(side='left', fill='x', expand=True)
        button = tk.Button(frame, text=label, bg=PAPER, activebackground='#e6eadc',
                            relief='flat', bd=0, font=(SANS, 10), pady=6,
                            command=lambda kind=mode: ui.show_task(ui.selected.get(), kind))
        button.pack(fill='x')
        ui.task_tab_buttons[mode] = (frame, button)
    bottom = ttk.Frame(right)
    bottom.pack(side='bottom', fill='x', pady=(12, 0))
    actions = ttk.Frame(bottom)
    actions.pack(fill='x')
    ttk.Button(actions, text='保存设置', command=ui.save).pack(side='right')
    ui.plan_summary_label = ttk.Label(bottom, textvariable=ui.survival_summary,
                                      foreground=MUTED, font=(SANS, 9), wraplength=350)
    ui.task_hint = tk.StringVar()
    ttk.Label(bottom, textvariable=ui.task_hint, foreground=MUTED,
              font=(SANS, 8), wraplength=350).pack(fill='x', pady=(8, 0))
    ui.task_canvas = tk.Canvas(right, bg=PAPER, highlightthickness=0)
    ui.task_canvas.pack(fill='both', expand=True)
    ui.task_fields = ttk.Frame(ui.task_canvas)
    ui.task_field_window = ui.task_canvas.create_window(0, 0, window=ui.task_fields, anchor='nw')
    ui.task_fields.bind('<Configure>', lambda event: update_scrollregion(ui))
    bind_width(ui, ui.task_canvas, lambda width: ui.resize_task_fields(SimpleNamespace(width=width)))
    ui.bind('<MouseWheel>', ui.route_task_scroll, add='+')
    bind_width(ui, right, lambda width: ui.wrap_labels(right, max(100, width-20)))
    ui.log_text = ui.build_log_view(ui.daily_log_panel, '运行记录', compact=True)
    ui.panes.bind('<Configure>', ui.schedule_pane_layout)
    ui.panes.bind('<ButtonPress-1>', ui.begin_pane_resize, add='+')
    ui.panes.bind('<ButtonRelease-1>', ui.end_pane_resize, add='+')
    ui.build_log_view(ui.log_panel, '运行记录')

    ttk.Label(ui.settings_panel, text='连接与运行设置', font=(SERIF, 23, 'bold')).pack(anchor='w', pady=(0, 18))
    ui.window_combo = ui.field(ui.settings_panel, '游戏窗口', ui.window_choice, values=[])
    ttk.Button(ui.settings_panel, text='刷新游戏窗口', command=ui.refresh_windows).pack(anchor='w', pady=5)
    ui.field(ui.settings_panel, '运行方式', ui.backend, values=['本地后台（免API）', 'Midscene（前台）'])
    ttk.Button(ui.settings_panel, text='检查后台连接（不点击）',
               command=lambda: ui.start(diagnostic=True)).pack(anchor='w', pady=6)
    ui.field(ui.settings_panel, '单场战斗超时（秒）', ui.battle_seconds, spin=(30, 3600))
    ttk.Button(ui.settings_panel, text='Midscene前台模型设置（可选）', command=ui.model_settings).pack(anchor='w', pady=6)
    ttk.Label(ui.settings_panel, text='本地后台无需 API；游戏可被遮挡，不能最小化。\nMidscene 使用前台鼠标，通缉任务仅支持本地后台。',
              foreground=MUTED, wraplength=650).pack(anchor='w', pady=12)
    ttk.Button(ui.settings_panel, text='保存设置', command=ui.save).pack(anchor='w')
    from grocery_tool_ui import build_tools
    build_tools(ui, ui.help_panel)

    for variable in [*ui.selection.values(), *ui.statuses.values(), ui.status, ui.backend, ui.preview]:
        variable.trace_add('write', lambda *_: update_summary(ui))

    def responsive(event):
        if event.widget is not ui:
            return
        width = 112 if event.width<1120 else 174
        if int(sidebar.cget('width')) != width:
            sidebar.configure(width=width)
    ui.bind('<Configure>', responsive, add='+')
    ui.show_task('survival')
    update_summary(ui)
    update_navigation(ui)
