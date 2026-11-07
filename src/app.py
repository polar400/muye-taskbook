"""火影忍者online daily task desktop application. Python 3.10+, Windows."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import shutil
import sqlite3
import sys
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from survival_plan import GRADES, POINTS, DEFAULT_COUNTS, survival_plan, estimate
from failure_archive import FailureArchive, RunFailureTracker, run_id, clean, exception_details
from log_retention import maintain_logs, local_day
from wanted_task_ui import show_wanted_task
from welfare_task_ui import show_welfare_task
from arena_task import validate_arena_config
from team_instance_task import validate_team_instance_config
from team_instance_ui import show_team_instance
from arena_settings import parse_battle_limit

ROOT = Path(__file__).resolve().parents[1]
TASKS = [(task['id'], task['label']) for task in json.loads((ROOT/'resources/tasks.json').read_text(encoding='utf-8'))['tasks']]
BLUE = '#ae4428'

def game_windows():
    if os.name != 'nt':
        return []
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    result = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd): return True
        title = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, title, 512)
        if '火影忍者' not in title.value: return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = kernel.OpenProcess(0x1000, False, pid.value)
        if process:
            try:
                path = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(path))
                if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)) and Path(path.value).name.lower() == '360game.exe':
                    result.append((hwnd, title.value))
            finally: kernel.CloseHandle(process)
        return True
    user.EnumWindows(callback_type(visit), 0)
    return result

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('木叶任务簿 - 火影忍者online 每日任务助手 v0.2')
        self.geometry('1440x900')
        self.minsize(940, 680)
        self.configure(bg='white')
        self.events = queue.Queue()
        self.process = None
        self.running = False
        self.pending_pause = False
        self.paused = False
        self.stopping = False
        self.active_task = None
        self.failure_tracker = None
        self.windows = []
        self.selection = {key: tk.BooleanVar(value=True) for key, _ in TASKS}
        self.task_order = [key for key, _ in TASKS if key != 'arena']
        self.task_drag = None
        self.follow_logs = tk.BooleanVar(value=True)
        self.log_views = []
        self.pane_ratios = (0.29, 0.39, 0.32)
        self.layout_job = None
        self.resizing_sash = False
        self.statuses = {key: tk.StringVar(value='待运行') for key, _ in TASKS}
        self.statuses['startup']=tk.StringVar(value='待运行')
        self.selected = tk.StringVar(value='survival')
        self.status = tk.StringVar(value='就绪')
        self.step_status = tk.StringVar(value='当前步骤：待运行')
        self.difficulty = tk.StringVar(value='阿修罗级')
        self.reset = tk.BooleanVar(value=True)
        self.task_modes = {key: 'common' for key, _ in TASKS}
        self.survival_grades = {g: tk.BooleanVar(value=True) for g in GRADES}
        self.survival_counts = {g: tk.IntVar(value=DEFAULT_COUNTS[g]) for g in GRADES}
        self.survival_initial = tk.IntVar(value=60)
        self.survival_goal = tk.IntVar(value=220)
        self.survival_summary = tk.StringVar()
        self.tolerance = tk.IntVar(value=20)
        self.arena_mode = tk.StringVar(value='休闲战斗')
        self.team_instance_name = tk.StringVar(value='桥上的决战')
        self.team_instance_difficulty = tk.StringVar(value='简单')
        self.team_instance_daily_count = tk.IntVar(value=1)
        self.arena_limit = tk.StringVar(value='3')
        self.ranked_server = tk.StringVar(value='连服')
        self.ranked_all = tk.BooleanVar(value=True)
        self.ranked_count = tk.IntVar(value=1)
        self.battle_seconds = tk.IntVar(value=900)
        self.hosting_minutes = tk.IntVar(value=90)
        self.escort_refresh_limit = tk.IntVar(value=4)
        self.escort_grade = tk.StringVar(value='SS')
        self.preview = tk.BooleanVar(value=False)
        self.backend = tk.StringVar(value='本地后台（免API）')
        self.window_choice = tk.StringVar()
        self.display = tk.StringVar()
        self.model = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_NAME', ''))
        self.base_url = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_BASE_URL', ''))
        self.family = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_FAMILY', ''))
        self.api_key = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_API_KEY', ''))
        self.load()
        for var in [*self.survival_grades.values(), *self.survival_counts.values(), self.survival_initial, self.survival_goal]:
            var.trace_add('write', self.update_survival_summary)
        self.update_survival_summary()
        self.build()
        self.refresh_windows()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)

    def load(self):
        try:
            cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
            saved_order = cfg.get('taskOrder', cfg.get('tasks', []))
            if isinstance(saved_order, list):
                self.task_order = list(dict.fromkeys(key for key in saved_order if isinstance(key, str) and key in self.selection and key != 'arena'))
                self.task_order += [key for key, _ in TASKS if key != 'arena' and key not in self.task_order]
            self.backend.set(cfg.get('backend','本地后台（免API）'))
            if cfg.get('survivalGrades')==[] and 'survival' not in cfg.get('tasks',[]):
                grades,counts=[],None
            else:grades, counts = survival_plan(cfg)
            for g in GRADES:
                self.survival_grades[g].set(g in grades)
                self.survival_counts[g].set((counts or DEFAULT_COUNTS).get(g, DEFAULT_COUNTS[g]))
            self.survival_initial.set(cfg.get('survivalInitial', 60))
            self.survival_goal.set(cfg.get('survivalGoal', 220))
            self.arena_mode.set(cfg.get('arenaMode','休闲战斗'))
            self.team_instance_name.set(cfg.get('teamInstanceName','桥上的决战'))
            self.team_instance_difficulty.set(cfg.get('teamInstanceDifficulty','简单'))
            self.team_instance_daily_count.set(cfg.get('teamInstanceDailyCount',1))
            self.arena_limit.set(cfg.get('arenaBattleLimit',3))
            server=cfg.get('rankedServer','连服')
            self.ranked_server.set('连服' if server=='联服' else server)
            self.ranked_all.set(cfg.get('rankedLimit',0)==0)
            self.ranked_count.set(cfg.get('rankedLimit',0) or 1)
            for key in ('difficulty', 'reset', 'tolerance', 'battle_seconds', 'hosting_minutes', 'escort_refresh_limit', 'escort_grade', 'model', 'base_url', 'family', 'display'):
                if key in cfg: getattr(self,key).set(cfg[key])
            for key in self.selection: self.selection[key].set(key in cfg.get('tasks', self.selection))
        except (OSError, ValueError, tk.TclError): pass

    def config(self):
        ranked_limit=0 if self.ranked_all.get() else self.ranked_count.get()
        if not self.ranked_all.get() and not 1<=ranked_limit<=20:
            raise ValueError('自选排位战场数应为1至20')
        arena_limit=parse_battle_limit(self.arena_limit.get(),enabled=False)
        return dict(tasks=[key for key in self.task_order if self.selection[key].get()], taskOrder=list(self.task_order), difficulty=self.difficulty.get(),
                    reset=self.reset.get(), survivalGrades=[g for g in GRADES if self.survival_grades[g].get()],
                    survivalCounts={g: self.survival_counts[g].get() for g in GRADES if self.survival_grades[g].get()},
                    survivalInitial=self.survival_initial.get(), survivalGoal=self.survival_goal.get(),
                    tolerance=self.tolerance.get(), battleSeconds=self.battle_seconds.get(),
                    arenaMode=self.arena_mode.get(),arenaBattleLimit=arena_limit,
                    teamInstanceName=self.team_instance_name.get(),teamInstanceDifficulty=self.team_instance_difficulty.get(),
                    teamInstanceDailyCount=self.team_instance_daily_count.get(),
                    rankedServer=self.ranked_server.get(),rankedLimit=ranked_limit,
                    hostingMinutes=self.hosting_minutes.get(), escortRefreshLimit=self.escort_refresh_limit.get(), escortGrade=self.escort_grade.get(), displayId=self.display.get().strip(), preview=self.preview.get(),backend=self.backend.get())

    def save(self):
        try:
            cfg = self.config()
            from ranked_policy import ranked_options
            ranked_options(cfg)
            if 'survival' in cfg['tasks']:survival_plan(cfg);estimate(cfg, cfg['survivalInitial'], cfg['survivalGoal'])
            for key in ('difficulty', 'reset', 'tolerance', 'battle_seconds', 'hosting_minutes', 'escort_refresh_limit', 'escort_grade', 'model', 'base_url', 'family', 'display'):
                cfg[key] = getattr(self,key).get()
            cfg.pop('preview',None)
            (ROOT/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self.log('设置已保存')
        except (ValueError, tk.TclError, OSError) as e: messagebox.showerror('保存失败',str(e))

    def build(self):
        from mission_desk_ui import build
        build(self, TASKS)

    def update_nav(self,event=None):
        from mission_desk_ui import update_navigation
        update_navigation(self)

    def model_settings(self):
        dialog=tk.Toplevel(self);dialog.title('Midscene 前台模型设置');dialog.geometry('660x440')
        frame=ttk.Frame(dialog,padding=20);frame.pack(fill='both',expand=True)
        for label,var in [('模型名称',self.model),('API 地址',self.base_url),('模型 Family',self.family)]:self.field(frame,label,var)
        self.field(frame,'API Key',self.api_key,secret=True)
        self.field(frame,'显示器 ID（可留空）',self.display)
        ttk.Label(frame,text='本地后台方式不需要填写这些设置。',foreground='#888888').pack(anchor='w',pady=14)
        ttk.Button(frame,text='保存设置',command=self.save).pack(anchor='w')

    def field(self,parent,label,variable,values=None,spin=None,secret=False):
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        stacked=parent==getattr(self,'task_fields',None)
        caption=ttk.Label(row,text=label,width=0 if stacked else 22)
        if stacked:caption.pack(anchor='w',pady=(0,5))
        else:caption.pack(side='left')
        if values is not None: widget=ttk.Combobox(row,textvariable=variable,values=values,state='readonly')
        elif spin:widget=ttk.Spinbox(row,textvariable=variable,from_=spin[0],to=spin[1],width=12)
        else:widget=ttk.Entry(row,textvariable=variable,show='●' if secret else '')
        if stacked:widget.pack(fill='x',expand=True)
        else:widget.pack(side='left',fill='x',expand=True)
        return widget

    def build_log_view(self,parent,title,compact=False):
        from mission_desk_ui import build_log_view
        return build_log_view(self,parent,title,compact)

    def wrap_labels(self,parent,width):
        for child in parent.winfo_children():
            if isinstance(child,ttk.Label):
                current=int(child.cget('wraplength') or 0)
                if current>0 and current!=width:child.configure(wraplength=width)
            elif isinstance(child,ttk.Frame):self.wrap_labels(child,width)

    def resize_task_fields(self,event):
        if int(float(self.task_canvas.itemcget(self.task_field_window,'width'))) != event.width:
            self.task_canvas.itemconfigure(self.task_field_window,width=event.width)
        self.wrap_labels(self.task_fields,max(100,event.width-8))

    def route_task_scroll(self,event):
        widget=event.widget
        while widget is not None:
            if widget in (self.task_canvas,self.task_fields):
                self.scroll_task_fields(event)
                return 'break'
            widget=getattr(widget,'master',None)

    def schedule_pane_layout(self,event=None):
        if event is not None:
            if getattr(self,'_pane_requested_width',None)==event.width:return
            self._pane_requested_width=event.width
        if self.layout_job:self.after_cancel(self.layout_job)
        self.layout_job=self.after(50,self.layout_panes)

    def layout_panes(self):
        self.layout_job=None
        width=self.panes.winfo_width()-10
        if width<=0:return
        left=max(236,int(width*self.pane_ratios[0]))
        logs=max(220,int(width*self.pane_ratios[2]))
        # Reserve settings space even when a sash was moved near an edge.
        left=min(left,max(236,width-552))
        logs=min(logs,max(220,width-left-332))
        if self.panes.sashpos(0)!=left:self.panes.sashpos(0,left)
        if self.panes.sashpos(1)!=width-logs+5:self.panes.sashpos(1,width-logs+5)

    def begin_pane_resize(self,event):
        self.resizing_sash=self.panes.identify(event.x,event.y) in (0,1)

    def end_pane_resize(self,event):
        if self.resizing_sash:
            width=max(1,self.panes.winfo_width()-10)
            left=self.panes.sashpos(0);middle=self.panes.sashpos(1)-left-5
            self.pane_ratios=(left/width,middle/width,(width-left-middle)/width)
            self.schedule_pane_layout()
        self.resizing_sash=False

    def scroll_task_fields(self,event):
        if self.task_fields.winfo_reqheight()>self.task_canvas.winfo_height():self.task_canvas.yview_scroll(-int(event.delta/120),'units')

    def update_survival_summary(self,*_):
        try:
            cfg=self.config()
            added,total,missing=estimate(cfg,self.survival_initial.get(),self.survival_goal.get())
            grades=' → '.join(cfg['survivalGrades'])
            result=f'挑战顺序：{grades}\n预计增加 {added} 分 · 预计总分 {total}/{self.survival_goal.get()}'
            result+=f' · 还差 {missing} 分' if missing else ' · 可达到目标'
            self.survival_summary.set(result)
        except (ValueError,tk.TclError):self.survival_summary.set('请勾选等级并填写有效场数和积分估算值。')

    def show_task(self,key,mode=None):
        if key == 'arena':
            self.arena_view.show_mode(mode or 'common')
            self.grocery_view.show_tool('arena')
            self.notebook.select(self.help_panel)
            return
        if mode is not None:self.task_modes[key]=mode
        mode=self.task_modes[key]
        self.selected.set(key)
        self.notebook.select(self.task_panel)
        self.task_title.config(text=dict(TASKS)[key])
        from mission_desk_ui import update_task_focus
        update_task_focus(self)
        for task,gear in self.gears.items():gear.config(fg=BLUE if task==key else '#5e6b52')
        for tab,(frame,button) in self.task_tab_buttons.items():
            frame.config(highlightbackground=BLUE if tab==mode else '#dddddd')
            button.config(fg=BLUE if tab==mode else '#252525')
        for child in self.task_fields.winfo_children():child.destroy()
        self.task_canvas.yview_moveto(0)
        if key=='welfare':
            show_welfare_task(self,mode)
            return
        if key=='team_instance':
            show_team_instance(self,mode)
            return
        if key=='wanted':
            show_wanted_task(self,mode)
            return
        self.task_hint.set({'survival':'每场检查实际积分，达到游戏满分后领取奖励。',
                           'strong':'支持天级、夜叉级、阿修罗级。普通奖励次数为0时跳过。',
                           'hosting':'本轮结束判断与完整收尾仍待实施或验收。',
                           'ranked':'按所选范围和场数挑战；战败尝试刷新，冷却时继续挑战。',
                           'escort':'每日最多3次；目前执行至接取，交付流程待补充。'}[key])
        if key=='survival':self.plan_summary_label.pack(fill='x',before=self.plan_summary_label.master.winfo_children()[0],pady=(0,10))
        else:self.plan_summary_label.pack_forget()
        descriptions={
          'survival':'先检查重置次数，再按高级设置的挑战计划进行。每场读取实际积分，达到游戏满分后一键领取。',
          'strong':'按所选难度进入战斗，等待结算后确认，再查看分数并确认关闭。普通奖励次数为0时跳过。',
          'hosting':'保留游戏已有托管勾选并启动。可靠本轮结束判断及关闭温泉、离开家园的完整收尾仍待实施或验收。',
          'ranked':'按所选本服或连服挑战，优先挑选战力接近的对手，没有匹配则随机选。默认用完剩余次数，胜负都计一次。战败后尝试刷新；冷却时继续按原规则选人。',
          'escort':'组队副本活动 → 押镖劫掠 → 参加。按所选SS或S等级查找，没有则免费刷新，有则点击对应行普通押送。每天最多3次，以游戏剩余次数为准。接取后的路线和交付步骤待补充。'}
        if mode=='common':
            ttk.Label(self.task_fields,text=descriptions[key],wraplength=530,justify='left',foreground='#5e6b52').pack(anchor='w',pady=(0,16))
            if key=='survival':
                ttk.Checkbutton(self.task_fields,text='剩余重置次数为1时重置',variable=self.reset).pack(anchor='w')
                self.field(self.task_fields,'估算起始积分',self.survival_initial,spin=(0,1000))
                self.field(self.task_fields,'估算满分目标',self.survival_goal,spin=(1,1000))
                ttk.Label(self.task_fields,text='起点默认60、目标默认220，只用于估算。实际积分及满分目标自动从游戏读取。',wraplength=530,foreground='#667158').pack(anchor='w')
            elif key=='strong':self.field(self.task_fields,'挑战难度',self.difficulty,values=['天级','夜叉级','阿修罗级'])
            elif key=='hosting':ttk.Label(self.task_fields,text='保留游戏内已有托管任务选择。超时可在高级设置调整。').pack(anchor='w')
            elif key=='ranked':
                self.field(self.task_fields,'挑战范围',self.ranked_server,values=['本服','连服'])
                ttk.Label(self.task_fields,text='连服对应游戏中的“联服”。挑战场数和战力匹配范围可在高级设置调整。',wraplength=530,foreground='#5e6b52').pack(anchor='w',pady=8)
            elif key=='escort':
                self.field(self.task_fields,'接取等级',self.escort_grade,values=['SS','S'])
                ttk.Label(self.task_fields,text='每日接取上限：3次（读取游戏剩余次数）',foreground='#5e6b52').pack(anchor='w',pady=8)
        elif key=='survival':
            ttk.Label(self.task_fields,text='选择挑战等级与每个等级最多挑战场数',font=('Microsoft YaHei UI',11)).pack(anchor='w',pady=(0,6))
            for grade in GRADES:
                row=ttk.Frame(self.task_fields);row.pack(fill='x',pady=3)
                ttk.Checkbutton(row,text=grade,width=6,variable=self.survival_grades[grade]).pack(side='left')
                ttk.Label(row,text=f'{POINTS[grade]} 分 / 场',width=12,foreground='#5e6b52').pack(side='left')
                ttk.Spinbox(row,textvariable=self.survival_counts[grade],from_=1,to=1 if grade=='SS' else 30,width=5).pack(side='left',padx=8)
                ttk.Label(row,text='场（上限）').pack(side='left')
            ttk.Label(self.task_fields,text='只挑战勾选等级，按 SS → S → A → B → C 排序。实际次数不足就跳到下一个所选等级；满分立即领奖。计划耗尽但积分未满时停止并提示。',wraplength=530,foreground='#667158').pack(anchor='w')
        elif key=='hosting':self.field(self.task_fields,'托管超时（分钟）',self.hosting_minutes,spin=(1,240))
        elif key=='ranked':
            ttk.Checkbutton(self.task_fields,text='用完剩余挑战次数（默认）',variable=self.ranked_all,command=self.update_ranked_limit).pack(anchor='w',pady=(0,8))
            row=ttk.Frame(self.task_fields);row.pack(fill='x',pady=6)
            ttk.Label(row,text='最多挑战场数',width=23).pack(side='left')
            self.ranked_count_spin=ttk.Spinbox(row,textvariable=self.ranked_count,from_=1,to=20,width=8)
            self.ranked_count_spin.pack(side='left');self.update_ranked_limit()
            ttk.Label(self.task_fields,text='取消勾选后可填写场数。胜负都计一次；剩余次数不足时以游戏为准。达到上限后结束，不再刷新。',wraplength=530,foreground='#5e6b52').pack(anchor='w',pady=(0,8))
            self.field(self.task_fields,'匹配战力差（百分比）',self.tolerance,spin=(0,100))
        elif key=='escort':self.field(self.task_fields,'最多免费刷新次数',self.escort_refresh_limit,spin=(0,20))
        if mode=='advanced' and key!='survival':
            self.field(self.task_fields,'单场战斗超时（秒）',self.battle_seconds,spin=(30,3600))
            ttk.Label(self.task_fields,text='超时设置对战斗任务共用；连接与运行方式仍在左侧“设置”页。',wraplength=530,foreground='#667158').pack(anchor='w',pady=8)
        self.wrap_labels(self.task_fields,max(100,self.task_canvas.winfo_width()-8))

    def update_ranked_limit(self):
        self.ranked_count_spin.configure(state='disabled' if self.ranked_all.get() else 'normal')

    def select_all(self,value):
        if self.running:return
        for key in self.task_order:self.selection[key].set(value)

    def begin_task_drag(self,event,key):
        if self.running:return 'break'
        self.cancel_task_drag()
        event.widget.focus_set()
        event.widget.grab_set()
        self.task_drag={'key':key,'y':event.y_root,'index':self.task_order.index(key),'moved':False}
        return 'break'

    def update_task_drag(self,event):
        drag=self.task_drag
        if not drag or self.running:return 'break'
        if not drag['moved'] and abs(event.y_root-drag['y'])<5:return 'break'
        drag['moved']=True
        self.task_handles[drag['key']].configure(bg='#eee3d7',cursor='fleur')
        others=[key for key in self.task_order if key!=drag['key']]
        index=sum(event.y_root>=self.task_rows[key].winfo_rooty()+self.task_rows[key].winfo_height()/2 for key in others)
        drag['index']=index
        if index<len(others):y=self.task_rows[others[index]].winfo_y()-3
        else:
            row=self.task_rows[others[-1]] if others else self.task_rows[drag['key']]
            y=row.winfo_y()+row.winfo_height()+1
        self.task_drop_line.place(x=0,y=max(0,y),relwidth=1,height=2)
        self.task_drop_line.lift()
        return 'break'

    def cancel_task_drag(self):
        if self.task_drag:
            handle=self.task_handles[self.task_drag['key']]
            handle.grab_release()
            handle.configure(bg=self.task_rows[self.task_drag['key']].cget('bg'),cursor='hand2')
        self.task_drag=None
        if hasattr(self,'task_drop_line'):self.task_drop_line.place_forget()
        return 'break'

    def end_task_drag(self,event):
        drag=self.task_drag
        if drag and not self.running:self.update_task_drag(event)
        if drag and drag['moved'] and not self.running:
            order=[key for key in self.task_order if key!=drag['key']]
            order.insert(drag['index'],drag['key'])
            self.cancel_task_drag()
            self.apply_task_order(order)
        else:self.cancel_task_drag()
        return 'break'

    def move_task(self,key,offset):
        if self.running:return 'break'
        self.cancel_task_drag()
        index=self.task_order.index(key);target=index+offset
        if 0<=target<len(self.task_order):
            order=list(self.task_order)
            order[index],order[target]=order[target],order[index]
            self.apply_task_order(order)
        return 'break'

    def task_order_menu(self,event,key):
        if self.running:return 'break'
        self.cancel_task_drag()
        event.widget.focus_set()
        menu=tk.Menu(self,tearoff=False)
        index=self.task_order.index(key)
        menu.add_command(label='上移（Alt+↑）',command=lambda:self.move_task(key,-1),state='normal' if index else 'disabled')
        menu.add_command(label='下移（Alt+↓）',command=lambda:self.move_task(key,1),state='normal' if index<len(self.task_order)-1 else 'disabled')
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()
        return 'break'

    def update_task_order_controls(self):
        for handle in self.task_handles.values():
            handle.configure(cursor='arrow' if self.running else 'hand2')
            handle.itemconfigure('all',fill='#aaaaaa' if self.running else '#667586')

    def apply_task_order(self,order):
        if self.running or order==self.task_order:return
        self.task_order=list(order)
        for row in self.task_rows.values():row.pack_forget()
        for key in self.task_order:self.task_rows[key].pack(fill='x',pady=3)
        try:
            path=ROOT/'config.json'
            cfg=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            cfg['taskOrder']=list(self.task_order)
            path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self.status.set('任务顺序已保存：'+ ' → '.join(dict(TASKS)[key] for key in self.task_order))
        except (OSError,ValueError,TypeError) as e:
            self.status.set('顺序已调整，本次可用；保存失败')
            messagebox.showerror('任务顺序保存失败',str(e))

    def update_sorting_state(self):
        for handle in self.task_handles.values():
            handle.configure(cursor='arrow' if self.running else 'hand2',takefocus=not self.running)
            handle.itemconfigure('all',fill='#b8bdc3' if self.running else '#667586')

    def refresh_windows(self):
        self.windows=game_windows()
        values=[f'{title}  [{hwnd}]' for hwnd,title in self.windows]
        self.window_combo.config(values=values)
        if self.window_choice.get() not in values:self.window_choice.set(values[0] if values else '')

    def log(self,message):
        secrets=(self.api_key.get(),)+ (self.failure_tracker.secrets if self.failure_tracker else ())
        message=clean(message,secrets)
        today=local_day()
        if getattr(self,'_retention_day',None)!=today:
            try:
                maintain_logs(ROOT,today)
                self._retention_day=today
            except (OSError,ValueError,sqlite3.Error) as error:
                message+='\n日志清理未完成：'+clean(str(error),secrets)
        text=f'[{time.strftime("%H:%M:%S")}] {message}\n'
        for view in self.log_views:
            view.config(state='normal');view.insert('end',text)
            if self.follow_logs.get():view.see('end')
            view.config(state='disabled')
        folder=ROOT/'logs';folder.mkdir(exist_ok=True)
        with (folder/(today.isoformat()+'.log')).open('a',encoding='utf-8') as f:f.write(text)

    def open_logs(self):
        (ROOT/'logs').mkdir(exist_ok=True);os.startfile(ROOT/'logs')

    def open_failures(self):
        archive=FailureArchive(ROOT)
        os.startfile(archive.folder)

    def start(self,diagnostic=False,*,arena_only=False):
        if getattr(getattr(self,'grocery_tool',None),'running',False):
            messagebox.showwarning('正在运行杂货屋','请先停止杂货屋，再启动每日任务或后台诊断。',parent=self)
            return
        if self.running:return
        self.cancel_task_drag()
        self.failure_tracker=None;self.stopping=False
        try:
            cfg=self.config()
            if arena_only:
                cfg.update(tasks=['arena'], arenaBattleLimit=parse_battle_limit(self.arena_limit.get(),enabled=True))
            cfg['diagnostic']=diagnostic
            if diagnostic:cfg['preview']=False
            if not cfg['tasks'] and not diagnostic:raise ValueError('请至少勾选一个任务')
            from ranked_policy import ranked_options
            ranked_options(cfg)
            if 'survival' in cfg['tasks'] and not diagnostic:
                survival_plan(cfg);estimate(cfg,cfg['survivalInitial'],cfg['survivalGoal'])
            if not 0<=cfg['tolerance']<=100 or not 30<=cfg['battleSeconds']<=3600 or not 1<=cfg['hostingMinutes']<=240:raise ValueError('请检查超时和战力匹配范围')
            if not 0<=cfg['escortRefreshLimit']<=20:raise ValueError('押镖免费刷新上限应为0至20')
            if cfg['escortGrade'] not in ('SS','S'):raise ValueError('押镖接取等级应为SS或S')
            if not diagnostic:
                validate_arena_config(cfg)
                validate_team_instance_config(cfg)
            local=cfg['backend']=='本地后台（免API）' or diagnostic
            if 'welfare' in cfg['tasks'] and not local:
                raise ValueError('福利大厅使用本地素材识别，请选择“本地后台（免API）”')
            if 'wanted' in cfg['tasks'] and not local:
                raise ValueError('通缉任务使用本地素材识别，请选择“本地后台（免API）”')
            node=shutil.which('node')
            if not local and not node:raise ValueError('未找到Node.js，请先安装')
            if not cfg['preview']:
                if not local:
                    if not all(v.get().strip() for v in (self.model,self.family,self.base_url,self.api_key)):raise ValueError('请在连接设置填写模型名称、API地址、Family和API Key')
                    if not (ROOT/'node_modules/@midscene/computer').exists():raise ValueError('缺少运行依赖，请运行 scripts/安装依赖.cmd')
                elif not (ROOT/'resources/local/ocr/rec.onnx').exists():raise ValueError('缺少本地OCR模型')
                self.refresh_windows()
                if not self.windows:raise ValueError('未找到360游戏大厅中的火影忍者online窗口')
                index=self.window_combo.current()
                if index<0:raise ValueError('请选择游戏窗口')
                self.game_hwnd=self.windows[index][0]
                cfg['gameHwnd']=self.game_hwnd
            self.save()
            cfg['runId']=run_id()
            self.failure_tracker=RunFailureTracker(ROOT,cfg['runId'],cfg['backend'],(self.api_key.get(),))
            self.log('运行编号：'+cfg['runId'])
            (ROOT/'run.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
            env=os.environ.copy()
            env.update(MIDSCENE_MODEL_NAME=self.model.get().strip(),MIDSCENE_MODEL_FAMILY=self.family.get().strip(),MIDSCENE_MODEL_BASE_URL=self.base_url.get().strip(),MIDSCENE_MODEL_API_KEY=self.api_key.get().strip())
            env['PYTHONIOENCODING']='utf-8'
            if local:
                for key in list(env):
                    if key.startswith('MIDSCENE_MODEL_'):env.pop(key)
            command=[sys.executable,str(ROOT/'src/native_worker.py'),str(ROOT/'run.json')] if local else [node,str(ROOT/'src/worker.mjs'),str(ROOT/'run.json')]
            self.process=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except (ValueError,tk.TclError,OSError,sqlite3.Error) as e:
            if self.failure_tracker:self.collect_failure_event({'kind':'error','message':str(e),'failure':exception_details(e,self.failure_tracker.secrets)},self.failure_tracker)
            messagebox.showerror('无法开始',str(e));self.notebook.select(self.settings_panel);return
        self.running=True;self.stopping=False;self.paused=False;self.pending_pause=False
        self.update_sorting_state()
        self.update_task_order_controls()
        self.statuses['startup'].set('排队中' if local and not diagnostic else '不执行')
        for key,_ in TASKS:self.statuses[key].set('排队中' if key in cfg['tasks'] else '未选择')
        self.start_button.config(state='disabled');self.pause_button.config(state='normal',text='暂停');self.stop_button.config(state='normal')
        self.status.set('运行中');self.notebook.select(self.help_panel if arena_only else self.task_panel)
        self.step_status.set('当前步骤：等待任务开始')
        if not cfg['preview'] and not local:
            self.iconify()
            user=ctypes.windll.user32
            user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
            user.SetForegroundWindow.argtypes=[wintypes.HWND]
            user.ShowWindow(self.game_hwnd,9);user.SetForegroundWindow(self.game_hwnd)
        threading.Thread(target=self.read_output,args=(self.process,),daemon=True).start()

    def read_output(self,process):
        tracker=self.failure_tracker
        for line in process.stdout:
            if line.startswith('APP_EVENT '):
                try:
                    event=json.loads(line[10:])
                    if not isinstance(event,dict) or not isinstance(event.get('kind'),str):raise ValueError('无效运行事件')
                    event['message']=str(event.get('message',''))
                except ValueError:event={'kind':'log','message':line.strip()}
            else:event={'kind':'log','message':line.strip()}
            self.collect_failure_event(event,tracker)
        code=process.wait();self.collect_failure_event({'kind':'exit','message':str(code)},tracker)

    def collect_failure_event(self,event,tracker):
        result=None
        if tracker:
            try:result=tracker.event(event,manual=self.stopping)
            except (OSError,ValueError,sqlite3.Error) as error:
                self.events.put({'kind':'log','message':'错误归档失败：'+clean(str(error),tracker.secrets)})
        self.events.put(event)
        if result:
            if result['status']=='interrupted':message='人工中断已记录，不计入错误统计：'+result['taskName']
            else:message=f"错误已归档：{result['taskName']} · {result['step']}；详情见“出错任务统计”"
            self.events.put({'kind':'log','message':message})

    def drain(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event['kind'];message=event['message']
                # Never retain a model credential in generated UI or logs.
                key=self.api_key.get()
                if key:message=message.replace(key,'[API Key已隐藏]')
                if kind=='exit':
                    self.running=False;self.start_button.config(state='normal');self.pause_button.config(state='disabled',text='暂停');self.stop_button.config(state='disabled')
                    self.update_sorting_state()
                    self.update_task_order_controls()
                    if self.stopping:self.status.set('已停止');self.log('执行已停止')
                    elif message!='0' and not self.status.get().startswith('失败'):self.status.set('进程异常退出，请查看日志')
                    if self.active_task and self.statuses[self.active_task].get()=='运行中':self.statuses[self.active_task].set('已停止' if self.stopping else '失败')
                    if self.backend.get()=='Midscene（前台）':self.deiconify()
                    self.process=None
                else:
                    if message:self.log(message)
                    if kind=='task':
                        self.active_task=event['id'];self.statuses[event['id']].set({'running':'运行中','done':'完成','preview':'预览完成','accepted':'已接取，待交付','skipped':'已跳过','failed':'未完成'}.get(event['status'],event['status']))
                        if event['status']=='running':self.step_status.set('当前步骤：'+message)
                    elif kind=='node':self.step_status.set(message)
                    elif kind=='paused':self.paused=True;self.pending_pause=False;self.status.set('已暂停');self.pause_button.config(text='继续',state='normal')
                    elif kind=='done':self.status.set(message)
                    elif kind=='error':self.status.set('正在停止' if event.get('manual') or self.stopping else '失败：'+message)
        except queue.Empty:pass
        self.after(100,self.drain)

    def send(self,message):
        if self.process and self.process.poll() is None:
            try:self.process.stdin.write(message+'\n');self.process.stdin.flush()
            except (BrokenPipeError,OSError):pass

    def pause(self):
        if not self.running:return
        if self.paused:
            self.paused=False;self.send('resume');self.pause_button.config(text='暂停');self.status.set('运行中')
        else:
            self.pending_pause=True;self.send('pause');self.pause_button.config(state='disabled',text='暂停中');self.status.set('等待当前操作结束后暂停')

    def stop(self):
        if not self.running or self.stopping:return
        self.stopping=True;self.status.set('正在停止');self.send('stop')
        if self.failure_tracker and not self.failure_tracker.recorded:
            self.collect_failure_event({'kind':'interrupted','message':'用户主动停止运行','manual':True},self.failure_tracker)
        process=self.process
        def kill():
            if process.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                else:process.terminate()
        threading.Thread(target=kill,daemon=True).start()

    def close(self):
        grocery=getattr(self,'grocery_tool',None)
        if grocery and grocery.running:grocery.close()
        if self.running:
            self.stop();self.after(200,self.close_when_stopped)
        elif grocery and grocery.running:self.after(200,self.close_when_stopped)
        else:
            if grocery:grocery.dispose()
            self.destroy()

    def close_when_stopped(self):
        grocery=getattr(self,'grocery_tool',None)
        if self.running or (grocery and grocery.running):self.after(200,self.close_when_stopped)
        else:
            if grocery:grocery.dispose()
            self.destroy()

if __name__=='__main__':
    App().mainloop()
