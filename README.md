<p align="center">
  <img src="resources/app-icons/naruto-chibi-20261105.png" width="256" alt="木叶任务簿应用图标" />
</p>
<h1 align="center">木叶任务簿</h1>
<p align="center"><em>🍃 火影忍者 Online 每日任务助手 🍃</em></p>
<p align="center">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB" />
  <img alt="Windows x64" src="https://img.shields.io/badge/platform-Windows_x64-8A2BE2" />
  <img alt="日志保留15天" src="https://img.shields.io/badge/日志保留-15天-ae4428" />
  <img alt="发布候选" src="https://img.shields.io/badge/status-发布候选-orange" />
</p>

**支持火影忍者 Online 的 Windows 每日任务助手。** 默认使用本地后台截图、OCR 和窗口消息输入。保留应用原有图标和木叶任务簿界面风格。完整每日任务链尚未全部实机验收；iOS、Android、macOS 和 Linux 暂无可用发行版。

## 下载与启动

[下载 Windows x64 依赖随附包](https://github.com/polar400/muye-taskbook/releases/download/v0.2.0-rc.1/MuyeTaskbook-Windows-x64-Python314.zip) · [全部发行文件与校验值](https://github.com/polar400/muye-taskbook/releases/tag/v0.2.0-rc.1)

当前为预发布候选版本；Windows 包仍需安装 Python，并非免安装 EXE。

Windows 依赖随附包：安装 **Windows x64 Python 3.14（含 Tkinter）** 后，在解压目录运行 `安装Python依赖.cmd`，再双击 `启动.cmd`。该包随附原项目 vendor 中的 MaaFramework 与 NumPy，Pillow 由安装脚本补齐；它不是免安装 EXE。

源码包：先运行 `安装Python依赖.cmd` 安装锁定版本的依赖至 vendor，再运行 `启动.cmd`。下载依赖需要网络。若仅使用默认本地后台，无需 Node 或模型 API。

1. 在 360 游戏大厅登录，停留木叶村主页，游戏不能最小化。
2. 在助手设置里选择窗口和“本地后台（免API）”。
3. 首次只选择一项任务；先运行流程预览，再进行游戏内验证。预览不会操作游戏，也不等于任务完成。

可选 Midscene 前台方式需要 Node.js：运行 `安装依赖.cmd`，按[使用说明](使用说明.md)配置。它会使用真实鼠标键盘和模型服务。

## 本次整理

- 运行记录只显示当前过程、状态和本次异常，不输出历史错误次数。
- 日志及独立故障归档保留北京时间最近 15 个自然日，含当天。每天首次写日志时从最旧日期清理；关闭期间不执行清理，重新打开后执行。故障数据库、详情、关联截图同步删除。
- `verification` 是开发验证目录，包含部分功能生成的截图，不作为 logs 备份整体删除，以免破坏测试素材和授权状态；其容量需另行管理。
- 原目录未修改；开发脚本、测试、资源、资料保留。个人配置、历史日志和验证资料完整保存在本地私有备份中，没有放进公开候选包。

## 文档与验证

[使用说明](使用说明.md) · [后台使用说明](后台使用说明.md) · [架构说明](架构说明.md) · [技术文档](技术文档.md) · [发布说明](发布说明.md)

```powershell
python -B -m unittest tests_release tests_failure_archive tests_native_failure
node --test tests.mjs
```

部分既有离线测试需要原 `verification` 截图，源码候选包不附带个人实机记录；维护者可从私有完整备份恢复。不得把这些离线检查解释为游戏全流程通过。押镖目前仅接取，托管可靠收尾等范围以技术文档为准。

## 授权与素材

未擅自为原代码选择开源许可证。第三方依赖自带各自许可；游戏素材、图标来源及公开再分发权限尚需作者核对，见[第三方说明](THIRD_PARTY_NOTICES.md)。本项目不代表游戏官方。
