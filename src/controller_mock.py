"""键盘模拟手柄 — 开发/测试用。

当没有物理手柄时，用键盘模拟手柄输入。
接口与 GamepadListener 完全一致，可无缝替换。

默认映射:
    WASD      → 左摇杆
    IJKL      → 右摇杆
    Space     → A
    Left Shift→ B
    E         → X
    R         → Y
    Q         → LB
    U         → RB
    1         → LT
    2         → RT
    Enter     → START
    Tab       → SELECT
    方向键     → 十字键
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import pygame
from pygame.locals import KEYDOWN, KEYUP

from src.types import (
    Button, StickState, TriggerState, ButtonState, GamepadState,
    OnStateCallback, OnButtonCallback, OnConnectCallback, OnDisconnectCallback,
)


# ─── 键盘→手柄映射 ───

# 键盘按键 → 手柄按钮
_KEY_BUTTON_MAP = {
    pygame.K_SPACE: Button.A,
    pygame.K_LSHIFT: Button.B,
    pygame.K_RSHIFT: Button.B,
    pygame.K_e: Button.X,
    pygame.K_r: Button.Y,
    pygame.K_q: Button.LB,
    pygame.K_u: Button.RB,
    pygame.K_1: Button.LT,
    pygame.K_2: Button.RT,
    pygame.K_RETURN: Button.START,
    pygame.K_TAB: Button.SELECT,
    pygame.K_LCTRL: Button.LEFT_STICK,
    pygame.K_RCTRL: Button.RIGHT_STICK,
}

# 方向键 → 十字键
_KEY_DPAD_MAP = {
    pygame.K_UP: (0, 1),
    pygame.K_DOWN: (0, -1),
    pygame.K_LEFT: (-1, 0),
    pygame.K_RIGHT: (1, 0),
}

# WASD → 左摇杆
_KEY_LEFT_STICK = {
    pygame.K_w: (0.0, 1.0),
    pygame.K_s: (0.0, -1.0),
    pygame.K_a: (-1.0, 0.0),
    pygame.K_d: (1.0, 0.0),
}

# IJKL → 右摇杆
_KEY_RIGHT_STICK = {
    pygame.K_i: (0.0, 1.0),
    pygame.K_k: (0.0, -1.0),
    pygame.K_j: (-1.0, 0.0),
    pygame.K_l: (1.0, 0.0),
}


# ─── 监听器 ───

class GamepadListener:
    """键盘模拟手柄监听器 — 接口完全兼容 GamepadListener。"""

    def __init__(self, deadzone: float = 0.15):
        self._deadzone = deadzone
        self._state = GamepadState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = True  # 模拟：始终连接

        # 按键追踪
        self._pressed_keys: set[int] = set()
        self._stick_keys_l: set[int] = set()
        self._stick_keys_r: set[int] = set()

        # 回调
        self._on_state: list[OnStateCallback] = []
        self._on_button: list[OnButtonCallback] = []
        self._on_connect: list[OnConnectCallback] = []
        self._on_disconnect: list[OnDisconnectCallback] = []

    def on_state(self, cb: OnStateCallback): self._on_state.append(cb)
    def on_button(self, cb: OnButtonCallback): self._on_button.append(cb)
    def on_connect(self, cb: OnConnectCallback): self._on_connect.append(cb)
    def on_disconnect(self, cb: OnDisconnectCallback): self._on_disconnect.append(cb)

    def start(self) -> bool:
        if self._running:
            return True
        # 初始化pygame显示（键盘事件需要display模块）
        pygame.display.init()
        pygame.display.set_mode((1, 1), pygame.HIDDEN)  # 隐藏窗口
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mock-gamepad")
        self._thread.start()
        for cb in self._on_connect:
            cb()
        return True

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        pygame.display.quit()

    @property
    def state(self) -> GamepadState:
        with self._lock:
            return self._state

    def _loop(self):
        """主循环：读取pygame键盘事件。"""
        while self._running:
            pygame.event.pump()

            for event in pygame.event.get():
                if event.type == KEYDOWN:
                    self._on_key(event.key, True)
                elif event.type == KEYUP:
                    self._on_key(event.key, False)

            # 更新摇杆（根据当前按住的键计算）
            self._update_sticks()

            time.sleep(0.01)  # ~100Hz

    def _on_key(self, key: int, pressed: bool):
        """处理键盘按下/释放。"""
        now = time.monotonic()

        # 跟踪按住的键
        if pressed:
            self._pressed_keys.add(key)
        else:
            self._pressed_keys.discard(key)

        # 跟踪摇杆键
        if key in _KEY_LEFT_STICK:
            if pressed:
                self._stick_keys_l.add(key)
            else:
                self._stick_keys_l.discard(key)
        if key in _KEY_RIGHT_STICK:
            if pressed:
                self._stick_keys_r.add(key)
            else:
                self._stick_keys_r.discard(key)

        with self._lock:
            state = self._state
            state.timestamp = now

            # 按钮映射
            if key in _KEY_BUTTON_MAP:
                btn = _KEY_BUTTON_MAP[key]
                bs = state.buttons[btn]
                if pressed and not bs.pressed:
                    bs.pressed = True
                    bs.pressed_at = now
                    self._notify_button(btn, True)
                elif not pressed and bs.pressed:
                    bs.pressed = False
                    bs.released_at = now
                    bs.hold_duration = (now - bs.pressed_at) * 1000
                    self._notify_button(btn, False)

            # 扳机（1/2键作为切换）
            if key == pygame.K_1:
                state.left_trigger.value = 1.0 if pressed else 0.0
                was = state.left_trigger.pressed
                state.left_trigger.pressed = pressed
                if not was and pressed:
                    self._notify_button(Button.LT, True)
                elif was and not pressed:
                    self._notify_button(Button.LT, False)
            if key == pygame.K_2:
                state.right_trigger.value = 1.0 if pressed else 0.0
                was = state.right_trigger.pressed
                state.right_trigger.pressed = pressed
                if not was and pressed:
                    self._notify_button(Button.RT, True)
                elif was and not pressed:
                    self._notify_button(Button.RT, False)

            # 十字键
            if key in _KEY_DPAD_MAP:
                dx, dy = _KEY_DPAD_MAP[key]
                cur_x, cur_y = state.dpad
                if pressed:
                    state.dpad = (cur_x + dx, cur_y + dy)
                else:
                    state.dpad = (cur_x - dx, cur_y - dy)

        # 触发state回调
        for cb in self._on_state:
            cb(self._state)

    def _update_sticks(self):
        """根据当前按住的键计算摇杆位置。"""
        lx, ly = 0.0, 0.0
        for k in self._stick_keys_l:
            dx, dy = _KEY_LEFT_STICK[k]
            lx += dx
            ly += dy
        # 限制在 [-1, 1]
        lx = max(-1.0, min(1.0, lx))
        ly = max(-1.0, min(1.0, ly))

        rx, ry = 0.0, 0.0
        for k in self._stick_keys_r:
            dx, dy = _KEY_RIGHT_STICK[k]
            rx += dx
            ry += dy
        rx = max(-1.0, min(1.0, rx))
        ry = max(-1.0, min(1.0, ry))

        with self._lock:
            self._state.left_stick.x = lx
            self._state.left_stick.y = ly
            self._state.right_stick.x = rx
            self._state.right_stick.y = ry

    def _notify_button(self, btn: Button, pressed: bool):
        for cb in self._on_button:
            cb(btn, pressed)


def find_controllers() -> list[str]:
    return ["键盘模拟手柄 (Mock Gamepad)"]
