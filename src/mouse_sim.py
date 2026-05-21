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
        if not self._click_via_uia():
            self._controller.click(Button.left, 1)

    def click_right(self):
        if not self._click_via_uia():
            self._controller.click(Button.right, 1)

    def click_middle(self):
        if not self._click_via_uia():
            self._controller.click(Button.middle, 1)

    def click_via_uia(self, debug: bool = False) -> bool:
        """在光标位置通过 UIA 点击，绕过 UIPI 限制。

        用于 OSK 等以 UIAccess 权限运行、拒绝 SendInput 的窗口。
        Returns True 表示已通过 UIA 处理点击，False 表示应使用普通点击。
        """
        return self._click_via_uia(debug=debug)

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

    def _click_via_uia(self, debug: bool = False) -> bool:
        """通过 UI Automation 在光标位置点击。

        遍历祖先链检测是否属于 OSK 等高权限窗口，
        如果是则用 UIA Click() 绕过 UIPI 限制。

        Returns True 表示点击已被 UIA 处理。
        """
        try:
            import ctypes.wintypes
            _ole32 = ctypes.windll.ole32
            _ole32.CoInitializeEx(None, 0x2)  # STA, 重复调用无害
        except Exception:
            pass
        try:
            import uiautomation as auto
            x, y = self._controller.position
            ctrl = auto.ControlFromPoint(x, y)
            if ctrl is None:
                if debug:
                    print("[UIA] ControlFromPoint 返回 None")
                return False

            # 收集祖先链用于调试
            chain_info: list[str] = []
            ancestor = ctrl
            target_ctrl = ctrl  # 最深层元素，用于最终点击
            for i in range(20):
                try:
                    cn = getattr(ancestor, "ClassName", "") or ""
                    name = ancestor.Name or ""
                    ct = ancestor.ControlTypeName or ""
                    chain_info.append(
                        f"  [{i}] {ct} cls={cn} name=\"{name[:60]}\""
                    )
                    name_compact = name.replace(" ", "").replace("-", "")
                    cn_lower = cn.lower()
                    if any(kw in cn_lower or kw in name_compact.lower() for kw in [
                        "osk", "tipband", "tipscreen",
                        "onscreenkeyboard", "screenkeyboard",
                        "屏幕键盘", "osk",
                    ]):
                        if debug:
                            print("[UIA] ✓ OSK 检测成功，执行 UIA Click")
                            for line in chain_info:
                                print(line)
                        ctrl.Click()
                        return True
                    ancestor = ancestor.GetParentControl()
                    if ancestor is None:
                        break
                except Exception:
                    break

            if debug:
                print(f"[UIA] ✗ 未检测到 OSK ({len(chain_info)} 层祖先):")
                for line in chain_info:
                    print(line)
        except Exception as e:
            if debug:
                print(f"[UIA] 异常: {e}")
        return False

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
