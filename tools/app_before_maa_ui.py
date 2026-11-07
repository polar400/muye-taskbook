"""火影忍者online daily task desktop application. Python 3.10+, Windows."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = Path(__file__).resolve().parent
TASKS = [(task['id'], task['label']) for task in json.loads((ROOT/'resources/tasks.json').read_text(encoding='utf-8'))['tasks']]
BLUE = '#0784c5'

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
        self.title('火影忍者online · 每日任务助手 0.1')
        self.geometry('1120x790')
        self.minsize(980, 720)
        self.configure(bg='white')
        self.events = queue.Queue()
        self.process = None
        self.running = False
        self.pending_pause = False
        self.paused = False
        self.stopping = False
        self.active_task = None
        self.windows = []
        self.selection = {key: tk.BooleanVar(value=True) for key, _ in TASKS}
        self.statuses = {key: tk.StringVar(value='待运行') for key, _ in TASKS}
        self.selected = tk.StringVar(value='survival')
        self.status = tk.StringVar(value='就绪 · 请先完成模型连接设置')
        self.difficulty = tk.StringVar(value='阿修罗级')
        self.reset = tk.BooleanVar(value=True)
        self.tolerance = tk.IntVar(value=20)
        self.battle_seconds = tk.IntVar(value=900)
        self.hosting_minutes = tk.IntVar(value=90)
        self.escort_refresh_limit = tk.IntVar(value=4)
        self.escort_grade = tk.StringVar(value='SS')
        self.preview = tk.BooleanVar(value=False)
        self.window_choice = tk.StringVar()
        self.display = tk.StringVar()
        self.model = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_NAME', ''))
        self.base_url = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_BASE_URL', ''))
        self.family = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_FAMILY', ''))
        self.api_key = tk.StringVar(value=os.getenv('MIDSCENE_MODEL_API_KEY', ''))
        self.load()
        self.build()
        self.refresh_windows()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)

    def load(self):
        try:
            cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
            for key in ('difficulty', 'reset', 'tolerance', 'battle_seconds', 'hosting_minutes', 'escort_refresh_limit', 'escort_grade', 'model', 'base_url', 'family', 'display'):
                if key in cfg: getattr(self,key).set(cfg[key])
            for key in self.selection: self.selection[key].set(key in cfg.get('tasks', self.selection))
        except (OSError, ValueError, tk.TclError): pass

    def config(self):
        return dict(tasks=[key for key,_ in TASKS if self.selection[key].get()], difficulty=self.difficulty.get(),
                    reset=self.reset.get(), tolerance=self.tolerance.get(), battleSeconds=self.battle_seconds.get(),
                    hostingMinutes=self.hosting_minutes.get(), escortRefreshLimit=self.escort_refresh_limit.get(), escortGrade=self.escort_grade.get(), displayId=self.display.get().strip(), preview=self.preview.get())

    def save(self):
        try:
            cfg = self.config()
            for key in ('difficulty', 'reset', 'tolerance', 'battle_seconds', 'hosting_minutes', 'escort_refresh_limit', 'escort_grade', 'model', 'base_url', 'family', 'display'):
                cfg[key] = getattr(self,key).get()
            cfg.pop('preview',None)
            (ROOT/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self.log('设置已保存；API Key只保留在本次运行内存中')
        except (ValueError, tk.TclError, OSError) as e: messagebox.showerror('保存失败',str(e))

    def build(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='white')
        style.configure('TFrame',background='white')
        style.configure('TLabel',background='white',foreground='#252e38')
        style.configure('TButton',padding=(12,7),background='#f7f9fb')
        style.configure('Blue.TButton',background=BLUE,foreground='white',padding=(18,10))
        style.map('Blue.TButton',background=[('active','#00689d'),('disabled','#aebcc4')])
        style.configure('TCheckbutton',background='white')
        style.configure('TNotebook',background='white',borderwidth=0)
        style.configure('TNotebook.Tab',padding=(34,12),background='#f7f9fb')
        style.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected',BLUE)])
        head = ttk.Frame(self,padding=(26,18))
        head.pack(fill='x')
        ttk.Label(head,text='火影忍者online',font=('Microsoft YaHei UI',18,'bold')).pack(side='left')
        ttk.Label(head,text='每日任务助手  /  0.1',foreground='#718096').pack(side='left',padx=18)
        ttk.Button(head,text='打开文件夹',command=lambda:os.startfile(ROOT)).pack(side='right')
        ttk.Separator(self).pack(fill='x')
        body = ttk.Frame(self,padding=24)
        body.pack(fill='both',expand=True)
        left = ttk.Frame(body,width=285)
        left.pack(side='left',fill='y',padx=(0,24))
        left.pack_propagate(False)
        ttk.Label(left,text='一键每日',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',pady=(0,12))
        card = ttk.LabelFrame(left,text='任务队列',padding=12)
        card.pack(fill='x')
        for key, name in TASKS:
            row=ttk.Frame(card); row.pack(fill='x',pady=3)
            ttk.Checkbutton(row,text=name,variable=self.selection[key]).pack(side='left')
            ttk.Button(row,text='⚙',width=3,command=lambda k=key:self.show_task(k)).pack(side='right')
            ttk.Label(card,textvariable=self.statuses[key],foreground='#77828d').pack(anchor='w',padx=24)
        bar=ttk.Frame(card);bar.pack(fill='x',pady=(22,0))
        ttk.Button(bar,text='全选',command=lambda:self.select_all(True)).pack(side='left',expand=True,fill='x')
        ttk.Button(bar,text='清空',command=lambda:self.select_all(False)).pack(side='left',expand=True,fill='x')
        ttk.Label(left,text='完成后：返回木叶村',foreground='#718096').pack(pady=10)
        self.start_button=ttk.Button(left,text='开始执行',style='Blue.TButton',command=self.start)
        self.start_button.pack(fill='x',pady=(0,8))
        control=ttk.Frame(left);control.pack(fill='x')
        self.pause_button=ttk.Button(control,text='暂停',state='disabled',command=self.pause)
        self.pause_button.pack(side='left',fill='x',expand=True)
        self.stop_button=ttk.Button(control,text='停止',state='disabled',command=self.stop)
        self.stop_button.pack(side='left',fill='x',expand=True)
        self.preview_button=ttk.Checkbutton(left,text='流程预览（不操作游戏）',variable=self.preview)
        self.preview_button.pack(anchor='w',pady=8)
        self.notebook=ttk.Notebook(body);self.notebook.pack(side='left',fill='both',expand=True)
        self.task_panel=ttk.Frame(self.notebook,padding=20)
        self.settings_panel=ttk.Frame(self.notebook,padding=20)
        self.log_panel=ttk.Frame(self.notebook,padding=12)
        self.help_panel=ttk.Frame(self.notebook,padding=20)
        for panel,label in [(self.task_panel,'任务设置'),(self.settings_panel,'连接设置'),(self.log_panel,'运行日志'),(self.help_panel,'使用说明')]:self.notebook.add(panel,text=label)
        self.task_title=ttk.Label(self.task_panel,font=('Microsoft YaHei UI',16,'bold'));self.task_title.pack(anchor='w',pady=(0,18))
        self.task_fields=ttk.Frame(self.task_panel);self.task_fields.pack(fill='x')
        ttk.Separator(self.task_panel).pack(fill='x',pady=20)
        ttk.Label(self.task_panel,text='通用等待设置',font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w',pady=8)
        self.field(self.task_panel,'单场战斗超时（秒）',self.battle_seconds,spin=(30,3600))
        ttk.Button(self.task_panel,text='保存设置',command=self.save).pack(anchor='w',pady=20)
        self.field(self.settings_panel,'游戏窗口',self.window_choice,values=[])
        self.window_combo=self.settings_panel.winfo_children()[-1].winfo_children()[-1]
        ttk.Button(self.settings_panel,text='刷新游戏窗口',command=self.refresh_windows).pack(anchor='w',pady=(0,14))
        self.field(self.settings_panel,'模型名称',self.model)
        self.field(self.settings_panel,'API 地址',self.base_url)
        self.field(self.settings_panel,'模型 Family',self.family)
        self.field(self.settings_panel,'API Key',self.api_key,secret=True)
        self.field(self.settings_panel,'显示器 ID（可留空）',self.display)
        ttk.Label(self.settings_panel,text='使用支持视觉定位的模型。API Key只在本次运行内使用。\n开始前请让游戏处于木叶村主界面；执行时会使用真实鼠标。\n多屏环境可填游戏所在显示器ID。',wraplength=540,foreground='#718096').pack(anchor='w',pady=12)
        ttk.Button(self.settings_panel,text='保存连接设置',command=self.save).pack(anchor='w')
        logbar=ttk.Frame(self.log_panel);logbar.pack(fill='x',pady=(0,8))
        ttk.Button(logbar,text='打开日志文件夹',command=self.open_logs).pack(side='right')
        self.log_text=tk.Text(self.log_panel,font=('Microsoft YaHei UI',10),wrap='word',bg='#f8fafc',fg='#344456',relief='flat',padx=12,pady=12,state='disabled')
        self.log_text.pack(fill='both',expand=True)
        helptext='1. 打开360游戏大厅中的火影忍者online，进入要运行的账号。\n\n2. 在连接设置填写视觉模型名称、API地址、Family和API Key；API Key不写入配置。\n\n3. 左侧勾选任务，点击齿轮设置参数。强者降临支持天级、夜叉级和阿修罗级。\n\n4. 点击开始执行。程序最小化后会将选定游戏窗口置于前台。执行中不要手动操作鼠标。\n\n5. 暂停会等待当前识别或操作结束；停止会终止进程。失败后可处理游戏界面，再重新选择任务开始。\n\n流程预览仅检查队列，不调用模型、不点击游戏。\n\n当前实现使用Midscene视觉模型；尚未进行完整的游戏自动化验收。首次使用请单独勾选一项任务验证。'
        ttk.Label(self.help_panel,text=helptext,wraplength=540,justify='left').pack(anchor='nw')
        footer=ttk.Frame(self,padding=(26,12));footer.pack(fill='x')
        ttk.Label(footer,textvariable=self.status,foreground=BLUE).pack(anchor='w')
        self.show_task('survival')

    def field(self,parent,label,variable,values=None,spin=None,secret=False):
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        ttk.Label(row,text=label,width=22).pack(side='left')
        if values is not None: widget=ttk.Combobox(row,textvariable=variable,values=values,state='readonly')
        elif spin:widget=ttk.Spinbox(row,textvariable=variable,from_=spin[0],to=spin[1],width=12)
        else:widget=ttk.Entry(row,textvariable=variable,show='●' if secret else '')
        widget.pack(side='left',fill='x',expand=True)
        return widget

    def show_task(self,key):
        self.selected.set(key)
        self.notebook.select(self.task_panel)
        self.task_title.config(text=dict(TASKS)[key])
        for child in self.task_fields.winfo_children():child.destroy()
        descriptions={
          'survival':'重置一次 → SS → S → A/B/C。每场检查积分，积分满后一键领取。绿色自动需点击到红色取消，速度设为×2。',
          'strong':'按所选难度进入战斗，等待结算后确认，再查看分数并确认关闭。普通奖励次数为0时跳过。',
          'hosting':'保留游戏已有托管勾选，开始托管。确认日志显示本轮托管结束后，关闭温泉并离开家园。',
          'ranked':'读取次数和我方战力，优先挑选战力接近的对手。没有匹配对手则随机选。结束战斗后无论胜负都确认，重复至次数为0。',
          'escort':'组队副本活动 → 押镖劫掠 → 参加。按所选SS或S等级查找，没有则免费刷新，有则点击对应行普通押送。每天最多3次，以游戏剩余次数为准。接取后的路线和交付步骤待补充。'}
        ttk.Label(self.task_fields,text=descriptions[key],wraplength=530,justify='left',foreground='#667586').pack(anchor='w',pady=(0,20))
        if key=='survival':ttk.Checkbutton(self.task_fields,text='剩余重置次数为1时重置',variable=self.reset).pack(anchor='w')
        elif key=='strong':self.field(self.task_fields,'挑战难度',self.difficulty,values=['天级','夜叉级','阿修罗级'])
        elif key=='hosting':self.field(self.task_fields,'托管超时（分钟）',self.hosting_minutes,spin=(1,240))
        elif key=='ranked':self.field(self.task_fields,'匹配战力差（百分比）',self.tolerance,spin=(0,100))
        elif key=='escort':
            self.field(self.task_fields,'接取等级',self.escort_grade,values=['SS','S'])
            ttk.Label(self.task_fields,text='每日接取上限：3次（读取游戏剩余次数）',foreground='#667586').pack(anchor='w',pady=8)
            self.field(self.task_fields,'最多免费刷新次数',self.escort_refresh_limit,spin=(0,20))

    def select_all(self,value):
        if self.running:return
        for var in self.selection.values():var.set(value)

    def refresh_windows(self):
        self.windows=game_windows()
        values=[f'{title}  [{hwnd}]' for hwnd,title in self.windows]
        self.window_combo.config(values=values)
        if self.window_choice.get() not in values:self.window_choice.set(values[0] if values else '')

    def log(self,message):
        text=f'[{time.strftime("%H:%M:%S")}] {message}\n'
        self.log_text.config(state='normal');self.log_text.insert('end',text);self.log_text.see('end');self.log_text.config(state='disabled')
        folder=ROOT/'logs';folder.mkdir(exist_ok=True)
        with (folder/(time.strftime('%Y-%m-%d')+'.log')).open('a',encoding='utf-8') as f:f.write(text)

    def open_logs(self):
        (ROOT/'logs').mkdir(exist_ok=True);os.startfile(ROOT/'logs')

    def start(self):
        if self.running:return
        try:
            cfg=self.config()
            if not cfg['tasks']:raise ValueError('请至少勾选一个任务')
            if not 0<=cfg['tolerance']<=100 or not 30<=cfg['battleSeconds']<=3600 or not 1<=cfg['hostingMinutes']<=240:raise ValueError('请检查超时和战力匹配范围')
            if not 0<=cfg['escortRefreshLimit']<=20:raise ValueError('押镖免费刷新上限应为0至20')
            if cfg['escortGrade'] not in ('SS','S'):raise ValueError('押镖接取等级应为SS或S')
            node=shutil.which('node')
            if not node:raise ValueError('未找到Node.js，请先安装')
            if not cfg['preview']:
                if not all(v.get().strip() for v in (self.model,self.family,self.base_url,self.api_key)):raise ValueError('请在连接设置填写模型名称、API地址、Family和API Key')
                if not (ROOT/'node_modules/@midscene/computer').exists():raise ValueError('缺少运行依赖，请运行 安装依赖.cmd')
                self.refresh_windows()
                if not self.windows:raise ValueError('未找到360游戏大厅中的火影忍者online窗口')
                index=self.window_combo.current()
                if index<0:raise ValueError('请选择游戏窗口')
                self.game_hwnd=self.windows[index][0]
            self.save()
            (ROOT/'run.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
            env=os.environ.copy()
            env.update(MIDSCENE_MODEL_NAME=self.model.get().strip(),MIDSCENE_MODEL_FAMILY=self.family.get().strip(),MIDSCENE_MODEL_BASE_URL=self.base_url.get().strip(),MIDSCENE_MODEL_API_KEY=self.api_key.get().strip())
            env['PYTHONIOENCODING']='utf-8'
            self.process=subprocess.Popen([node,str(ROOT/'src/worker.mjs'),str(ROOT/'run.json')],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except (ValueError,tk.TclError,OSError) as e:messagebox.showerror('无法开始',str(e));self.notebook.select(self.settings_panel);return
        self.running=True;self.stopping=False;self.paused=False;self.pending_pause=False
        for key,_ in TASKS:self.statuses[key].set('排队中' if key in cfg['tasks'] else '未选择')
        self.start_button.config(state='disabled');self.pause_button.config(state='normal',text='暂停');self.stop_button.config(state='normal')
        self.status.set('运行中');self.notebook.select(self.log_panel)
        if not cfg['preview']:
            self.iconify()
            user=ctypes.windll.user32
            user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
            user.SetForegroundWindow.argtypes=[wintypes.HWND]
            user.ShowWindow(self.game_hwnd,9);user.SetForegroundWindow(self.game_hwnd)
        threading.Thread(target=self.read_output,args=(self.process,),daemon=True).start()

    def read_output(self,process):
        for line in process.stdout:
            if line.startswith('APP_EVENT '):
                try:self.events.put(json.loads(line[10:]))
                except ValueError:self.events.put({'kind':'log','message':line.strip()})
            else:self.events.put({'kind':'log','message':line.strip()})
        code=process.wait();self.events.put({'kind':'exit','message':str(code)})

    def drain(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event['kind'];message=event['message']
                # Never retain a model credential in generated UI or logs.
                key=self.api_key.get()
                if key:message=message.replace(key,'[API Key已隐藏]')
                if kind=='exit':
                    self.running=False;self.start_button.config(state='normal');self.pause_button.config(state='disabled',text='暂停');self.stop_button.config(state='disabled')
                    if self.stopping:self.status.set('已停止');self.log('执行已停止')
                    elif message!='0' and not self.status.get().startswith('失败'):self.status.set('进程异常退出，请查看日志')
                    if self.active_task and self.statuses[self.active_task].get()=='运行中':self.statuses[self.active_task].set('已停止' if self.stopping else '失败')
                    self.deiconify();self.process=None
                else:
                    if message:self.log(message)
                    if kind=='task':
                        self.active_task=event['id'];self.statuses[event['id']].set({'running':'运行中','done':'完成','preview':'预览完成'}.get(event['status'],event['status']))
                    elif kind=='paused':self.paused=True;self.pending_pause=False;self.status.set('已暂停');self.pause_button.config(text='继续',state='normal')
                    elif kind=='done':self.status.set(message)
                    elif kind=='error':self.status.set('失败：'+message)
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
        process=self.process
        def kill():
            if process.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                else:process.terminate()
        threading.Thread(target=kill,daemon=True).start()

    def close(self):
        if self.running:
            self.stop();self.after(200,self.close_when_stopped)
        else:self.destroy()

    def close_when_stopped(self):
        if self.running:self.after(200,self.close_when_stopped)
        else:self.destroy()

if __name__=='__main__':
    App().mainloop()
