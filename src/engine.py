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
from src.navigator import Navigator


class ActionType(Enum):
    """动作类型，用于分类映射目标。"""
    MOUSE = auto()      # 鼠标相关（移动、点击、滚轮）
    KEY = auto()        # 键盘相关（单键、组合键）
    SWITCH = auto()     # 模式切换
    NAVIGATE = auto()   # UI 焦点导航（vim 模式）
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
    if mapping_value.startswith("scroll_"):
        return (ActionType.MOUSE, mapping_value)
    if mapping_value.startswith("nav."):
        return (ActionType.NAVIGATE, mapping_value[4:])
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
            speed_boost=config.global_.mouse_speed_boost,
        )
        self.keys = KeySimulator()
        self.navigator = Navigator()

        # 当前模式
        self._current_mode: str = config.default_mode or ""
        self._last_tick = time.monotonic()

        # 模式切换按钮状态追踪
        self._switch_hold_start: dict[Button, float] = {}
        self._switch_was_pressed: set[Button] = set()
        self._hold_threshold = config.global_.mode_switch_hold_ms / 1000.0

        # 按钮边沿检测（区分"刚按下"和"持续按住"）
        self._prev_buttons: dict[Button, bool] = {b: False for b in Button}

        # RT 扳机模拟值平滑 & 边沿检测（绕过按钮事件系统，直接读模拟量）
        self._rt_smoothed = 0.0
        self._rt_speed_active = False  # 视频倍速是否已触发
        self._rt_sticky_frames = 0     # 粘性释放计数器（防止 raw 抖动导致闪烁）
        self._dbg_frame = 0  # 调试用帧计数

        # 左摇杆焦点导航状态（vim 模式）
        self._stick_nav_cooldown = 0.0
        self._stick_nav_dir = (0, 0)
        self._stick_jump_cooldown = 0.0  # LT+摇杆跳转冷却

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
        if self.navigator.active:
            self.navigator.stop()

    def tick(self):
        """每帧调用一次。处理摇杆→鼠标移动、滚轮、RT 扳机加速。"""
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

        # --- RT 扳机模拟值（EMA 平滑 + 粘性释放，抗抖动） ---
        raw_rt = state.right_trigger.value
        alpha = 0.2  # 稍小平滑系数，更抗噪
        self._rt_smoothed += alpha * (raw_rt - self._rt_smoothed)
        rt_now = self._rt_smoothed > 0.25

        # 粘性释放：激活即时响应，松开需连续 8 帧 (~130ms) 确认
        if rt_now:
            self._rt_sticky_frames = 0
        else:
            self._rt_sticky_frames += 1

        rt_active = self._rt_sticky_frames < 8

        # 调试：每秒输出一次
        self._dbg_frame += 1
        if self._dbg_frame % 60 == 1:
            print(f"[RT debug] raw={raw_rt:.3f} smoothed={self._rt_smoothed:.3f} "
                  f"sticky={self._rt_sticky_frames} active={rt_active} "
                  f"boost={self.mouse._speed_boost_active} mode={self._current_mode}")

        # 鼠标加速 — 所有模式通用，RT 按住时光标变快
        self.mouse.set_speed_boost(rt_active)

        # --- 左摇杆焦点导航（vim 模式） ---
        if self._current_mode == "vim" and self.navigator.active:
            lt_active = state.left_trigger.value > 0.25
            stick_active = abs(state.left_stick.x) > 0.5 or abs(state.left_stick.y) > 0.5

            if lt_active and stick_active:
                # LT + 摇杆 → 跳到最远
                self._handle_stick_jump(state.left_stick.x, state.left_stick.y, dt)
            elif not lt_active:
                # 普通摇杆导航
                self._handle_stick_nav(state.left_stick.x, state.left_stick.y, dt)

        # 视频倍速 — vim 模式 + 视频上下文，边沿触发防止重复调用
        if self._current_mode == "vim" and self.navigator.active:
            if rt_active and not self._rt_speed_active:
                self.navigator.speed_start()
                self._rt_speed_active = True
            elif not rt_active and self._rt_speed_active:
                self.navigator.speed_end()
                self._rt_speed_active = False
        else:
            # 非 vim 模式，确保倍速状态重置
            if self._rt_speed_active:
                self.navigator.speed_end()
                self._rt_speed_active = False

        # --- 摇杆→鼠标移动 ---
        if "LEFT_STICK_X" in mappings and mappings["LEFT_STICK_X"] == "mouse_x":
            self.mouse.move(state.left_stick.x, state.left_stick.y, dt)

        # --- 右摇杆→滚轮 ---
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
        elif action_type == ActionType.NAVIGATE:
            if param == "speed_hold":
                self.navigator.speed_start()
            else:
                self._nav_action(param)

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
        elif action_type == ActionType.NAVIGATE:
            if param == "speed_hold":
                self.navigator.speed_end()

    def _switch_mode(self, target_mode: str):
        """切换到目标模式。"""
        if target_mode not in self.config.modes:
            return

        old = self._current_mode
        old_cfg = self.config.get_mode(old)
        new_cfg = self.config.get_mode(target_mode)

        # 离开旧模式
        if old_cfg and self._mode_has_nav(old_cfg):
            self.navigator.stop()

        self._current_mode = target_mode

        # 进入新模式
        if new_cfg and self._mode_has_nav(new_cfg):
            self.navigator.start()

        self.keys.release_all()
        print(f"模式切换: {old} → {target_mode}")

    def _nav_action(self, action: str):
        """分发导航动作到 Navigator。"""
        nav = self.navigator
        if not nav.active:
            return

        dispatch = {
            "up": nav.move_up,
            "down": nav.move_down,
            "left": nav.move_left,
            "right": nav.move_right,
            "click": nav.click,
            "right_click": nav.right_click,
            "double_click": nav.double_click,
            "escape": nav.escape,
            "tab": nav.tab,
            "enter": nav.enter,
            "scroll_up": nav.scroll_up,
            "scroll_down": nav.scroll_down,
            "prev_tab": nav.prev_tab,
            "next_tab": nav.next_tab,
            "refresh": nav.refresh,
            "task_view": nav.task_view,
            "switch_input": nav.switch_input,
        }
        fn = dispatch.get(action)
        if fn:
            fn()

    def _handle_stick_nav(self, stick_x: float, stick_y: float, dt: float):
        """左摇杆控制焦点导航（vim 模式）。

        带死区和冷却，防止误触发。方向变化时立即响应，
        持续推住则按固定间隔重复。
        """
        deadzone = 0.5
        repeat_delay = 0.2  # 200ms 重复间隔

        # 确定主导方向
        dir_x = 0
        dir_y = 0
        if abs(stick_x) > abs(stick_y):
            if stick_x > deadzone:
                dir_x = 1
            elif stick_x < -deadzone:
                dir_x = -1
        else:
            if stick_y > deadzone:
                dir_y = 1
            elif stick_y < -deadzone:
                dir_y = -1

        new_dir = (dir_x, dir_y)
        if new_dir != self._stick_nav_dir:
            self._stick_nav_dir = new_dir
            self._stick_nav_cooldown = 0.0  # 方向变化立即响应

        if new_dir == (0, 0):
            return  # 摇杆居中，不移动

        self._stick_nav_cooldown -= dt
        if self._stick_nav_cooldown > 0:
            return

        if dir_x > 0:
            self.navigator.move_right()
        elif dir_x < 0:
            self.navigator.move_left()
        elif dir_y > 0:
            self.navigator.move_down()
        elif dir_y < 0:
            self.navigator.move_up()

        self._stick_nav_cooldown = repeat_delay

    def _handle_stick_jump(self, stick_x: float, stick_y: float, dt: float):
        """LT+摇杆：跳到目标方向最远元素。"""
        deadzone = 0.5
        cooldown = 0.35  # 跳转冷却比普通导航稍长

        self._stick_jump_cooldown -= dt
        if self._stick_jump_cooldown > 0:
            return

        dir_x, dir_y = 0, 0
        if abs(stick_x) > abs(stick_y):
            if stick_x > deadzone:
                dir_x = 1
            elif stick_x < -deadzone:
                dir_x = -1
        else:
            if stick_y > deadzone:
                dir_y = 1
            elif stick_y < -deadzone:
                dir_y = -1

        if dir_x != 0 or dir_y != 0:
            self.navigator.jump_to_end(dir_x, dir_y)
            self._stick_jump_cooldown = cooldown

    @staticmethod
    def _mode_has_nav(mode: ModeConfig | None) -> bool:
        """检查模式中是否有导航动作映射。"""
        if mode is None:
            return False
        return any((v or "").startswith("nav.") for v in mode.mappings.values())

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
        elif action == "speed_hold":
            self.mouse.set_speed_boost(pressed)
        elif action == "x":
            pass  # 摇杆移动在 tick() 中处理
        elif action == "y":
            pass
