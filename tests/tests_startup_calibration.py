"""Window-only startup regressions; no game input or desktop changes."""
import unittest
from unittest.mock import Mock, patch

from adapters.background_window import BackgroundWindow


class StartupCalibrationTests(unittest.TestCase):
    def window(self, profile):
        window = object.__new__(BackgroundWindow)
        window.root = 42
        window.check = Mock()
        window.calibration_bounds = Mock(return_value=(-2560, 0, 0, 1528))
        state = [0, 106, 1920, 1032, 1920, 1139]
        requests = []

        def resize(hwnd, z, x, y, width, height, flags):
            self.assertEqual((hwnd, z, flags), (42, None, 0x14))
            self.assertEqual((x, y), (-2560 + (2560-width)//2, (1528-height)//2))
            requests.append((width, height))
            cw, ch = profile(width, height)
            state[:] = [0, 106, cw, ch, width, height]
            return True

        window.measure = lambda: tuple(state)
        window.capture = Mock(return_value=Mock(shape=(1015, 1920, 3)))
        return window, requests, resize

    def run_calibration(self, window, resize):
        with patch('adapters.background_window.u.IsZoomed', return_value=False), \
             patch('adapters.background_window.u.SetWindowPos', side_effect=resize), \
             patch('adapters.background_window.time.sleep'):
            return window.calibrate()

    def test_scrollbar_history_is_reset_before_height_search(self):
        previous = [1920, 1140]

        def profile(width, height):
            old_width = previous[0]
            previous[:] = [width, height]
            if width == 1920 and old_width > width:
                return 1920, 1015
            if width == 1920 and height < 1140:
                return 1894, height-132
            return width, height-106

        window, requests, resize = self.window(profile)
        self.run_calibration(window, resize)
        self.assertEqual(window.measure()[2:4], (1920, 1015))
        self.assertEqual(requests, [(1920, 1147), (1946, 1147), (1920, 1147)])
        self.assertLessEqual(len(requests), 12)
        window.capture.assert_called_once()

    def test_reset_restores_measured_physical_outer_size(self):
        # Windows rounds the requested 1147 to 1148 on the tested display.
        window, requests, base_resize = self.window(lambda w, h: (w, h-106))
        physical = [1920, 1140]

        def resize(hwnd, z, x, y, width, height, flags):
            old_width = physical[0]
            base_resize(hwnd, z, x, y, width, height, flags)
            physical[:] = [width, (height+1)//2*2]
            client = (1920, 1015) if width == 1920 and old_width > width else (width, physical[1]-107)
            window.measure = lambda: (0, 106, *client, *physical)
            return True

        self.run_calibration(window, resize)
        self.assertEqual(requests, [(1920, 1147), (1946, 1148), (1920, 1148)])

    def test_reset_resize_failure_stops_without_capture(self):
        window, requests, resize = self.window(lambda w, h: (w, h-106))

        def fail_widen(*args):
            if args[4] > 1920:
                return False
            return resize(*args)

        with self.assertRaisesRegex(RuntimeError, '无法调整'):
            self.run_calibration(window, fail_widen)
        window.capture.assert_not_called()

    def test_permanently_unreachable_canvas_still_stops(self):
        window, requests, resize = self.window(lambda w, h: (1894, 990))
        with self.assertRaisesRegex(RuntimeError, '停止后续任务|停止校准'):
            self.run_calibration(window, resize)
        self.assertLessEqual(len(requests), 12)
        window.capture.assert_not_called()

    def test_successful_resize_without_correct_screenshot_is_rejected(self):
        window, _, resize = self.window(lambda w, h: (1920, 1015))
        window.capture.return_value = Mock(shape=(990, 1894, 3))
        with self.assertRaisesRegex(RuntimeError, '截图尺寸不一致'):
            self.run_calibration(window, resize)

    def test_both_layout_branches_unreachable_do_not_loop(self):
        def profile(w, h):
            if h < 1140:
                return w-26, h-132
            return w, h-106
        window, requests, resize = self.window(profile)
        with self.assertRaisesRegex(RuntimeError, '停止后续任务|停止校准'):
            self.run_calibration(window, resize)
        self.assertLessEqual(len(requests), 12)
        window.capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
