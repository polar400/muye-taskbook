"""Explicit window-only live verification. Never starts a game task."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    from app import game_windows
    from adapters.background_window import BackgroundWindow, centered_window_position, u
    windows = game_windows()
    if len(windows) != 1:
        raise RuntimeError('实测需要唯一且非最小化的游戏窗口')
    window = BackgroundWindow(windows[0][0])
    report = {'status': 'running', 'gameTaskInputs': 0, 'cases': []}
    destination = ROOT/'verification/startup-calibration-live-20261106.json'
    try:
        for label, setup in (
            ('short', [(1960, 1200), (1920, 1122)]),
            ('tall', [(1920, 1122), (1920, 1147)]),
            ('already-calibrated', []),
        ):
            for size in setup:
                window.check()
                x, y = centered_window_position(window.calibration_bounds(), size)
                if not u.SetWindowPos(window.root, None, x, y, *size, 0x14):
                    raise RuntimeError('测试准备无法设置根窗口')
                time.sleep(1.6)
            row = {'label': label, 'before': window.measure(), 'events': []}
            report['cases'].append(row)
            image = window.calibrate(log=lambda message: (row['events'].append(message), print(message, flush=True)))
            row['samples'] = []
            for _ in range(3):
                time.sleep(.3)
                row['samples'].append(window.measure())
            assert len(set(row['samples'])) == 1, row
            assert row['samples'][0][2:4] == (1920, 1015), row
            # Re-capture after stability checks, using production boundary checks.
            image = window.capture()
            assert image.shape[:2] == (1015, 1920), image.shape
            path = ROOT/f'verification/startup-calibration-{label}-20261106.png'
            window.save(image, path)
            row.update(shape=image.shape, screenshot=str(path.relative_to(ROOT)),
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        report['sourceSha256'] = hashlib.sha256((ROOT/'adapters/background_window.py').read_bytes()).hexdigest()
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(destination, flush=True)


if __name__ == '__main__':
    main()
