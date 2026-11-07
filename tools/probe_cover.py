"""Local test fixture; contains no user data and performs no game actions."""
import tkinter as tk
root=tk.Tk()
root.title('火影助手 · 后台验证遮挡窗口')
root.geometry('1250x750+330+70')
root.configure(bg='#f0f5fa')
tk.Label(root,text='后台兼容性验证',font=('Microsoft YaHei UI',26),bg='#f0f5fa').pack(pady=80)
tk.Label(root,text='此窗口用于遮挡游戏。测试应保持它在前台，且不移动真实鼠标。',font=('Microsoft YaHei UI',14),bg='#f0f5fa').pack(pady=15)
tk.Entry(root,font=('Microsoft YaHei UI',18),width=40).pack(pady=30)
root.mainloop()
