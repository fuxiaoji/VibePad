"""手柄输入捕获模块 — 多后端支持。

后端优先级:
    1. XInput (Windows) — 直接调用 XInputGetState，绕过 SDL2
    2. SDL2 GameController — 跨平台，Xbox 蓝牙手柄
    3. pygame joystick — 通用 DirectInput
    4. hidapi — 底层 HID，最后备选

架构:
    后台线程: 读取手柄 → 解析 → 更新 GamepadState → 触发回调
    主线程:   读取 state 属性，消费数据
"""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
import time
from typing import Optional

from src.types import (
    Button, Stick, StickState, TriggerState, ButtonState, GamepadState,
    OnStateCallback, OnButtonCallback, OnConnectCallback, OnDisconnectCallback,
)


# ─── Xbox 360 HID 报告解析器 ───

class XboxReportParser:
    """解析 Xbox 360/One 控制器的 HID 输入报告。

    标准 Xbox 360 报告格式（20字节）:
        [0]  = 消息类型 (0x00=normal, 0x01=button-only)
        [1]  = 按钮低字节 (bitfield)
        [2]  = 按钮高字节 (bitfield)
        [3]  = 左扳机 (0-255)
        [4]  = 右扳机 (0-255)
        [5-6]  = 左摇杆X (int16 LE)
        [7-8]  = 左摇杆Y (int16 LE)
        [9-10] = 右摇杆X (int16 LE)
        [11-12]= 右摇杆Y (int16 LE)
    """

    STICK_MAX = 32767.0

    # 按钮位掩码 [字节1]
    BTN_DPAD_UP    = 0x01
    BTN_DPAD_DOWN  = 0x02
    BTN_DPAD_LEFT  = 0x04
    BTN_DPAD_RIGHT = 0x08
    BTN_START      = 0x10
    BTN_SELECT     = 0x20
    BTN_L_STICK    = 0x40
    BTN_R_STICK    = 0x80

    # 按钮位掩码 [字节2]
    BTN_A  = 0x10   # Xbox驱动中A在bit4
    BTN_B  = 0x20
    BTN_X  = 0x40
    BTN_Y  = 0x80
    BTN_LB = 0x01
    BTN_RB = 0x02

    # 备选映射：有些驱动用不同的位布局
    # 字节1 的另一种常见映射
    BTN_A_ALT  = 0x10
    BTN_B_ALT  = 0x20

    @classmethod
    def parse(cls, data: bytes) -> dict:
        """解析报告，返回结构化数据。"""
        if len(data) < 14:
            return {}

        # 提取字段
        btn1, btn2 = data[1], data[2]
        lt, rt = data[3], data[4]
        lx = struct.unpack_from('<h', data, 5)[0]
        ly = struct.unpack_from('<h', data, 7)[0]
        rx = struct.unpack_from('<h', data, 9)[0]
        ry = struct.unpack_from('<h', data, 11)[0]

        # 解析按钮
        dpad = (0, 0)
        if btn1 & cls.BTN_DPAD_UP:
            dpad = (dpad[0], 1)
        if btn1 & cls.BTN_DPAD_DOWN:
            dpad = (dpad[0], -1)
        if btn1 & cls.BTN_DPAD_LEFT:
            dpad = (-1, dpad[1])
        if btn1 & cls.BTN_DPAD_RIGHT:
            dpad = (1, dpad[1])

        buttons = {
            Button.A:           bool(btn2 & cls.BTN_A),
            Button.B:           bool(btn2 & cls.BTN_B),
            Button.X:           bool(btn2 & cls.BTN_X),
            Button.Y:           bool(btn2 & cls.BTN_Y),
            Button.LB:          bool(btn2 & cls.BTN_LB),
            Button.RB:          bool(btn2 & cls.BTN_RB),
            Button.START:       bool(btn1 & cls.BTN_START),
            Button.SELECT:      bool(btn1 & cls.BTN_SELECT),
            Button.LEFT_STICK:  bool(btn1 & cls.BTN_L_STICK),
            Button.RIGHT_STICK: bool(btn1 & cls.BTN_R_STICK),
            Button.DPAD_UP:     bool(btn1 & cls.BTN_DPAD_UP),
            Button.DPAD_DOWN:   bool(btn1 & cls.BTN_DPAD_DOWN),
            Button.DPAD_LEFT:   bool(btn1 & cls.BTN_DPAD_LEFT),
            Button.DPAD_RIGHT:  bool(btn1 & cls.BTN_DPAD_RIGHT),
        }

        # 扳机
        lt_val = lt / 255.0
        rt_val = rt / 255.0

        return {
            "lx": lx / cls.STICK_MAX,
            "ly": ly / cls.STICK_MAX,
            "rx": rx / cls.STICK_MAX,
            "ry": ry / cls.STICK_MAX,
            "lt": lt_val,
            "rt": rt_val,
            "buttons": buttons,
            "dpad": dpad,
        }


# ─── XInput 后端 (Windows, 最高优先级) ───

class _GamepadBackendXInput:
    """Windows XInput 后端 — 直接用 ctypes 调用 XInputGetState。

    绕过 SDL2，直接读取 XUSB 驱动数据。
    支持所有 Xbox 360/One/Series 手柄 (USB 和 Xbox 无线适配器)。
    """

    XINPUT_DEADZONE_LEFT = 7849   # XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE
    XINPUT_DEADZONE_RIGHT = 8689  # XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE
    STICK_MAX = 32768.0
    TRIGGER_MAX = 255.0

    # XInput 按钮位掩码 → Button
    _BTN_MASK = {
        0x1000: Button.A,
        0x2000: Button.B,
        0x4000: Button.X,
        0x8000: Button.Y,
        0x0100: Button.LB,
        0x0200: Button.RB,
        0x0010: Button.START,
        0x0020: Button.SELECT,
        0x0040: Button.LEFT_STICK,
        0x0080: Button.RIGHT_STICK,
        0x0001: Button.DPAD_UP,
        0x0002: Button.DPAD_DOWN,
        0x0004: Button.DPAD_LEFT,
        0x0008: Button.DPAD_RIGHT,
    }

    @classmethod
    def create(cls, listener: "_GamepadListener"):
        import ctypes
        from ctypes import wintypes

        class XINPUT_GAMEPAD(ctypes.Structure):
            _fields_ = [
                ('wButtons', wintypes.WORD),
                ('bLeftTrigger', ctypes.c_uint8),
                ('bRightTrigger', ctypes.c_uint8),
                ('sThumbLX', ctypes.c_short),
                ('sThumbLY', ctypes.c_short),
                ('sThumbRX', ctypes.c_short),
                ('sThumbRY', ctypes.c_short),
            ]

        class XINPUT_STATE(ctypes.Structure):
            _fields_ = [
                ('dwPacketNumber', wintypes.DWORD),
                ('Gamepad', XINPUT_GAMEPAD),
            ]

        try:
            xinput = ctypes.windll.xinput1_4
        except Exception:
            try:
                xinput = ctypes.windll.xinput1_3
            except Exception:
                return None

        state = XINPUT_STATE()
        for i in range(4):
            ret = xinput.XInputGetState(i, ctypes.byref(state))
            if ret == 0:
                print(f"gamepad connected (XInput): slot {i}")
                return cls(listener, xinput, i, state.__class__)

        return None

    def __init__(self, listener: "_GamepadListener", xinput, slot: int, state_cls):
        self._listener = listener
        self._xinput = xinput
        self._slot = slot
        self._state = state_cls()
        self._last_packet = 0

    def read(self) -> dict:
        ret = self._xinput.XInputGetState(self._slot, ctypes.byref(self._state))
        if ret != 0:
            return {}

        g = self._state.Gamepad

        # 摇杆: XInput 自带死区，但我们自己做规范化
        # 范围 [-32768, 32767] → [-1, 1]
        lx = max(-1.0, min(1.0, g.sThumbLX / self.STICK_MAX))
        ly = max(-1.0, min(1.0, g.sThumbLY / self.STICK_MAX))
        rx = max(-1.0, min(1.0, g.sThumbRX / self.STICK_MAX))
        ry = max(-1.0, min(1.0, g.sThumbRY / self.STICK_MAX))

        # 扳机: [0, 255] → [0, 1]
        lt = g.bLeftTrigger / self.TRIGGER_MAX
        rt = g.bRightTrigger / self.TRIGGER_MAX

        # 按钮
        buttons = {b: False for b in Button}
        mask = g.wButtons
        for bit, btn in self._BTN_MASK.items():
            if mask & bit:
                buttons[btn] = True

        # DPad
        dpad = (0, 0)
        if mask & 0x0001:
            dpad = (dpad[0], 1)
        if mask & 0x0002:
            dpad = (dpad[0], -1)
        if mask & 0x0004:
            dpad = (-1, dpad[1])
        if mask & 0x0008:
            dpad = (1, dpad[1])

        return {
            "lx": lx,
            "ly": -ly,
            "rx": rx,
            "ry": -ry,
            "lt": lt,
            "rt": rt,
            "buttons": buttons,
            "dpad": dpad,
        }

    def close(self):
        pass  # XInput 不需要显式关闭


# ─── SDL2 GameController 后端 ───

class _GamepadBackendSDL2:
    """SDL2 GameController 后端 — 对 Xbox 蓝牙手柄支持最好。

    SDL2 GameController API 使用标准化的手柄映射:
      - 摇杆: [-32768, 32767] → 归一化到 [-1, 1]
      - 扳机: [0, 32767] → 归一化到 [0, 1]
      - 按钮: get_button(idx) → 0/1
    """

    AXIS_MAX = 32768.0
    TRIGGER_MAX = 32767.0

    # SDL2 GameController 按钮索引 → Button
    _BTN_MAP = {
        0:  Button.A,
        1:  Button.B,
        2:  Button.X,
        3:  Button.Y,
        4:  Button.SELECT,     # Back
        6:  Button.START,      # Start
        7:  Button.LEFT_STICK,
        8:  Button.RIGHT_STICK,
        9:  Button.LB,         # Left Shoulder
        10: Button.RB,         # Right Shoulder
        11: Button.DPAD_UP,
        12: Button.DPAD_DOWN,
        13: Button.DPAD_LEFT,
        14: Button.DPAD_RIGHT,
    }

    @classmethod
    def create(cls, listener: "_GamepadListener"):
        try:
            import pygame
            from pygame._sdl2 import controller as sdl2_ctrl

            sdl2_ctrl.init()
            count = sdl2_ctrl.get_count()
            if count == 0:
                return None

            for i in range(count):
                if sdl2_ctrl.is_controller(i):
                    ctrl = sdl2_ctrl.Controller(i)
                    print(f"gamepad connected (SDL2 GameController): {ctrl.name}")
                    return cls(listener, ctrl)
            return None
        except Exception as e:
            print(f"SDL2 GameController backend init failed: {e}")
            return None

    def __init__(self, listener: "_GamepadListener", ctrl):
        self._listener = listener
        self._ctrl = ctrl

    def read(self) -> dict:
        import pygame
        from pygame._sdl2 import controller as sdl2_ctrl

        pygame.event.pump()
        sdl2_ctrl.update()

        lx = self._ctrl.get_axis(0) / self.AXIS_MAX
        ly = self._ctrl.get_axis(1) / self.AXIS_MAX
        rx = self._ctrl.get_axis(2) / self.AXIS_MAX
        ry = self._ctrl.get_axis(3) / self.AXIS_MAX

        lt = self._ctrl.get_axis(4) / self.TRIGGER_MAX
        rt = self._ctrl.get_axis(5) / self.TRIGGER_MAX

        buttons = {b: False for b in Button}
        for sdl_idx, btn in self._BTN_MAP.items():
            if self._ctrl.get_button(sdl_idx):
                buttons[btn] = True

        dpad = (0, 0)
        if buttons.get(Button.DPAD_UP):
            dpad = (dpad[0], 1)
        if buttons.get(Button.DPAD_DOWN):
            dpad = (dpad[0], -1)
        if buttons.get(Button.DPAD_LEFT):
            dpad = (-1, dpad[1])
        if buttons.get(Button.DPAD_RIGHT):
            dpad = (1, dpad[1])

        return {
            "lx": lx,
            "ly": -ly,
            "rx": rx,
            "ry": -ry,
            "lt": lt,
            "rt": rt,
            "buttons": buttons,
            "dpad": dpad,
        }

    def close(self):
        try:
            from pygame._sdl2 import controller as sdl2_ctrl
            sdl2_ctrl.quit()
        except Exception:
            pass


# ─── pygame 手柄后端 ───

class _GamepadBackendPygame:
    """pygame (SDL2) joystick 后端 — 通用 DirectInput 兼容。"""

    # pygame 按钮索引 → Button
    _BTN_MAP = {
        0:  Button.A,
        1:  Button.B,
        2:  Button.X,
        3:  Button.Y,
        4:  Button.LB,
        5:  Button.RB,
        6:  Button.SELECT,
        7:  Button.START,
        8:  Button.LEFT_STICK,
        9:  Button.RIGHT_STICK,
        11: Button.DPAD_UP,
        12: Button.DPAD_DOWN,
        13: Button.DPAD_LEFT,
        14: Button.DPAD_RIGHT,
    }

    @classmethod
    def create(cls, listener: "_GamepadListener"):
        try:
            import pygame
            pygame.joystick.init()
            count = pygame.joystick.get_count()
            if count == 0:
                return None
            joy = pygame.joystick.Joystick(0)
            joy.init()
            name = joy.get_name()
            print(f"gamepad connected (pygame joystick): {name}")
            return cls(listener, joy)
        except Exception as e:
            print(f"pygame joystick backend init failed: {e}")
            return None

    def __init__(self, listener: "_GamepadListener", joy):
        self._listener = listener
        self._joy = joy

    def read(self) -> dict:
        import pygame
        pygame.event.pump()

        num_axes = self._joy.get_numaxes()
        lx = self._joy.get_axis(0) if num_axes > 0 else 0.0
        ly = self._joy.get_axis(1) if num_axes > 1 else 0.0
        rx = self._joy.get_axis(2) if num_axes > 2 else 0.0
        ry = self._joy.get_axis(3) if num_axes > 3 else 0.0

        lt_raw = self._joy.get_axis(4) if num_axes > 4 else -1.0
        rt_raw = self._joy.get_axis(5) if num_axes > 5 else -1.0
        lt = (lt_raw + 1.0) / 2.0
        rt = (rt_raw + 1.0) / 2.0

        num_btns = self._joy.get_numbuttons()
        buttons = {b: False for b in Button}
        for i in range(min(num_btns, 15)):
            if self._joy.get_button(i):
                btn = self._BTN_MAP.get(i)
                if btn:
                    buttons[btn] = True

        num_hats = self._joy.get_numhats()
        dpad = (0, 0)
        if num_hats > 0:
            hat_x, hat_y = self._joy.get_hat(0)
            dpad = (hat_x, hat_y)
            if hat_y == 1:
                buttons[Button.DPAD_UP] = True
            if hat_y == -1:
                buttons[Button.DPAD_DOWN] = True
            if hat_x == -1:
                buttons[Button.DPAD_LEFT] = True
            if hat_x == 1:
                buttons[Button.DPAD_RIGHT] = True

        return {
            "lx": lx,
            "ly": -ly,
            "rx": rx,
            "ry": -ry,
            "lt": lt,
            "rt": rt,
            "buttons": buttons,
            "dpad": dpad,
        }

    def close(self):
        try:
            import pygame
            pygame.joystick.quit()
        except Exception:
            pass


# ─── hidapi 手柄后端 ───

class _GamepadBackendHID:
    """hidapi 后端 — 底层 HID 读取，解析 Xbox 格式报告。"""

    @staticmethod
    def _find_device():
        import hid
        for d in hid.enumerate():
            name = d.get("product_string", "")
            usage_page = d.get("usage_page", 0)
            usage = d.get("usage", 0)
            if usage_page == 0x01 and usage in (0x04, 0x05, 0x06, 0x08):
                try:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    dev.set_nonblocking(False)
                    print(f"手柄已连接 (hidapi): {name} (VID:{hex(d['vendor_id'])}, PID:{hex(d['product_id'])})")
                    return dev
                except Exception as e:
                    print(f"无法打开设备 {name}: {e}")
        return None

    @classmethod
    def create(cls, listener: "_GamepadListener"):
        try:
            import hid
            dev = cls._find_device()
            if dev is None:
                return None
            return cls(listener, dev)
        except ImportError:
            return None

    def __init__(self, listener: "_GamepadListener", device):
        self._listener = listener
        self._device = device
        self._parser = XboxReportParser()

    def read(self) -> dict:
        import hid
        data = self._device.read(64, timeout_ms=100)
        if data and len(data) >= 14:
            return self._parser.parse(bytes(data))
        return {}

    def close(self):
        try:
            self._device.close()
        except Exception:
            pass


# ─── 统一监听器 ───

class _GamepadListener:
    """多后端手柄监听器。

    自动选择最佳后端: pygame (SDL2) > hidapi。
    在后台线程中阻塞读取手柄数据，解析后更新状态并触发回调。
    """

    def __init__(self, deadzone: float = 0.15):
        self._deadzone = deadzone
        self._state = GamepadState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._on_state: list[OnStateCallback] = []
        self._on_button: list[OnButtonCallback] = []
        self._on_connect: list[OnConnectCallback] = []
        self._on_disconnect: list[OnDisconnectCallback] = []

        self._backend = None  # _GamepadBackendPygame or _GamepadBackendHID

    # --- 回调注册 ---

    def on_state(self, cb: OnStateCallback):
        self._on_state.append(cb)

    def on_button(self, cb: OnButtonCallback):
        self._on_button.append(cb)

    def on_connect(self, cb: OnConnectCallback):
        self._on_connect.append(cb)

    def on_disconnect(self, cb: OnDisconnectCallback):
        self._on_disconnect.append(cb)

    # --- 生命周期 ---

    def start(self) -> bool:
        if self._running:
            return True
        # 在主线程初始化 pygame（后台线程不能初始化 display）
        try:
            import pygame
            pygame.init()
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
        except Exception:
            pass
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gamepad")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._backend:
            self._backend.close()
            self._backend = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            import pygame
            pygame.quit()
        except Exception:
            pass

    @property
    def state(self) -> GamepadState:
        with self._lock:
            return self._state

    # --- 死区 ---

    def _apply_deadzone(self, value: float) -> float:
        if abs(value) < self._deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - self._deadzone) / (1.0 - self._deadzone)

    # --- 状态更新 ---

    def _update_state(self, parsed: dict):
        now = time.monotonic()
        prev_buttons: dict[Button, bool] = {}

        with self._lock:
            state = self._state
            state.timestamp = now

            # 摇杆
            state.left_stick.x = self._apply_deadzone(parsed.get("lx", 0.0))
            state.left_stick.y = self._apply_deadzone(parsed.get("ly", 0.0))
            state.right_stick.x = self._apply_deadzone(parsed.get("rx", 0.0))
            state.right_stick.y = self._apply_deadzone(parsed.get("ry", 0.0))

            # 扳机
            lt_val = parsed.get("lt", 0.0)
            rt_val = parsed.get("rt", 0.0)
            state.left_trigger.value = lt_val
            state.right_trigger.value = rt_val

            lt_was = state.left_trigger.pressed
            state.left_trigger.pressed = lt_val > state.left_trigger.threshold
            rt_was = state.right_trigger.pressed
            state.right_trigger.pressed = rt_val > state.right_trigger.threshold

            # 按钮变更检测
            new_buttons = parsed.get("buttons", {})
            for btn in Button:
                bs = state.buttons[btn]
                old = bs.pressed
                new = new_buttons.get(btn, False)
                if new and not old:
                    bs.pressed = True
                    bs.pressed_at = now
                    prev_buttons[btn] = True
                elif not new and old:
                    bs.pressed = False
                    bs.released_at = now
                    bs.hold_duration = (now - bs.pressed_at) * 1000
                    prev_buttons[btn] = False

            # 十字键
            state.dpad = parsed.get("dpad", (0, 0))

        # 在锁外触发回调（避免死锁）
        for btn, pressed in prev_buttons.items():
            for cb in self._on_button:
                cb(btn, pressed)

        for cb in self._on_state:
            cb(self._state)

    def _try_backend(self, backend_class):
        backend = backend_class.create(self)
        if backend:
            self._backend = backend
            for cb in self._on_connect:
                cb()
            return True
        return False

    def _loop(self):
        while self._running and self._backend is None:
            # 1) XInput: Windows 原生, 对 Xbox 手柄最可靠
            if self._try_backend(_GamepadBackendXInput):
                break
            # 2) SDL2 GameController: 跨平台, Xbox 蓝牙
            if self._try_backend(_GamepadBackendSDL2):
                break
            # 3) SDL2 Joystick: 通用 DirectInput
            if self._try_backend(_GamepadBackendPygame):
                break
            # 4) hidapi: 底层 HID，最后后备
            try:
                import pygame as _pg
                _pg.joystick.quit()
            except ImportError:
                pass
            if self._try_backend(_GamepadBackendHID):
                break
            time.sleep(1.0)

        if self._backend is None:
            self._running = False
            return

        while self._running:
            try:
                parsed = self._backend.read()
                if parsed:
                    self._update_state(parsed)
            except (ValueError, OSError):
                self._backend.close()
                self._backend = None
                for cb in self._on_disconnect:
                    cb()
                while self._running:
                    time.sleep(0.5)
                    if self._try_backend(_GamepadBackendXInput):
                        break
                    if self._try_backend(_GamepadBackendSDL2):
                        break
                    if self._try_backend(_GamepadBackendPygame):
                        break
                    try:
                        import pygame as _pg
                        _pg.joystick.quit()
                    except ImportError:
                        pass
                    if self._try_backend(_GamepadBackendHID):
                        break
            except Exception:
                time.sleep(0.01)


# 公开别名
GamepadListener = _GamepadListener


def find_controllers() -> list[str]:
    """列出连接的游戏手柄。优先使用 SDL2 GameController 检测。"""
    found = []
    # SDL2 GameController API (best for Xbox/Bluetooth)
    try:
        import pygame
        from pygame._sdl2 import controller as sdl2_ctrl
        sdl2_ctrl.init()
        count = sdl2_ctrl.get_count()
        for i in range(count):
            if sdl2_ctrl.is_controller(i):
                found.append(f"SDL2: {sdl2_ctrl.name_forindex(i)}")
    except Exception:
        pass
    # SDL2 Joystick API (fallback)
    if not found:
        try:
            import pygame
            was_init = pygame.joystick.get_init()
            if not was_init:
                pygame.joystick.init()
            count = pygame.joystick.get_count()
            for i in range(count):
                joy = pygame.joystick.Joystick(i)
                name = joy.get_name()
                if joy.get_numaxes() >= 2 and joy.get_numbuttons() >= 4:
                    found.append(f"pygame: {name}")
            if not was_init:
                pygame.joystick.quit()
        except Exception:
            pass
    return found
