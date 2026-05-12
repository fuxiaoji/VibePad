"""手柄相关的共享数据类型。

被 controller.py 和 controller_mock.py 共同引用，
保证 GamepadState / Button 等类型在两个模块中一致。
"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class Button(Enum):
    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    LB = auto()
    RB = auto()
    LT = auto()
    RT = auto()
    START = auto()
    SELECT = auto()
    LEFT_STICK = auto()
    RIGHT_STICK = auto()
    DPAD_UP = auto()
    DPAD_DOWN = auto()
    DPAD_LEFT = auto()
    DPAD_RIGHT = auto()


class Stick(Enum):
    LEFT_X = auto()
    LEFT_Y = auto()
    RIGHT_X = auto()
    RIGHT_Y = auto()


@dataclass
class StickState:
    x: float = 0.0
    y: float = 0.0


@dataclass
class TriggerState:
    value: float = 0.0
    pressed: bool = False
    threshold: float = 0.5


@dataclass
class ButtonState:
    pressed: bool = False
    pressed_at: float = 0.0
    released_at: float = 0.0
    hold_duration: float = 0.0


@dataclass
class GamepadState:
    left_stick: StickState = field(default_factory=StickState)
    right_stick: StickState = field(default_factory=StickState)
    left_trigger: TriggerState = field(default_factory=TriggerState)
    right_trigger: TriggerState = field(default_factory=TriggerState)
    buttons: dict[Button, ButtonState] = field(default_factory=dict)
    dpad: tuple[int, int] = (0, 0)
    timestamp: float = 0.0

    def __post_init__(self):
        for btn in Button:
            if btn not in self.buttons:
                self.buttons[btn] = ButtonState()

    def is_pressed(self, button: Button) -> bool:
        return self.buttons[button].pressed

    def hold_ms(self, button: Button) -> float:
        s = self.buttons[button]
        if not s.pressed:
            return 0.0
        return (time.monotonic() - s.pressed_at) * 1000


# 回调类型
OnStateCallback = Callable[[GamepadState], None]
OnButtonCallback = Callable[[Button, bool], None]
OnConnectCallback = Callable[[], None]
OnDisconnectCallback = Callable[[], None]
