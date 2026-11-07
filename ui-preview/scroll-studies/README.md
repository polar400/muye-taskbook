# 滚动交互网页预览

独立的简约灰白网页原型，包含六种可操作的滚动演示。不接入 Tkinter、游戏脚本、任务执行、识别接口或用户配置。

## 打开方式

- 直接双击本目录的 `index.html`，不需要安装依赖或联网。
- 本轮本地预览地址：<http://127.0.0.1:4173>。如服务器已退出，在本目录运行 `node server.mjs` 再访问。
- 左侧导航跳到对应演示；窄屏时导航位于顶部。
- 吸附演示需将鼠标放入画框内滚动，也可点击底部圆点和箭头。
- “减少动效”切换到静态呈现，自动尊重系统的减少动态效果偏好。

## 当前已实现

| 效果 | 行为 |
| --- | --- |
| Scroll-triggered | 卡片进入视口自动淡入并上移，滚动往返不重播 |
| Scroll-linked | 顶部整页阅读进度；本段进度、圆点和方块随滚动推进、停住或倒放 |
| Parallax | 远景、中景、近景使用不同位移速度 |
| Sticky | 注释卡片在所属区块内吸顶，到达区块末尾自然离开 |
| Scroll Snap | 独立画框内三个整屏区块自动对齐，支持圆点和前后按钮；边界可继续滚动页面 |
| Horizontal Scroll | 垂直滚动驱动四张卡片水平移动，最后一张可完整到达，随后恢复页面滚动 |

## 文件及验证

- `index.html`：结构和演示文案。
- `styles.css`：灰白样式、响应式布局、入场动画、吸顶及吸附。
- `script.js`：`update` 更新滚动进度与位移，IntersectionObserver 负责一次入场，`goToSnap` / `updateSnap` 控制吸附导航，`applyMotionPreference` 控制减少动效。
- `server.mjs`：仅绑定 127.0.0.1 的静态预览服务，只提供页面及两个资源文件。
- `browser-check.js`：在新加载的桌面预览页中运行的浏览器测量检查。
- `mouse-check.mjs`：连接本轮独立 QA 浏览器的本地调试地址，验证明确坐标的真实滚轮输入。
- `验证记录.md`：当前验证结果及可交接摘要。
- `preview-desktop.png` / `preview-mobile.png` / `preview-snap.png`：实际浏览器截图。

PowerShell 下运行桌面浏览器检查（需安装 agent-browser，先打开独立测试会话）：

```powershell
agent-browser --session scroll-studies-qa open http://127.0.0.1:4173
agent-browser --session scroll-studies-qa set viewport 1440 900
$source = Get-Content -LiteralPath './browser-check.js' -Raw
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($source))
agent-browser --session scroll-studies-qa eval -b $encoded
```

本轮仅验证 Chromium 桌面浏览器及其 375 像素窄屏模拟；其他浏览器与真实移动设备待验证。此网页为独立预览，接入 Tkinter 待另行明确需求。
