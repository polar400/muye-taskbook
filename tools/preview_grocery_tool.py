"""Show the actual desktop grocery page with isolated storage and no game IO."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
import app


def main():
    with tempfile.TemporaryDirectory(prefix='grocery-preview-', dir=ROOT/'verification') as folder:
        with patch.object(app, 'ROOT', Path(folder)), patch.object(app, 'game_windows', return_value=[]), \
             patch.object(app.subprocess, 'Popen', side_effect=AssertionError('Preview cannot launch workers')):
            ui = app.App()
            ui.title('杂货屋 · 研发预览（预设隔离，不操作游戏）')
            ui.notebook.select(ui.help_panel)
            ui.update_nav()
            ui.update()
            print('Grocery preview ready. All storage is isolated; no game workers are allowed.', flush=True)
            ui.mainloop()


if __name__ == '__main__':
    main()
