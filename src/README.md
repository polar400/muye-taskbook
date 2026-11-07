# 程序源码

桌面界面、每日任务流程、后台工作进程和适配器。主启动入口为仓库根目录的 `启动.cmd`，对应 `src/app.py`。资源、vendor 依赖和运行数据保持以仓库根目录定位。

## 文件用途

| 文件 | 作用 |
| --- | --- |
| [adapters/background_window.py](adapters/background_window.py) | Windows 后台截图与窗口输入 |
| [adapters/local_ocr.py](adapters/local_ocr.py) | 本地 OCR 与模板匹配 |
| [adapters/midscene.mjs](adapters/midscene.mjs) | Midscene 前台输入与识别适配 |
| [app.py](app.py) | 桌面主界面、设置与任务队列 |
| [arena_daily.py](arena_daily.py) | 竞技场每日任务识别与执行 |
| [arena_lower_probe.py](arena_lower_probe.py) | 竞技场下方按钮定位探测 |
| [arena_pointer_pe.py](arena_pointer_pe.py) | 竞技场指针试验的 PE 信息解析 |
| [arena_settings.py](arena_settings.py) | 竞技场模式与场数参数 |
| [arena_task.py](arena_task.py) | 竞技场任务调度 |
| [arena_task_ui.py](arena_task_ui.py) | 竞技场任务说明面板 |
| [arena_tokens.py](arena_tokens.py) | 竞技场令牌图像识别 |
| [arena_tool_ui.py](arena_tool_ui.py) | 竞技场独立操作面板 |
| [arena_virtual_pointer.py](arena_virtual_pointer.py) | 竞技场虚拟鼠标试验 |
| [core/resource.mjs](core/resource.mjs) | 任务资源读取与配置校验 |
| [core/tasker.mjs](core/tasker.mjs) | 任务队列与节点执行 |
| [failure_archive.py](failure_archive.py) | 故障记录、截图与错误归档 |
| [flows.mjs](flows.mjs) | Midscene 前台每日任务流程 |
| [grocery_controller.py](grocery_controller.py) | 杂货屋界面与工作进程控制 |
| [grocery_driver.py](grocery_driver.py) | 杂货屋后台操作驱动 |
| [grocery_live.py](grocery_live.py) | 杂货屋实时执行与记录 |
| [grocery_plan.py](grocery_plan.py) | 杂货屋兑换计划与状态校验 |
| [grocery_recognition.py](grocery_recognition.py) | 杂货屋物品识别 |
| [grocery_scroll.py](grocery_scroll.py) | 杂货屋列表滚动与页面匹配 |
| [grocery_tool_ui.py](grocery_tool_ui.py) | 杂货屋工具界面 |
| [grocery_vision.py](grocery_vision.py) | 杂货屋视觉状态识别 |
| [grocery_worker.py](grocery_worker.py) | 杂货屋独立后台进程 |
| [local_flows.py](local_flows.py) | 本地每日任务执行流程 |
| [log_retention.py](log_retention.py) | 运行日志与故障资料的15日清理 |
| [mission_desk_ui.py](mission_desk_ui.py) | 木叶任务簿桌面工作台 |
| [native_worker.py](native_worker.py) | 本地后台任务工作进程 |
| [ranked_numbers.py](ranked_numbers.py) | 排位战力与次数数字识别 |
| [ranked_pipeline.py](ranked_pipeline.py) | 排位战 Maa 流程调度 |
| [ranked_policy.py](ranked_policy.py) | 排位匹配参数与策略 |
| [ranked_vision.py](ranked_vision.py) | 排位战界面识别 |
| [survival_plan.py](survival_plan.py) | 生存演习等级与积分计划 |
| [survival_reset.py](survival_reset.py) | 生存演习重置判断 |
| [survival_start.py](survival_start.py) | 生存演习启动与入口处理 |
| [team_instance_challenge.py](team_instance_challenge.py) | 组队副本挑战流程 |
| [team_instance_daily.py](team_instance_daily.py) | 组队副本每日任务流程 |
| [team_instance_rewards.py](team_instance_rewards.py) | 组队副本领奖流程 |
| [team_instance_settlement.py](team_instance_settlement.py) | 组队副本结算识别 |
| [team_instance_task.py](team_instance_task.py) | 组队副本任务调度 |
| [team_instance_ui.py](team_instance_ui.py) | 组队副本设置与说明界面 |
| [wanted_task.py](wanted_task.py) | 通缉任务接取与完成流程 |
| [wanted_task_ui.py](wanted_task_ui.py) | 通缉任务说明 |
| [welfare_task.py](welfare_task.py) | 福利大厅领取流程 |
| [welfare_task_ui.py](welfare_task_ui.py) | 福利大厅任务说明 |
| [welfare_tool.py](welfare_tool.py) | 福利大厅独立工具 |
| [welfare_vision.py](welfare_vision.py) | 福利大厅图像识别 |
| [worker.mjs](worker.mjs) | Midscene 前台工作进程与暂停控制 |
