"""手柄输入捕获模块。

使用 `inputs` 库捕获手柄的：
- 连接/断开事件
- 摇杆（左/右）
- 按钮（A/B/X/Y等）
- 扳机（LT/RT）
- 十字键（DPAD）
"""

import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from inputs import devices, get_gamepad, UnpluggedError


# --- 常量 ---

class Button(Enum):
    """手柄按钮枚举（Xbox标准命名）。"""
    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    LB = auto()       # Left Bumper
    RB = auto()       # Right Bumper
    LT = auto()       # Left Trigger
    RT = auto()       # Right Trigger
    START = auto()
    SELECT = auto()
    LEFT_STICK = auto()
    RIGHT_STICK = auto()
    DPAD_UP = auto()
    DPAD_DOWN = auto()
    DPAD_LEFT = auto()
    DPAD_RIGHT = auto()


class Stick(Enum):
    """摇杆轴枚举。"""
    LEFT_X = auto()
    LEFT_Y = auto()
    RIGHT_X = auto()
    RIGHT_Y = auto()


# inputs库的事件码映射（Xbox手柄）
_EVENT_MAP = {
    # 按钮
    "BTN_SOUTH": Button.A,
    "BTN_EAST": Button.B,
    "BTN_NORTH": Button.Y,
    "BTN_WEST": Button.X,
    "BTN_TL": Button.LB,
    "BTN_TR": Button.RB,
    "BTN_START": Button.START,
    "BTN_SELECT": Button.SELECT,
    "BTN_THUMBL": Button.LEFT_STICK,
    "BTN_THUMBR": Button.RIGHT_STICK,
    # 扳机（作为按钮）
    "ABS_Z": Button.LT,
    "ABS_RZ": Button.RT,
    # 十字键
    "ABS_HAT0Y": None,   # DPAD上下，值：-1=上, 1=下
    "ABS_HAT0X": None,   # DPAD左右，值：-1=左, 1=右
    # 摇杆
    "ABS_X": Stick.LEFT_X,
    "ABS_Y": Stick.LEFT_Y,
    "ABS_RX": Stick.RIGHT_X,
    "ABS_RY": Stick.RIGHT_Y,
}

# 归一化摇杆范围（inputs库原始值范围）
_STICK_MAX = 32768


# --- 数据类型 ---

@dataclass
class StickState:
    """摇杆状态，值归一化到 [-1.0, 1.0]。"""
    x: float = 0.0
    y: float = 0.0


@dataclass
class TriggerState:
    """扳机状态，值归一化到 [0.0, 1.0]。"""
    value: float = 0.0
    pressed: bool = False   # 超过阈值视为按下
    threshold: float = 0.5


@dataclass
class ButtonState:
    """按钮状态。"""
    pressed: bool = False
    pressed_at: float = 0.0     # 按下时刻 (monotonic)
    released_at: float = 0.0    # 释放时刻
    hold_duration: float = 0.0  # 当前按住时长


@dataclass
class GamepadState:
    """手柄完整状态快照。"""
    left_stick: StickState = field(default_factory=StickState)
    right_stick: StickState = field(default_factory=StickState)
    left_trigger: TriggerState = field(default_factory=TriggerState)
    right_trigger: TriggerState = field(default_factory=TriggerState)
    buttons: dict[Button, ButtonState] = field(default_factory=dict)
    dpad: tuple[int, int] = (0, 0)  # (x, y): x∈{-1,0,1}, y∈{-1,0,1}
    timestamp: float = 0.0

    def __post_init__(self):
        for btn in Button:
            if btn not in self.buttons:
                self.buttons[btn] = ButtonState()

    def is_pressed(self, button: Button) -> bool:
        return self.buttons[button].pressed

    def hold_ms(self, button: Button) -> float:
        """返回按钮已按住的毫秒数，未按下时返回0。"""
        s = self.buttons[button]
        if not s.pressed:
            return 0.0
        return (time.monotonic() - s.pressed_at) * 1000


# --- 回调类型 ---

OnStateCallback = Callable[[GamepadState], None]
OnButtonCallback = Callable[[Button, bool], None]   # button, pressed
OnConnectCallback = Callable[[], None]
OnDisconnectCallback = Callable[[], None]


class GamepadListener:
    """手柄输入监听器。

    在后台线程中循环读取手柄事件，维护 GamepadState 快照，
    并通过回调通知状态变化。

    用法:
        listener = GamepadListener()
        listener.on_state(lambda state: print(state.left_stick))
        listener.start()
        ...
        listener.stop()
    """

    def __init__(self, deadzone: float = 0.15):
        self._deadzone = deadzone
        self._state = GamepadState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # 回调
        self._on_state: list[OnStateCallback] = []
        self._on_button: list[OnButtonCallback] = []
        self._on_connect: list[OnConnectCallback] = []
        self._on_disconnect: list[OnDisconnectCallback] = []

    # --- 回调注册 ---

    def on_state(self, cb: OnStateCallback):
        """注册状态更新回调（高频，每帧调用）。"""
        self._on_state.append(cb)

    def on_button(self, cb: OnButtonCallback):
        """注册按钮按下/释放回调。"""
        self._on_button.append(cb)

    def on_connect(self, cb: OnConnectCallback):
        """注册手柄连接回调。"""
        self._on_connect.append(cb)

    def on_disconnect(self, cb: OnDisconnectCallback):
        """注册手柄断开回调。"""
        self._on_disconnect.append(cb)

    # --- 生命周期 ---

    def start(self) -> bool:
        """启动监听线程。返回是否成功找到手柄。"""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gamepad-listener")
        self._thread.start()
        return True

    def stop(self):
        """停止监听。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @property
    def state(self) -> GamepadState:
        """获取当前手柄状态（线程安全）。"""
        with self._lock:
            return self._state

    # --- 内部 ---

    def _apply_deadzone(self, value: float) -> float:
        """对摇杆值施加死区处理。"""
        if abs(value) < self._deadzone:
            return 0.0
        # 重新映射：deadzone→1.0 映射到 0.0→1.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - self._deadzone) / (1.0 - self._deadzone)

    def _handle_event(self, code: str, value: int):
        """处理单个手柄事件，更新内部状态。"""
        now = time.monotonic()
        with self._lock:
            state = self._state
            state.timestamp = now

            if code in ("ABS_X", "ABS_Y", "ABS_RX", "ABS_RY"):
                stick = _EVENT_MAP[code]
                normalized = self._apply_deadzone(value / _STICK_MAX)
                if stick == Stick.LEFT_X:
                    state.left_stick.x = normalized
                elif stick == Stick.LEFT_Y:
                    state.left_stick.y = -normalized   # Y轴翻转
                elif stick == Stick.RIGHT_X:
                    state.right_stick.x = normalized
                elif stick == Stick.RIGHT_Y:
                    state.right_stick.y = -normalized

            elif code in ("ABS_Z", "ABS_RZ"):
                # 扳机：0-255
                trigger = state.left_trigger if code == "ABS_Z" else state.right_trigger
                trigger.value = value / 255.0
                was_pressed = trigger.pressed
                trigger.pressed = trigger.value > trigger.threshold
                if trigger.pressed and not was_pressed:
                    btn = Button.LT if code == "ABS_Z" else Button.RT
                    self._fire_button(btn, True, now)
                elif not trigger.pressed and was_pressed:
                    btn = Button.LT if code == "ABS_Z" else Button.RT
                    self._fire_button(btn, False, now)

            elif code == "ABS_HAT0Y":
                state.dpad = (state.dpad[0], -value)

            elif code == "ABS_HAT0X":
                state.dpad = (value, state.dpad[1])

            elif code in _EVENT_MAP and _EVENT_MAP[code] is not None:
                btn = _EVENT_MAP[code]
                pressed = bool(value)
                bs = state.buttons[btn]
                if pressed and not bs.pressed:
                    bs.pressed = True
                    bs.pressed_at = now
                    bs.hold_duration = 0.0
                    self._fire_button(btn, True, now)
                elif not pressed and bs.pressed:
                    bs.pressed = False
                    bs.released_at = now
                    bs.hold_duration = (now - bs.pressed_at) * 1000
                    self._fire_button(btn, False, now)

    def _fire_button(self, btn: Button, pressed: bool, now: float):
        """触发按钮回调（在锁内调用，避免死锁）。"""
        for cb in self._on_button:
            cb(btn, pressed)

    def _fire_state(self):
        """触发状态回调。"""
        state = self.state
        for cb in self._on_state:
            cb(state)

    def _loop(self):
        """后台监听主循环。"""
        # 等待手柄连接
        gamepad = None
        while self._running:
            try:
                gamepad_devices = devices.gamepads
                if not gamepad_devices:
                    time.sleep(0.5)
                    continue
                gamepad = get_gamepad()
                break
            except Exception:
                time.sleep(0.5)

        if gamepad is None:
            self._running = False
            return

        for cb in self._on_connect:
            cb()

        try:
            while self._running:
                try:
                    events = gamepad.read()
                except UnpluggedError:
                    for cb in self._on_disconnect:
                        cb()
                    # 尝试重新连接
                    gamepad = None
                    while self._running:
                        try:
                            gamepad = get_gamepad()
                            for cb in self._on_connect:
                                cb()
                            break
                        except Exception:
                            time.sleep(1.0)
                    if gamepad is None:
                        break
                    continue

                if not events:
                    time.sleep(0.001)
                    continue

                for event in events:
                    self._handle_event(event.code, event.state)

                self._fire_state()

        except Exception:
            pass
        finally:
            self._running = False


def find_controllers() -> list[str]:
    """列出当前连接的手柄名称。"""
    try:
        return [d.name for d in devices.gamepads]
    except Exception:
        return []
