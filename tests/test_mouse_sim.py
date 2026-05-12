"""鼠标模拟模块测试。"""

import pytest
from src.mouse_sim import MouseSimulator, SpeedCurve, curve_from_string


class TestMouseSimulator:
    def test_init_defaults(self):
        m = MouseSimulator()
        assert m.sensitivity == 1.0
        assert m.scroll_sensitivity == 1.0
        assert m.curve == SpeedCurve.LINEAR
        assert m.base_speed == 800.0

    def test_init_custom(self):
        m = MouseSimulator(sensitivity=2.0, scroll_sensitivity=0.5,
                           curve=SpeedCurve.QUADRATIC, base_speed=1200.0)
        assert m.sensitivity == 2.0
        assert m.scroll_sensitivity == 0.5
        assert m.curve == SpeedCurve.QUADRATIC
        assert m.base_speed == 1200.0

    def test_move_zero_stick_no_movement(self):
        """摇杆归零时不应报错。"""
        m = MouseSimulator()
        m.move(0.0, 0.0, 0.016)

    def test_move_with_zero_dt(self):
        """dt=0 时应安全返回。"""
        m = MouseSimulator()
        m.move(0.5, 0.5, 0.0)

    def test_move_with_negative_dt(self):
        m = MouseSimulator()
        m.move(0.5, 0.5, -0.01)

    def test_click_methods_dont_crash(self):
        """点击方法调用不报错（不验证实际点击）。"""
        m = MouseSimulator()
        m.click_left()
        m.click_right()
        m.click_middle()

    def test_scroll(self):
        m = MouseSimulator(scroll_sensitivity=2.0)
        m.scroll(0, -1)
        m.scroll(1, 1)
        m.scroll(0, 0)

    def test_press_release(self):
        m = MouseSimulator()
        m.press_left()
        m.release_left()
        m.press_right()
        m.release_right()

    def test_drag_sequence(self):
        m = MouseSimulator()
        m.drag_start()
        m.drag_move(0.5, 0.0, 0.016)
        m.drag_end()

    def test_apply_curve_linear(self):
        m = MouseSimulator(curve=SpeedCurve.LINEAR)
        assert m._apply_curve(0.5) == pytest.approx(0.5)
        assert m._apply_curve(1.0) == pytest.approx(1.0)
        assert m._apply_curve(0.0) == pytest.approx(0.0)

    def test_apply_curve_quadratic(self):
        m = MouseSimulator(curve=SpeedCurve.QUADRATIC)
        assert m._apply_curve(0.5) == pytest.approx(0.25)
        assert m._apply_curve(1.0) == pytest.approx(1.0)

    def test_apply_curve_cubic(self):
        m = MouseSimulator(curve=SpeedCurve.CUBIC)
        assert m._apply_curve(0.5) == pytest.approx(0.125)
        assert m._apply_curve(1.0) == pytest.approx(1.0)

    def test_curve_from_string(self):
        assert curve_from_string("linear") == SpeedCurve.LINEAR
        assert curve_from_string("quadratic") == SpeedCurve.QUADRATIC
        assert curve_from_string("cubic") == SpeedCurve.CUBIC
        assert curve_from_string("unknown") == SpeedCurve.LINEAR
        assert curve_from_string("") == SpeedCurve.LINEAR
