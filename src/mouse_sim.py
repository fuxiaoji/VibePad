"""鼠标模拟模块。

将手柄摇杆输入转换为鼠标移动、滚轮和点击。
使用 pynput 底层控制，避免 pyautogui 的故障安全 corner 检测。
"""

from __future__ import annotations

import time
from enum import Enum, auto

from pynput.mouse import Controller, Button


class SpeedCurve(Enum):
    """光标速度曲线。"""
    LINEAR = auto()
    QUADRATIC = auto()
    CUBIC = auto()


class MouseSimulator:
    """鼠标模拟器。

    用法:
        mouse = MouseSimulator(sensitivity=1.0, curve=SpeedCurve.LINEAR)
        mouse.move(stick_x, stick_y, delta_time)
        mouse.click_left()
        mouse.scroll(0, -1)  # 向下滚动
    """

    def __init__(
        self,
        sensitivity: float = 1.0,
        scroll_sensitivity: float = 1.0,
        curve: SpeedCurve = SpeedCurve.LINEAR,
        base_speed: float = 800.0,   # 基础速度 (像素/秒)，摇杆推满时
        speed_boost: float = 2.0,    # 按住加速倍率
    ):
        self.sensitivity = sensitivity
        self.scroll_sensitivity = scroll_sensitivity
        self.curve = curve
        self.base_speed = base_speed
        self.speed_boost = speed_boost
        self._speed_boost_active = False
        self._controller = Controller()
        self._scroll_accum_x = 0.0
        self._scroll_accum_y = 0.0

    # --- 光标移动 ---

    def move(self, stick_x: float, stick_y: float, dt: float):
        """根据摇杆偏移量移动光标。

        Args:
            stick_x: 摇杆X轴 [-1.0, 1.0]
            stick_y: 摇杆Y轴 [-1.0, 1.0]
            dt: 距上次移动的时间间隔（秒）
        """
        if dt <= 0:
            return

        # 计算速度向量
        magnitude = (stick_x ** 2 + stick_y ** 2) ** 0.5
        if magnitude < 0.001:
            return

        speed = self._apply_curve(magnitude) * self.base_speed * self.sensitivity
        if self._speed_boost_active:
            speed *= self.speed_boost
        dx = stick_x / magnitude * speed * dt
        dy = stick_y / magnitude * speed * dt

        self._controller.move(int(dx), int(dy))

    # --- 点击 ---

    def click_left(self):
        self._controller.click(Button.left, 1)

    def click_right(self):
        self._controller.click(Button.right, 1)

    def click_middle(self):
        self._controller.click(Button.middle, 1)

    def press_left(self):
        self._controller.press(Button.left)

    def release_left(self):
        self._controller.release(Button.left)

    def press_right(self):
        self._controller.press(Button.right)

    def release_right(self):
        self._controller.release(Button.right)

    # --- 拖拽 ---

    def drag_start(self):
        self._controller.press(Button.left)

    def drag_move(self, stick_x: float, stick_y: float, dt: float):
        self.move(stick_x, stick_y, dt)

    def drag_end(self):
        self._controller.release(Button.left)

    # --- 滚轮 ---

    def scroll(self, dx: float, dy: float):
        """滚动鼠标滚轮。

        Args:
            dx: 水平滚动量（正=右）
            dy: 垂直滚动量（正=上）
        """
        self._scroll_accum_x += dx * self.scroll_sensitivity
        self._scroll_accum_y += dy * self.scroll_sensitivity

        ix = int(self._scroll_accum_x)
        iy = int(self._scroll_accum_y)

        if ix or iy:
            self._controller.scroll(ix, iy)
            self._scroll_accum_x -= ix
            self._scroll_accum_y -= iy

    # --- 速度加速 ---

    def set_speed_boost(self, active: bool):
        """启用/禁用光标加速（按住 RT 时加速）。"""
        self._speed_boost_active = active

    # --- 内部 ---

    def _apply_curve(self, magnitude: float) -> float:
        """对摇杆幅值施加速度曲线。"""
        if self.curve == SpeedCurve.LINEAR:
            return magnitude
        elif self.curve == SpeedCurve.QUADRATIC:
            return magnitude ** 2
        elif self.curve == SpeedCurve.CUBIC:
            return magnitude ** 3
        return magnitude


def curve_from_string(name: str) -> SpeedCurve:
    """从配置字符串解析速度曲线。"""
    mapping = {
        "linear": SpeedCurve.LINEAR,
        "quadratic": SpeedCurve.QUADRATIC,
        "cubic": SpeedCurve.CUBIC,
    }
    return mapping.get(name.lower(), SpeedCurve.LINEAR)
