"""Open an isolated UI preview without changing game state or user settings."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'src'), str(Path(__file__).resolve().parents[1])]
import app

with tempfile.TemporaryDirectory(prefix='ui-preview-',dir=app.ROOT/'verification') as folder:
    path=Path(folder)
    config=app.ROOT/'config.json'
    if config.exists():(path/'config.json').write_bytes(config.read_bytes())
    with patch.object(app,'ROOT',path),patch.object(app.App,'refresh_windows'):
        ui=app.App()
        ui.title('界面验证 - 每日任务助手（三栏布局）')
        ui.log('界面验证：任务流程、任务设置和运行日志在同一页显示。')
        ui.log('界面验证：拖动左侧手柄可以调整任务顺序。')
        ui.log('界面验证：分隔条可调节三栏比例，缩放窗口后自动适配。')
        ui.log('界面验证：取消自动滚动后，可以翻阅历史记录。')
        ui.start_button.configure(state='disabled')
        ui.after(240000,ui.destroy)
        ui.mainloop()
