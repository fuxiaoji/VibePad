"""手柄输入捕获模块 — hidapi + Xbox HID 报告解析。

使用 hidapi 直接读取 HID 输入报告，解析标准 Xbox 360/One 格式。
macOS 蓝牙/USB 手柄通用。

架构:
    后台线程: hid.read() 阻塞读取 → 解析报告 → 更新 GamepadState → 触发回调
    主线程:   读取 state 属性，消费数据
"""

import struct
import threading
import time
from typing import Optional

import hid

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


# ─── 监听器 ───

class GamepadListener:
    """手柄监听器 — hidapi 后端。

    在后台线程中阻塞读取 HID 报告，解析后更新状态并触发回调。
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

        self._device = None  # hid.device() instance

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
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gamepad-hid")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

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
        """将解析后的数据写入 GamepadState 并触发回调。"""
        now = time.monotonic()
        prev_buttons: dict[Button, bool] = {}

        with self._lock:
            state = self._state
            state.timestamp = now

            # 摇杆
            state.left_stick.x = self._apply_deadzone(parsed["lx"])
            state.left_stick.y = self._apply_deadzone(-parsed["ly"])  # Y轴翻转
            state.right_stick.x = self._apply_deadzone(parsed["rx"])
            state.right_stick.y = self._apply_deadzone(-parsed["ry"])

            # 扳机
            lt_val = parsed["lt"]
            rt_val = parsed["rt"]
            state.left_trigger.value = lt_val
            state.right_trigger.value = rt_val

            lt_was = state.left_trigger.pressed
            state.left_trigger.pressed = lt_val > state.left_trigger.threshold
            rt_was = state.right_trigger.pressed
            state.right_trigger.pressed = rt_val > state.right_trigger.threshold

            # 按钮变更检测
            new_buttons = parsed["buttons"]
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
            state.dpad = parsed["dpad"]

        # 在锁外触发回调（避免死锁）
        for btn, pressed in prev_buttons.items():
            for cb in self._on_button:
                cb(btn, pressed)

        for cb in self._on_state:
            cb(self._state)

    def _find_device(self):
        """查找并打开游戏手柄 HID 设备。"""
        for d in hid.enumerate():
            name = d.get("product_string", "")
            usage_page = d.get("usage_page", 0)
            usage = d.get("usage", 0)
            # 匹配游戏手柄设备 (Usage Page 0x01 Generic Desktop, Usage 0x05 Gamepad)
            if usage_page == 0x01 and usage in (0x04, 0x05, 0x06, 0x08):
                try:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    dev.set_nonblocking(False)  # 阻塞读取
                    print(f"手柄已连接: {name} (VID:{hex(d['vendor_id'])}, PID:{hex(d['product_id'])})")
                    return dev
                except Exception as e:
                    print(f"无法打开设备 {name}: {e}")
        return None

    def _loop(self):
        """后台主循环。"""
        # 等待手柄连接
        while self._running:
            self._device = self._find_device()
            if self._device:
                break
            time.sleep(1.0)

        if self._device is None:
            self._running = False
            return

        for cb in self._on_connect:
            cb()

        parser = XboxReportParser()

        while self._running:
            try:
                data = self._device.read(64, timeout_ms=100)
                if data and len(data) >= 14:
                    parsed = parser.parse(bytes(data))
                    if parsed:
                        self._update_state(parsed)
            except (ValueError, OSError):
                # 设备断开
                self._device = None
                for cb in self._on_disconnect:
                    cb()
                # 重连
                while self._running:
                    time.sleep(0.5)
                    self._device = self._find_device()
                    if self._device:
                        for cb in self._on_connect:
                            cb()
                        break
            except Exception:
                time.sleep(0.01)


def find_controllers() -> list[str]:
    """列出连接的游戏手柄。"""
    found = []
    for d in hid.enumerate():
        if d.get("usage_page") == 0x01 and d.get("usage") in (0x04, 0x05, 0x06):
            found.append(d.get("product_string", f"{hex(d['vendor_id'])}:{hex(d['product_id'])}"))
    return found
