"""Grocery tool presentation. Game work is delegated to its isolated controller."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
from grocery_plan import load_catalog, load_plan, save_plan, load_state, parse_quantity
from PIL import Image, ImageTk

PAPER = '#f4f1ea'
SURFACE = '#fcfbf7'
SIDEBAR = '#eceee4'
INK = '#292d28'
MUTED = '#5e6b52'
LINE = '#cbd1bf'
ACCENT = '#ae4428'
SANS = 'Microsoft YaHei UI'
SERIF = 'SimSun'
SHOP_LABELS = {'sun': '日商店', 'moon': '月商店', 'sign': '签到商店', 'mystery': '神秘商店'}
CURRENCIES = {'sun': '日之币', 'moon': '月之币', 'sign': '签到令', 'mystery': '奇怪的石头'}


class GroceryToolView(tk.Frame):
    """Four-shop catalogue, persistent quantities and controller feedback."""

    def __init__(self, ui, parent, *, root=None, controller_factory=None, arena_factory=None):
        super().__init__(parent, bg=PAPER)
        self.ui = ui
        self.arena_factory = arena_factory
        module = sys.modules.get(type(ui).__module__)
        self.root = Path(root if root is not None else getattr(module, 'ROOT', ROOT))
        self.plan_path = self.root / 'grocery_plan.json'
        self.state_path = self.root / 'grocery_state.json'
        self.catalog = load_catalog()
        self.items = {item['key']: item for item in self.catalog}
        self.variables = {}
        self.inputs = {}
        self.errors = {}
        self.cards = {}
        self.shop_cards = {key: [] for key in SHOP_LABELS}
        self.shop_canvases = {}
        self.shop_contents = {}
        self.shop_buttons = {}
        self.photos = {}
        self._columns = {}
        self._save_job = None
        self._running = False
        self._purchase_supported = True
        self._pending = False
        self._load_error = None
        self._destroyed = False
        self.controller = None
        try:
            saved = load_plan(self.plan_path, self.catalog)
        except (OSError, ValueError, TypeError) as error:
            saved = {}
            self._load_error = f'现有预设读取失败，已保留原文件：{error}'
        self.status = tk.StringVar(self, value=self._load_error or '设置购买数量，预设会自动保存。')
        self.summary = tk.StringVar(self, value='未选择商品')
        self.balance_time = tk.StringVar(self, value='尚未读取游戏余额')
        self.purchase_notice = tk.StringVar(self, value='')
        self.balance_vars = {key: tk.StringVar(self, value='—') for key in CURRENCIES}
        self._build(saved)
        # Restore the purchase journal first. The controller then restores its
        # separately recorded balance observation, which may be more recent.
        try:
            state = load_state(self.state_path)
            if state:
                self.set_pending_state(state.get('status') != 'done')
                balances = state.get('balances_latest')
                if balances:
                    self.show_balance(balances, state.get('balances_read_at', ''))
                if state.get('status') == 'needs_review':
                    self.show_status('上轮购买结果待核对，不能自动重复购买。')
        except (OSError, ValueError, TypeError) as error:
            self.show_status(f'上轮记录读取失败，已保留原文件：{error}')
        if controller_factory is None:
            from grocery_controller import GroceryController
            controller_factory = GroceryController
        self.controller = controller_factory(ui, self, root=self.root)
        ui.grocery_tool = self.controller
        self._update_summary()
        self.bind('<Destroy>', self._on_destroy, add='+')

    def _build(self, saved):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.left = tk.Frame(self, bg=SIDEBAR, width=172, highlightthickness=1, highlightbackground=LINE)
        self.left.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        self.left.grid_propagate(False)
        self.left.columnconfigure(0, weight=1)
        self.left.rowconfigure(4, weight=1)
        tk.Label(self.left, text='小工具', bg=SIDEBAR, fg=MUTED, font=(SANS, 11), anchor='w').grid(
            row=0, column=0, sticky='ew', padx=14, pady=(17, 12))
        self.tool_buttons = {}
        tools = (('grocery', '杂货屋'), ('shortcuts', '常用入口'))
        if self.arena_factory is not None:tools += (('arena', '竞技场'),)
        for row, (key, title) in enumerate(tools, 1):
            button = tk.Button(self.left, text=title, anchor='w', relief='flat', borderwidth=0,
                               padx=15, pady=13, font=(SANS, 11), command=lambda k=key: self.show_tool(k))
            button.grid(row=row, column=0, sticky='ew', padx=6, pady=2)
            self.tool_buttons[key] = button
        footer = self.footer = tk.Frame(self.left, bg=SIDEBAR)
        footer.grid(row=5, column=0, sticky='sew', padx=12, pady=14)
        tk.Label(footer, textvariable=self.summary, bg=SIDEBAR, fg=MUTED, font=(SANS, 9),
                 wraplength=146, justify='left', anchor='w').pack(fill='x', pady=(0, 10))
        self.observe_button = ttk.Button(footer, text='读取余额', command=self._observe)
        self.observe_button.pack(fill='x', pady=(0, 7))
        self.start_button = ttk.Button(footer, text='开始购买', style='Primary.TButton', command=self._start)
        self.start_button.pack(fill='x', pady=(0, 7))
        self.new_button = ttk.Button(footer, text='新一轮', command=lambda: self._start(new_round=True))
        self.new_button.pack(fill='x', pady=(0, 7))
        self.stop_button = ttk.Button(footer, text='停止', command=self._stop, state='disabled')
        self.stop_button.pack(fill='x')
        self.right = tk.Frame(self, bg=PAPER)
        self.right.grid(row=0, column=1, sticky='nsew')
        self.right.columnconfigure(0, weight=1)
        self.right.rowconfigure(0, weight=1)
        self.grocery_page = tk.Frame(self.right, bg=PAPER)
        self.grocery_page.grid(row=0, column=0, sticky='nsew')
        self.grocery_page.columnconfigure(0, weight=1)
        self.grocery_page.rowconfigure(4, weight=1)
        tk.Label(self.grocery_page, text='杂货屋', bg=PAPER, fg=INK, font=(SERIF, 23, 'bold'),
                 anchor='w').grid(row=0, column=0, sticky='ew')
        balance_row = tk.Frame(self.grocery_page, bg=PAPER)
        balance_row.grid(row=1, column=0, sticky='ew', pady=(13, 2))
        for column, (key, title) in enumerate(CURRENCIES.items()):
            balance_row.columnconfigure(column, weight=1, uniform='balances')
            box = tk.Frame(balance_row, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
            box.grid(row=0, column=column, sticky='nsew', padx=(0, 7) if column < 3 else 0)
            tk.Label(box, text=title, bg=SURFACE, fg=MUTED, font=(SANS, 9)).pack(anchor='w', padx=9, pady=(5, 0))
            tk.Label(box, textvariable=self.balance_vars[key], bg=SURFACE, fg=INK,
                     font=(SANS, 14, 'bold')).pack(anchor='w', padx=9, pady=(0, 5))
        tk.Label(self.grocery_page, textvariable=self.balance_time, bg=PAPER, fg=MUTED,
                 font=(SANS, 9), anchor='w').grid(row=2, column=0, sticky='ew', pady=(3, 11))
        tabs = tk.Frame(self.grocery_page, bg=PAPER)
        tabs.grid(row=3, column=0, sticky='ew', pady=(0, 10))
        for key, title in SHOP_LABELS.items():
            count = sum(item['shop'] == key for item in self.catalog)
            button = tk.Button(tabs, text=f'{title}  {count}', relief='flat', borderwidth=0,
                               padx=10, pady=9, font=(SANS, 10), command=lambda k=key: self.show_shop(k))
            button.pack(side='left', padx=(0, 5))
            self.shop_buttons[key] = button
        self.shop_deck = tk.Frame(self.grocery_page, bg=PAPER)
        self.shop_deck.grid(row=4, column=0, sticky='nsew')
        self.shop_deck.columnconfigure(0, weight=1)
        self.shop_deck.rowconfigure(0, weight=1)
        for shop in SHOP_LABELS:
            canvas = tk.Canvas(self.shop_deck, bg=PAPER, highlightthickness=0, bd=0)
            canvas.grid(row=0, column=0, sticky='nsew')
            contents = tk.Frame(canvas, bg=PAPER)
            window = canvas.create_window(0, 0, anchor='nw', window=contents)
            self.shop_canvases[shop] = canvas
            self.shop_contents[shop] = contents
            contents.bind('<Configure>', lambda event, c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>', lambda event, k=shop, c=canvas, win=window: self._resize_shop(k, c, win, event.width))
            self._bind_wheel(canvas, canvas)
        for item in self.catalog:
            self._build_card(item, saved.get(item['key'], 0))
        self.status_label = tk.Label(self.grocery_page, textvariable=self.status, bg=PAPER, fg=MUTED,
                                    font=(SANS, 9), anchor='w', justify='left', wraplength=650)
        self.status_label.grid(row=6, column=0, sticky='ew', pady=(9, 0))
        self.capability_label = tk.Label(self.grocery_page, textvariable=self.purchase_notice, bg=PAPER,
                                        fg=ACCENT, font=(SANS, 10), anchor='w', justify='left', wraplength=650)
        self.capability_label.grid(row=5, column=0, sticky='ew', pady=(9, 0))
        self.capability_label.grid_remove()
        self.shortcuts_page = tk.Frame(self.right, bg=PAPER)
        self.shortcuts_page.grid(row=0, column=0, sticky='nsew')
        tk.Label(self.shortcuts_page, text='常用入口', font=(SERIF, 23, 'bold'), bg=PAPER,
                 fg=INK).pack(anchor='w', pady=(0, 20))
        self.shortcut_buttons = []
        for label, relative in (('打开项目文件夹', ''), ('打开使用说明', 'docs/使用说明.md'),
                                ('打开后台使用说明', 'docs/后台使用说明.md'),
                                ('打开后台验证结果', 'verification/验证结果.md')):
            button = ttk.Button(self.shortcuts_page, text=label,
                                command=lambda name=relative: os.startfile(ROOT / name))
            button.pack(anchor='w', pady=6)
            self.shortcut_buttons.append(button)
        tk.Label(self.shortcuts_page, text='勾选任务 → 参数 → 保存设置 → 开始执行。\n\n'
                 '流程预览只检查队列，不操作游戏。\n押镖仅接取，交付待实施；托管可靠结束判断与完整收尾待验收。',
                 bg=PAPER, fg=MUTED, font=(SANS, 10), wraplength=600, justify='left').pack(anchor='w', pady=24)
        if self.arena_factory is not None:
            self.arena_page = self.arena_factory(self.ui, self.right)
            self.arena_page.grid(row=0, column=0, sticky='nsew')
            self.ui.arena_view = self.arena_page
        self.show_shop('sun')
        self.show_tool('grocery')

    def _build_card(self, item, value):
        key, shop = item['key'], item['shop']
        card = tk.Frame(self.shop_contents[shop], bg=SURFACE, highlightthickness=1,
                        highlightbackground=LINE, width=152, height=208)
        card.grid_propagate(False)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=item['name'], bg=SURFACE, fg=INK, font=(SANS, 9),
                 wraplength=136, justify='center').grid(row=0, column=0, sticky='ew', padx=7, pady=(8, 3))
        path = Path(item.get('image_path') or ROOT / 'resources/local/grocery/image' / (item['asset'] + '.png'))
        if item['asset'] not in self.photos:
            with Image.open(path) as image:
                self.photos[item['asset']] = ImageTk.PhotoImage(image.convert('RGBA'), master=self)
        image_widget = tk.Label(card, image=self.photos[item['asset']], bg=SURFACE)
        image_widget.grid(row=1, column=0, pady=3)
        tk.Label(card, text=('购买数量' if item['shop'] == 'moon' and str(item.get('id')) in ('10800057','10840089') else '预设数量 · 待接入'), bg=SURFACE, fg=MUTED, font=(SANS, 9)).grid(row=2, column=0, pady=(4, 2))
        variable = tk.StringVar(self, value=str(value))
        spin = ttk.Spinbox(card, from_=0, to=999999, width=8, textvariable=variable, justify='center')
        spin.grid(row=3, column=0, padx=12, sticky='ew')
        error = tk.StringVar(self)
        tk.Label(card, textvariable=error, bg=SURFACE, fg=ACCENT, font=(SANS, 8),
                 wraplength=136).grid(row=4, column=0, sticky='ew', padx=5, pady=(3, 0))
        self.variables[key] = variable
        self.inputs[key] = spin
        self.errors[key] = error
        self.cards[key] = card
        self.shop_cards[shop].append(card)
        variable.trace_add('write', lambda *_: self._quantity_changed())
        spin.bind('<FocusOut>', lambda event: self._autosave())
        self._bind_wheel_tree(card, self.shop_canvases[shop])

    def _bind_wheel(self, widget, canvas):
        def wheel(event):
            amount = -int(event.delta / 120) if event.delta else 0
            if not amount and event.delta:
                amount = -1 if event.delta > 0 else 1
            canvas.yview_scroll(amount * 2, 'units')
            return 'break'
        widget.bind('<MouseWheel>', wheel, add='+')

    def _bind_wheel_tree(self, widget, canvas):
        self._bind_wheel(widget, canvas)
        for child in widget.winfo_children():
            self._bind_wheel_tree(child, canvas)

    def _resize_shop(self, shop, canvas, window, width):
        canvas.itemconfigure(window, width=width)
        columns = max(1, width // 164)
        if self._columns.get(shop) == columns:
            return
        self._columns[shop] = columns
        content = self.shop_contents[shop]
        for column in range(12):
            content.columnconfigure(column, weight=1 if column < columns else 0, uniform='cards' if column < columns else '')
        for index, card in enumerate(self.shop_cards[shop]):
            card.grid(row=index // columns, column=index % columns, sticky='n', padx=(0, 8), pady=(0, 10))

    def show_tool(self, key):
        self.selected_tool = key
        pages = {'grocery': self.grocery_page, 'shortcuts': self.shortcuts_page}
        if self.arena_factory is not None:pages['arena'] = self.arena_page
        page = pages[key]
        if key == 'arena':self.footer.grid_remove()
        else:self.footer.grid()
        page.tkraise()
        for candidate, button in self.tool_buttons.items():
            active = candidate == key
            button.configure(bg=INK if active else SIDEBAR, fg=SURFACE if active else MUTED,
                             activebackground=INK if active else LINE, activeforeground=SURFACE if active else INK)

    def show_shop(self, key):
        self.selected_shop = key
        # Canvas.tkraise raises canvas items; the Tcl widget command raises the
        # whole shop viewport above its siblings.
        self.tk.call('raise', str(self.shop_canvases[key]))
        for candidate, button in self.shop_buttons.items():
            active = candidate == key
            button.configure(bg=INK if active else SURFACE, fg=SURFACE if active else INK,
                             activebackground=INK if active else LINE, activeforeground=SURFACE if active else INK)

    def quantities(self):
        return {key: variable.get() for key, variable in self.variables.items()}

    def _parse_fields(self):
        values, invalid = {}, []
        for key, variable in self.variables.items():
            try:
                values[key] = parse_quantity(variable.get())
                self.errors[key].set('')
            except (ValueError, TypeError):
                self.errors[key].set('请输入非负整数')
                invalid.append(key)
        if invalid:
            item = self.items[invalid[0]]
            raise ValueError(f"{item['name']}：购买数量必须为非负整数")
        return values

    def validated_quantities(self):
        if self._load_error:
            raise ValueError(self._load_error)
        values = self._parse_fields()
        save_plan(self.plan_path, values, self.catalog)
        return values

    def _quantity_changed(self):
        self._update_summary()
        if self._running or self._destroyed or self._load_error:
            return
        if self._save_job is not None:
            self.ui.after_cancel(self._save_job)
        self._save_job = self.ui.after(450, self._scheduled_autosave)

    def _scheduled_autosave(self):
        self._save_job = None
        self._autosave()

    def _autosave(self):
        if self._save_job is not None:
            self.ui.after_cancel(self._save_job)
            self._save_job = None
        if self._running or self._destroyed or self._load_error:
            return
        try:
            self.validated_quantities()
        except (OSError, ValueError, TypeError) as error:
            self.show_status(f'预设未保存：{error}')
        else:
            self.show_status('预设已自动保存 · 0 表示不购买')

    def _update_summary(self):
        selected, total = 0, 0
        for variable in self.variables.values():
            try:
                value = parse_quantity(variable.get())
            except (ValueError, TypeError):
                continue
            if value:
                selected += 1
                total += value
        self.summary.set(f'已选 {selected} 件商品\n本轮共 {total} 份' if selected else '未选择商品\n数量 0 表示不购买')

    def _start(self, new_round=False):
        if self.controller is not None:
            self.controller.start(new_round=new_round)

    def _stop(self):
        if self.controller is not None:
            self.controller.stop()

    def _observe(self):
        if self.controller is not None and not self._running:
            self.controller.observe()

    def set_purchase_capability(self, supported, reason=''):
        self._purchase_supported = bool(supported)
        if supported:
            self.purchase_notice.set(reason)
            self.capability_label.grid() if reason else self.capability_label.grid_remove()
        else:
            self.purchase_notice.set('自动购买待实机验证；当前可保存预设、读取余额。')
            self.capability_label.grid()
        self._sync_controls()

    def _sync_controls(self):
        can_purchase = not self._running and self._purchase_supported
        self.start_button.configure(state='normal' if can_purchase else 'disabled')
        self.new_button.configure(state='normal' if can_purchase else 'disabled')
        self.observe_button.configure(state='disabled' if self._running else 'normal')
        self.stop_button.configure(state='normal' if self._running else 'disabled')

    def set_running(self, running):
        self._running = bool(running)
        for widget in self.inputs.values():
            widget.configure(state='disabled' if running else 'normal')
        self._sync_controls()

    def set_pending_state(self, pending):
        self._pending = bool(pending)
        self.start_button.configure(text='继续本轮' if pending else '开始购买')

    def set_resume_available(self, pending):
        self.set_pending_state(pending)

    def show_balance(self, balances, timestamp=''):
        for key in CURRENCIES:
            if key in balances and type(balances[key]) is int and balances[key] >= 0:
                self.balance_vars[key].set(f'{balances[key]:,}')
        self.balance_time.set(f'最后确认：{timestamp}' if timestamp else '上次确认的余额 · 时间未记录')

    def show_status(self, message):
        self.status.set(str(message))

    def show_progress(self, event):
        item = event.get('item') or {}
        if isinstance(item, dict):
            name = item.get('name', '')
            remaining = event.get('remaining')
            self.show_status(f"{name} · 剩余 {remaining} 份" if remaining is not None else str(event.get('message', name)))
        elif event.get('message'):
            self.show_status(event['message'])

    def flush_pending_edits(self):
        """Do not lose a valid edit when closing before the debounce expires."""
        if self._save_job is not None and not self._running and not self._destroyed:
            self._autosave()

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self.flush_pending_edits()
        self._destroyed = True
        if self._save_job is not None:
            try:
                self.ui.after_cancel(self._save_job)
            except tk.TclError:
                pass
            self._save_job = None


def build_tools(ui, parent, *, root=None, controller_factory=None):
    from arena_tool_ui import ArenaToolView
    view = GroceryToolView(ui, parent, root=root, controller_factory=controller_factory, arena_factory=ArenaToolView)
    view.pack(fill='both', expand=True)
    ui.grocery_view = view
    return view
