"""键盘模拟手柄 — 开发/测试用。

当没有物理手柄时，用键盘模拟手柄输入。
接口与 GamepadListener 完全一致，可无缝替换。

使用 Win32 WH_KEYBOARD_LL 全局钩子（ctypes），不依赖窗口焦点。

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
    Ctrl      → 左摇杆按下
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time

from src.types import (
    Button, StickState, TriggerState, ButtonState, GamepadState,
    OnStateCallback, OnButtonCallback, OnConnectCallback, OnDisconnectCallback,
)

# ─── Win32 常量 ───
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# 虚拟键码 → 字符串名
_VK_NAME_MAP: dict[int, str] = {
    0x41: "a", 0x42: "b", 0x43: "c", 0x44: "d", 0x45: "e",
    0x46: "f", 0x47: "g", 0x48: "h", 0x49: "i", 0x4A: "j",
    0x4B: "k", 0x4C: "l", 0x4D: "m", 0x4E: "n", 0x4F: "o",
    0x50: "p", 0x51: "q", 0x52: "r", 0x53: "s", 0x54: "t",
    0x55: "u", 0x56: "v", 0x57: "w", 0x58: "x", 0x59: "y",
    0x5A: "z",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x20: "space",
    0x0D: "enter",
    0x09: "tab",
    0x1B: "esc",
    0x10: "shift",   # VK_SHIFT
    0xA0: "shift",   # VK_LSHIFT
    0xA1: "shift",   # VK_RSHIFT
    0x11: "ctrl",    # VK_CONTROL
    0xA2: "ctrl",    # VK_LCONTROL
    0xA3: "ctrl",    # VK_RCONTROL
    0x25: "left",    # VK_LEFT
    0x26: "up",      # VK_UP
    0x27: "right",   # VK_RIGHT
    0x28: "down",    # VK_DOWN
}

# ─── 键盘→手柄映射 ───

_NAME_BUTTON_MAP = {
    "a": Button.A, "b": Button.B, "x": Button.X, "y": Button.Y,
    "q": Button.LB, "u": Button.RB,
    "1": Button.LT, "2": Button.RT,
    "enter": Button.START, "tab": Button.SELECT,
    "ctrl": Button.LEFT_STICK,
}

_DPAD_MAP = {
    "up": (0, 1), "down": (0, -1),
    "left": (-1, 0), "right": (1, 0),
}

_LEFT_STICK_MAP = {
    "w": (0.0, 1.0), "s": (0.0, -1.0),
    "a": (-1.0, 0.0), "d": (1.0, 0.0),
}

_RIGHT_STICK_MAP = {
    "i": (0.0, 1.0), "k": (0.0, -1.0),
    "j": (-1.0, 0.0), "l": (1.0, 0.0),
}


# ─── Win32 钩子 ───

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

# 全局钩子回调函数指针（必须保持引用防止 GC）
_hook_proc = None
_hook_id = None
_listener_ref = None  # 全局引用，让钩子回调能找到监听器

# 定义钩子回调签名
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,  # LRESULT
    ctypes.c_int,       # nCode
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


def _low_level_hook(nCode: int, wParam: int, lParam: int) -> int:
    """WH_KEYBOARD_LL 钩子回调 — 在独立的系统线程上下文中调用。"""
    if nCode >= 0 and _listener_ref:
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kb.vkCode
        name = _VK_NAME_MAP.get(vk, "")
        if name:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                _listener_ref.feed_key(name, True)
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                _listener_ref.feed_key(name, False)
    return ctypes.windll.user32.CallNextHookEx(_hook_id, nCode, wParam, lParam)


# ─── 监听器 ───

class GamepadListener:
    """键盘模拟手柄监听器 — 接口完全兼容 GamepadListener。

    使用 Win32 WH_KEYBOARD_LL 全局钩子（ctypes），无需窗口焦点即可工作。
    """

    def __init__(self, deadzone: float = 0.15):
        self._deadzone = deadzone
        self._state = GamepadState()
        self._lock = threading.Lock()
        self._running = False
        self._connected = True

        self._pressed: dict[str, bool] = {}

        self._on_state: list[OnStateCallback] = []
        self._on_button: list[OnButtonCallback] = []
        self._on_connect: list[OnConnectCallback] = []
        self._on_disconnect: list[OnDisconnectCallback] = []

    def on_state(self, cb: OnStateCallback): self._on_state.append(cb)
    def on_button(self, cb: OnButtonCallback): self._on_button.append(cb)
    def on_connect(self, cb: OnConnectCallback): self._on_connect.append(cb)
    def on_disconnect(self, cb: OnDisconnectCallback): self._on_connect.append(cb)

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True

        # 安装全局低级键盘钩子
        global _hook_proc, _hook_id, _listener_ref
        _listener_ref = self
        _hook_proc = HOOKPROC(_low_level_hook)
        # WH_KEYBOARD_LL 是全局钩子，hMod 传 NULL 即可
        # （ctypes 回调不在正常的 PE 模块中，无法用 GetModuleHandle）
        _hook_id = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, _hook_proc, 0, 0
        )
        if not _hook_id:
            err = ctypes.windll.kernel32.GetLastError()
            print(f"[mock] SetWindowsHookExW 失败 (错误码: {err})")
            # 尝试用 kernel32 模块句柄兜底
            k32_hmod = ctypes.windll.kernel32.GetModuleHandleW("kernel32.dll")
            _hook_id = ctypes.windll.user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, _hook_proc, k32_hmod, 0
            )
        if not _hook_id:
            err = ctypes.windll.kernel32.GetLastError()
            print(f"[mock] SetWindowsHookExW 最终失败 (错误码: {err})")
            _listener_ref = None
            self._running = False
            return False

        print(f"[mock] Win32 全局键盘钩子已安装 (id={_hook_id})")
        for cb in self._on_connect:
            cb()
        return True

    def stop(self):
        global _hook_id, _hook_proc, _listener_ref
        self._running = False
        if _hook_id:
            ctypes.windll.user32.UnhookWindowsHookEx(_hook_id)
            _hook_id = None
        _hook_proc = None
        _listener_ref = None

    @property
    def state(self) -> GamepadState:
        with self._lock:
            return self._state

    # ── 由钩子回调调用（在钩子线程上下文中） ──

    def feed_key(self, name: str, pressed: bool):
        """接收来自 Win32 钩子的键盘事件。"""
        now = time.monotonic()

        if pressed:
            self._pressed[name] = True
        else:
            self._pressed.pop(name, None)

        with self._lock:
            state = self._state
            state.timestamp = now

            if name in _NAME_BUTTON_MAP:
                btn = _NAME_BUTTON_MAP[name]
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

            if name == "shift":
                btn = Button.B
                bs = state.buttons[btn]
                if pressed and not bs.pressed:
                    bs.pressed = True; bs.pressed_at = now
                    self._notify_button(btn, True)
                elif not pressed and bs.pressed:
                    bs.pressed = False; bs.released_at = now
                    bs.hold_duration = (now - bs.pressed_at) * 1000
                    self._notify_button(btn, False)

            if name == "space":
                btn = Button.A
                bs = state.buttons[btn]
                if pressed and not bs.pressed:
                    bs.pressed = True; bs.pressed_at = now
                    self._notify_button(btn, True)
                elif not pressed and bs.pressed:
                    bs.pressed = False; bs.released_at = now
                    bs.hold_duration = (now - bs.pressed_at) * 1000
                    self._notify_button(btn, False)

            if name == "1":
                state.left_trigger.value = 1.0 if pressed else 0.0
                was = state.left_trigger.pressed
                state.left_trigger.pressed = pressed
                if not was and pressed:
                    self._notify_button(Button.LT, True)
                elif was and not pressed:
                    self._notify_button(Button.LT, False)
            if name == "2":
                state.right_trigger.value = 1.0 if pressed else 0.0
                was = state.right_trigger.pressed
                state.right_trigger.pressed = pressed
                if not was and pressed:
                    self._notify_button(Button.RT, True)
                elif was and not pressed:
                    self._notify_button(Button.RT, False)

        self._update_analogs()

        for cb in self._on_state:
            cb(self._state)

    def _update_analogs(self):
        lx, ly = 0.0, 0.0
        for k, (dx, dy) in _LEFT_STICK_MAP.items():
            if self._pressed.get(k):
                lx += dx; ly += dy
        lx = max(-1.0, min(1.0, lx))
        ly = max(-1.0, min(1.0, ly))

        rx, ry = 0.0, 0.0
        for k, (dx, dy) in _RIGHT_STICK_MAP.items():
            if self._pressed.get(k):
                rx += dx; ry += dy
        rx = max(-1.0, min(1.0, rx))
        ry = max(-1.0, min(1.0, ry))

        dpx, dpy = 0, 0
        for k, (dx, dy) in _DPAD_MAP.items():
            if self._pressed.get(k):
                dpx += dx; dpy += dy
        dpx = max(-1, min(1, dpx))
        dpy = max(-1, min(1, dpy))

        with self._lock:
            self._state.left_stick.x = lx
            self._state.left_stick.y = ly
            self._state.right_stick.x = rx
            self._state.right_stick.y = ry
            self._state.dpad = (dpx, dpy)

    def _notify_button(self, btn: Button, pressed: bool):
        for cb in self._on_button:
            cb(btn, pressed)


def find_controllers() -> list[str]:
    return ["键盘模拟手柄 (Mock Gamepad)"]
