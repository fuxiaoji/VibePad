"""模式引擎 — 连接手柄输入和键鼠输出。

根据当前模式的配置映射，将 GamepadState + button事件
翻译为 MouseSimulator 和 KeySimulator 的调用。

支持模式切换（短按/长按切换按钮）。
"""

from __future__ import annotations

import time
from enum import Enum, auto

from src.config import AppConfig, ModeConfig
from src.controller import GamepadListener, GamepadState, Button
from src.mouse_sim import MouseSimulator, curve_from_string
from src.key_sim import KeySimulator


class ActionType(Enum):
    """动作类型，用于分类映射目标。"""
    MOUSE = auto()      # 鼠标相关（移动、点击、滚轮）
    KEY = auto()        # 键盘相关（单键、组合键）
    SWITCH = auto()     # 模式切换
    NONE = auto()       # 无映射


def classify_action(mapping_value: str) -> tuple[ActionType, str]:
    """判断映射值的动作类型。

    Returns:
        (ActionType, 参数)
    """
    if not mapping_value or mapping_value == "null":
        return (ActionType.NONE, "")
    if mapping_value.startswith("switch_mode."):
        return (ActionType.SWITCH, mapping_value[12:])
    if mapping_value.startswith("key."):
        return (ActionType.KEY, mapping_value)
    if mapping_value.startswith("mouse_"):
        return (ActionType.MOUSE, mapping_value[6:])  # 去掉 "mouse_"
    return (ActionType.NONE, "")


class ModeEngine:
    """模式引擎。

    用法:
        engine = ModeEngine(config, listener)
        engine.start()
        # 主循环
        while True:
            engine.tick()
            time.sleep(0.01)
    """

    def __init__(self, config: AppConfig, listener: GamepadListener):
        self.config = config
        self.listener = listener

        # 输出设备
        self.mouse = MouseSimulator(
            sensitivity=config.global_.mouse_sensitivity,
            scroll_sensitivity=config.global_.scroll_sensitivity,
            curve=curve_from_string(config.global_.cursor_speed_curve),
        )
        self.keys = KeySimulator()

        # 当前模式
        self._current_mode: str = config.default_mode or ""
        self._last_tick = time.monotonic()

        # 模式切换按钮状态追踪
        self._switch_hold_start: dict[Button, float] = {}
        self._switch_was_pressed: set[Button] = set()
        self._hold_threshold = config.global_.mode_switch_hold_ms / 1000.0

        # 按钮边沿检测（区分"刚按下"和"持续按住"）
        self._prev_buttons: dict[Button, bool] = {b: False for b in Button}

    @property
    def current_mode(self) -> str:
        return self._current_mode

    def start(self):
        """启动引擎，注册回调。"""
        self.listener.on_button(self._on_button)
        self._last_tick = time.monotonic()

    def stop(self):
        """停止引擎，释放所有按键。"""
        self.keys.release_all()

    def tick(self):
        """每帧调用一次。处理摇杆→鼠标移动、滚轮持续输入。"""
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        if dt <= 0:
            return

        state = self.listener.state
        mode = self.config.get_mode(self._current_mode)
        if mode is None:
            return

        mappings = mode.mappings

        # --- 摇杆→鼠标移动 ---
        if "LEFT_STICK_X" in mappings and mappings["LEFT_STICK_X"] == "mouse_x":
            self.mouse.move(state.left_stick.x, state.left_stick.y, dt)

        # --- 右摇杆→滚轮 ---
        # 滚轮用 accumulate 方式：每帧根据摇杆值滚固定量
        scroll_x_action = mappings.get("RIGHT_STICK_X", "")
        scroll_y_action = mappings.get("RIGHT_STICK_Y", "")
        if scroll_x_action == "scroll_x" or scroll_y_action == "scroll_y":
            self.mouse.scroll(
                state.right_stick.x * dt * 10.0 if scroll_x_action == "scroll_x" else 0.0,
                -state.right_stick.y * dt * 10.0 if scroll_y_action == "scroll_y" else 0.0,
            )

        # --- 十字键→离散滚轮 ---
        dpad_x, dpad_y = state.dpad
        if dpad_y != 0 and mappings.get("DPAD_UP") == "scroll_up":
            self.mouse.scroll(0, -dpad_y * 3)
        if dpad_x != 0 and mappings.get("DPAD_LEFT") == "scroll_left":
            self.mouse.scroll(dpad_x * 3, 0)

    # --- 按钮处理 ---

    def _on_button(self, btn: Button, pressed: bool):
        """手柄按钮回调。"""
        now = time.monotonic()
        mode = self.config.get_mode(self._current_mode)
        if mode is None:
            return

        mapping_value = mode.mappings.get(btn.name, "")
        action_type, param = classify_action(mapping_value)

        if pressed:
            self._handle_press(btn, action_type, param, now)
        else:
            self._handle_release(btn, action_type, param, now)

        self._prev_buttons[btn] = pressed

    def _handle_press(self, btn: Button, action_type: ActionType, param: str, now: float):
        if action_type == ActionType.MOUSE:
            self._mouse_action(param, True)
        elif action_type == ActionType.KEY:
            self.keys.press(param)
        elif action_type == ActionType.SWITCH:
            self._switch_hold_start[btn] = now
            self._switch_was_pressed.add(btn)

    def _handle_release(self, btn: Button, action_type: ActionType, param: str, now: float):
        if action_type == ActionType.MOUSE:
            self._mouse_action(param, False)
        elif action_type == ActionType.KEY:
            self.keys.release(param)
        elif action_type == ActionType.SWITCH:
            if btn in self._switch_hold_start:
                hold_duration = now - self._switch_hold_start.pop(btn)
                self._switch_was_pressed.discard(btn)
                if hold_duration < self._hold_threshold:
                    # 短按 → 切换模式
                    self._switch_mode(param)

    def _switch_mode(self, target_mode: str):
        """切换到目标模式。"""
        if target_mode in self.config.modes:
            old = self._current_mode
            self._current_mode = target_mode
            self.keys.release_all()
            print(f"模式切换: {old} → {target_mode}")

    def _mouse_action(self, action: str, pressed: bool):
        """执行鼠标动作。"""
        if action == "left":
            if pressed:
                self.mouse.click_left()
        elif action == "right":
            if pressed:
                self.mouse.click_right()
        elif action == "middle":
            if pressed:
                self.mouse.click_middle()
        elif action == "x":
            pass  # 摇杆移动在 tick() 中处理
        elif action == "y":
            pass
