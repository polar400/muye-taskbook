"""Arena settings and independent run controls within the existing tools page."""
import tkinter as tk
from tkinter import ttk, messagebox
from arena_settings import parse_battle_limit
from arena_task_ui import show_arena_task


class ArenaToolView(ttk.Frame):
    arena_standalone = True

    def __init__(self, ui, parent):
        super().__init__(parent)
        self.ui = ui
        self.arena_mode = ui.arena_mode
        self.arena_limit = ui.arena_limit
        self.task_hint = tk.StringVar(self)
        self.plan_summary_label = ttk.Label(self)
        self.field = ui.field
        self.wrap_labels = ui.wrap_labels
        self._control_job = None
        ttk.Label(self, text='竞技场', font=('SimSun',23,'bold')).pack(anchor='w',pady=(0,8))
        ttk.Label(self, text='独立运行 · 结束后停留在竞技场', foreground='#5e6b52').pack(anchor='w',pady=(0,12))
        tabs = ttk.Frame(self)
        tabs.pack(fill='x',pady=(0,10))
        self.mode_buttons = {}
        for mode,label in (('common','常规设置'),('advanced','高级设置')):
            button = ttk.Button(tabs,text=label,command=lambda value=mode:self.show_mode(value))
            button.pack(side='left',padx=(0,8))
            self.mode_buttons[mode] = button
        bottom = ttk.Frame(self)
        bottom.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Label(bottom,textvariable=ui.status,foreground='#5e6b52',wraplength=550).pack(anchor='w')
        ttk.Label(bottom,textvariable=ui.step_status,wraplength=550).pack(anchor='w',pady=(5,8))
        ttk.Checkbutton(bottom,text='流程预览（不操作游戏）',variable=ui.preview).pack(anchor='w',pady=(0,8))
        controls = ttk.Frame(bottom)
        controls.pack(fill='x')
        self.save_button = ttk.Button(controls,text='保存设置',command=self.save)
        self.save_button.pack(side='left')
        self.start_button = ttk.Button(controls,text='开始竞技场',style='Primary.TButton',command=lambda:ui.start(arena_only=True))
        self.start_button.pack(side='right')
        self.stop_button = ttk.Button(controls,text='停止',command=ui.stop)
        self.stop_button.pack(side='right',padx=(0,8))
        self.pause_button = ttk.Button(controls,text='暂停',command=ui.pause)
        self.pause_button.pack(side='right',padx=(0,8))
        self.task_canvas = tk.Canvas(self,highlightthickness=0,bg='#f4f1ea')
        self.task_canvas.pack(fill='both',expand=True)
        self.task_fields = ttk.Frame(self.task_canvas)
        self._fields_window = self.task_canvas.create_window(0,0,window=self.task_fields,anchor='nw')
        self.task_fields.bind('<Configure>',lambda event:self.task_canvas.configure(scrollregion=self.task_canvas.bbox('all')))
        self.task_canvas.bind('<Configure>',self._resize)
        self.bind('<Destroy>',self._destroyed,add='+')
        self.show_mode('common')
        self._sync_controls()

    def _resize(self,event):
        self.task_canvas.itemconfigure(self._fields_window,width=event.width)
        self.ui.wrap_labels(self.task_fields,max(100,event.width-8))

    def _scroll(self,event):
        if self.task_fields.winfo_reqheight()>self.task_canvas.winfo_height():
            self.task_canvas.yview_scroll(-int(event.delta/120),'units')
        return 'break'

    def show_mode(self,mode):
        self.mode = mode
        for child in self.task_fields.winfo_children():child.destroy()
        show_arena_task(self,mode)
        self.task_canvas.yview_moveto(0)
        def bind_wheel(parent):
            parent.bind('<MouseWheel>',self._scroll,add='+')
            for child in parent.winfo_children():bind_wheel(child)
        bind_wheel(self.task_fields)
        for name,button in self.mode_buttons.items():
            button.configure(state='disabled' if name==mode else 'normal')

    def save(self):
        try:parse_battle_limit(self.arena_limit.get(),enabled=True)
        except (ValueError,tk.TclError) as error:
            messagebox.showerror('保存失败',str(error),parent=self)
            return
        self.ui.save()

    def _sync_controls(self):
        running = self.ui.running
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running and not self.ui.stopping else 'disabled')
        self.pause_button.configure(state='normal' if running and not self.ui.pending_pause and not self.ui.stopping else 'disabled',
                                    text='继续' if self.ui.paused else '暂停中' if self.ui.pending_pause else '暂停')
        self._control_job = self.ui.after(150,self._sync_controls)

    def _destroyed(self,event):
        if event.widget is self and self._control_job is not None:
            self.ui.after_cancel(self._control_job)
            self._control_job = None
