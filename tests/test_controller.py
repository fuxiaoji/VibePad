"""手柄输入捕获模块单元测试。"""

import pytest
from src.controller import (
    GamepadListener,
    GamepadState,
    StickState,
    TriggerState,
    ButtonState,
    Button,
    Stick,
    find_controllers,
)


class TestGamepadState:
    def test_initial_state(self):
        state = GamepadState()
        assert state.left_stick.x == 0.0
        assert state.left_stick.y == 0.0
        assert state.right_stick.x == 0.0
        assert state.right_stick.y == 0.0
        assert state.dpad == (0, 0)
        assert not state.is_pressed(Button.A)
        assert state.hold_ms(Button.A) == 0.0

    def test_button_press_state(self):
        state = GamepadState()
        state.buttons[Button.A] = ButtonState(pressed=True)
        assert state.is_pressed(Button.A)
        assert not state.is_pressed(Button.B)

    def test_all_buttons_initialized(self):
        state = GamepadState()
        for btn in Button:
            assert btn in state.buttons
            assert isinstance(state.buttons[btn], ButtonState)


class TestGamepadListener:
    def test_init_default_deadzone(self):
        listener = GamepadListener()
        assert listener._deadzone == 0.15

    def test_init_custom_deadzone(self):
        listener = GamepadListener(deadzone=0.2)
        assert listener._deadzone == 0.2

    def test_apply_deadzone_zero(self):
        listener = GamepadListener(deadzone=0.15)
        assert listener._apply_deadzone(0.0) == 0.0

    def test_apply_deadzone_within_deadzone(self):
        listener = GamepadListener(deadzone=0.15)
        assert listener._apply_deadzone(0.10) == 0.0
        assert listener._apply_deadzone(-0.10) == 0.0

    def test_apply_deadzone_at_edge(self):
        listener = GamepadListener(deadzone=0.15)
        result = listener._apply_deadzone(0.15)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_apply_deadzone_above_threshold(self):
        listener = GamepadListener(deadzone=0.15)
        # 0.5 → (0.5 - 0.15)/(1 - 0.15) = 0.35/0.85 ≈ 0.4118
        result = listener._apply_deadzone(0.5)
        assert result == pytest.approx(0.41176, rel=1e-3)

    def test_apply_deadzone_negative(self):
        listener = GamepadListener(deadzone=0.15)
        result = listener._apply_deadzone(-0.5)
        assert result == pytest.approx(-0.41176, rel=1e-3)

    def test_apply_deadzone_full_deflection(self):
        listener = GamepadListener(deadzone=0.15)
        result = listener._apply_deadzone(1.0)
        assert result == pytest.approx(1.0, rel=1e-3)
        result = listener._apply_deadzone(-1.0)
        assert result == pytest.approx(-1.0, rel=1e-3)

    def test_state_property_returns_same_reference(self):
        listener = GamepadListener()
        s1 = listener.state
        s2 = listener.state
        # state 返回内部状态的直接引用（性能考虑，避免每帧拷贝）
        assert s1 is s2

    def test_start_stop(self):
        listener = GamepadListener()
        # 无手柄时启动不会崩溃
        listener.start()
        listener.stop()
        assert not listener._running

    def test_button_callback_registration(self):
        listener = GamepadListener()
        calls = []

        def cb(btn, pressed):
            calls.append((btn, pressed))

        listener.on_button(cb)
        # 模拟内部触发
        listener._on_button.append(cb)
        assert len(listener._on_button) >= 1

    def test_find_controllers_returns_list(self):
        result = find_controllers()
        assert isinstance(result, list)


class TestButtonEnum:
    def test_all_buttons_unique(self):
        values = [b.value for b in Button]
        assert len(values) == len(set(values))

    def test_stick_enum(self):
        axes = [Stick.LEFT_X, Stick.LEFT_Y, Stick.RIGHT_X, Stick.RIGHT_Y]
        assert len(axes) == 4
