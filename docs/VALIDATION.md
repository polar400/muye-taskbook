# v0.2.0-rc.2 目录整理验证

2026-11-07：保留此前公开版本的全部1,063个文件，迁移140个文件；根目录收敛为7个入口及必要配置文件。图标、模型和既有图像资源逐一比对未变，194个项目 Python 文件通过 AST 语法检查，Node 源码通过语法检查。

迁移相关的62项 Python 检查通过，覆盖日志保留、故障归档、后台进程、杂货屋控制与计划、启动校准，以及 Python / Node 两种工作进程的任务排序预览。29项 Node 核心与前台流程测试通过。Windows 桌面界面启动、资源根目录定位检查通过。

复核命令（在仓库根目录运行）：

```powershell
python -B -m unittest tests.tests_release tests.tests_failure_archive tests.tests_native_failure tests.tests_task_order.TaskOrderTests.test_both_worker_previews_follow_sorted_checked_tasks tests.tests_grocery_controller tests.tests_grocery_worker tests.tests_grocery_plan tests.tests_startup_calibration
npm test
node --check src/worker.mjs
```

## 已有测试限制

扩展检查发现以下8项界面测试在整理前的候选副本和整理后的副本中均失败，涉及旧任务数量、页面选择或布局断言。本次不改变这些业务行为，也未将整个测试集标记为通过：

- tests_task_order.TaskOrderTests.test_drag_both_directions_keeps_settings_and_execution_order
- tests_task_order.TaskOrderTests.test_old_and_stale_config_orders
- tests_ui_resize.ResizeTests.test_task_changes_still_refresh_scroll_region_at_same_window_size
- tests_survival_plan.TaskSettingsTests.test_advanced_stays_in_task_and_preserves_choices_across_tabs
- tests_team_instance_ui.TeamInstanceUITests.test_old_config_appends_unselected
- tests_wanted_ui.WantedUITests.test_old_config_keeps_selection_and_appends_new_option
- tests_wanted_ui.WantedUITests.test_six_task_rows_fit_at_supported_sizes
- tests_wanted_ui.WantedUITests.test_task_is_selectable_and_common_and_advanced_render

整理后模块位于 tests 包内，执行时加 tests. 前缀。部分旧图像回放还需要私有 verification 素材。完整每日任务链与全新电脑联网安装仍待实测。
