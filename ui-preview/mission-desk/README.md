# 木叶任务簿：火影忍者online助手网页原型

本轮交付一个可本地运行的任务工作台。用户首要任务按现有项目推定为：勾选及排序每日任务、调整参数、开始后观察运行状态，并能暂停或停止。

## 打开与启动

1. 双击本目录 `预览.cmd` 或 `index.html`，即可在默认浏览器离线打开；无安装或构建步骤。
2. 当前本地预览：<http://127.0.0.1:4175>。
3. 若本地服务已退出，可运行：

```powershell
node "D:\火影忍者online\ui-preview\mission-desk\server.mjs"
```

服务仅绑定 127.0.0.1。端口已被本预览占用时，直接打开地址即可，不要重复启动。

## 操作

- 复选框决定是否执行演示；任务名称和“参数”入口决定正在编辑的任务。
- 编辑任务行内的上下箭头调整完整队列顺序。
- 常规／高级标签切换参数；超出范围或队列为空时阻止开始并提示。
- “保存到此浏览器”仅写入专用 localStorage 键 `naruto-mission-desk-preview-v1`；刷新后可恢复。
- “开始演示”启动所选队列的定时状态演示，可暂停、继续、停止。
- “模拟识别失败”保留中断状态，并停止后续演示，不自动重放。
- 运行记录支持自动跟随、滚轮查看历史，以及“日志全文”弹窗。全文为只读文本，可选中复制。
- 手机运行时优先显示运行记录，队列和参数折叠为可展开摘要；底部保留当前步骤、暂停／继续和停止。
- 导航可跳转到面板或运行记录；说明弹窗解释使用方式和演示边界。

## 内容与边界

- 六个任务名称来自本轮读取的 `resources/tasks.json`，参数规则来自技术文档及现有界面代码，包括新增通缉任务的界面说明。
- 初始数值为项目默认值，不是用户当前 config.json 的值；日期来自浏览器本地时间，日志时间为演示发生时间。
- 不读取、修改项目用户配置，不启动任何游戏工作进程，不调用 OCR、Maa 或游戏窗口接口。
- 计时器仅按任务演示几个步骤，不模拟真实战斗耗时、实际挑战场数或真实识别结果。配置输入、校验、保存与读取可交互；实际任务执行未接入。
- 押镖只显示接取演示，交付待实施；托管结束及收尾的真实验收状态明确保留，网页不会把它们报告为游戏任务完成。
- 图标为本地 SVG 图形；字体使用系统黑体与宋体回退，无外部字体、图片、视频或网络依赖。
- 原有 Tkinter 页面、游戏脚本和此前 scroll-studies 网页不由本原型替换。

## 文件

| 文件 | 用途 |
| --- | --- |
| index.html | 工作台结构与可访问性标签 |
| styles.css | 纸墨与朱橙视觉、响应式布局、运行布局、减少动态效果 |
| app.js | 队列、参数、浏览器保存、演示状态机、日志与弹窗 |
| mark.svg | 本地图形标记 |
| server.mjs | 可选静态预览服务 |
| 预览.cmd | 双击打开离线 HTML |
| browser-check.js | 浏览器交互验收脚本 |
| browser-results.json | 最终交互验收结果 |
| responsive-results.json | 四个视口的页面宽度检查 |
| accessibility-results.json | 最终自动无障碍检查原始输出 |
| 设计与评审.md | 三个方向、设计定义、三轮独立评审与剩余差距 |
| 验证与交接.md | 已验证、未验证、需决定及共同状态更新摘要 |

`desktop-r1/r2/r3.png`、`mobile-r1/r2/r3.png` 和运行态截图保留设计评审证据；`final-desktop.png`、`final-mobile.png`、`final-mobile-running.png` 为交付截图。

浏览器检查运行方式（先启动预览服务，安装环境需有 agent-browser）：

```powershell
agent-browser --session mission-desk-qa open http://127.0.0.1:4175
agent-browser --session mission-desk-qa set viewport 1440 1000
$source = Get-Content -LiteralPath "D:\火影忍者online\ui-preview\mission-desk\browser-check.js" -Raw
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($source))
agent-browser --session mission-desk-qa eval -b $encoded
```

检查会修改此 QA 浏览器的专用演示配置，不应在用户正在体验的同一浏览器会话中执行。
