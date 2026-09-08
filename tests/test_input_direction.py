"""Regression coverage for Bluetooth input and screen-coordinate directions."""

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.controller import GamepadListener, _GamepadBackendSDL2, _GamepadBackendPygame, _GamepadBackendXInput
from src.config import load_config
from src.engine import ModeEngine


@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("backend", ["sdl", "joystick", "xinput"])
def test_vertical_input_moves_and_scrolls_in_requested_direction(monkeypatch, backend, direction):
    import pygame
    from pygame._sdl2 import controller

    monkeypatch.setattr(pygame.event, "pump", lambda: None)
    monkeypatch.setattr(controller, "update", lambda: None)
    listener = GamepadListener(deadzone=0)
    if backend == "xinput":
        reader = _GamepadBackendXInput.__new__(_GamepadBackendXInput)
        reader._slot = 0
        reader._xinput = SimpleNamespace(XInputGetState=lambda *a: 0)
        reader._state = SimpleNamespace(Gamepad=SimpleNamespace(
            sThumbLX=0, sThumbLY=-direction * 24576,
            sThumbRX=0, sThumbRY=-direction * 24576,
            bLeftTrigger=0, bRightTrigger=0, wButtons=0))
        monkeypatch.setattr("src.controller.ctypes.byref", lambda value: value)
    else:
        device = MagicMock()
        scale = 32768 if backend == "sdl" else 1
        device.get_axis.side_effect = lambda i: direction * 0.75 * scale if i in (1, 3) else (-1 if i >= 4 and backend == "joystick" else 0)
        device.get_button.return_value = False
        device.get_numaxes.return_value = 6
        device.get_numbuttons.return_value = 10
        device.get_numhats.return_value = 0
        reader = (_GamepadBackendSDL2 if backend == "sdl" else _GamepadBackendPygame)(listener, device)
    listener._update_state(reader.read())
    assert listener.state.left_stick.y == pytest.approx(direction * 0.75)
    assert listener.state.right_stick.y == pytest.approx(direction * 0.75)
    engine = ModeEngine(load_config("config.yaml"), listener)
    engine._last_tick -= 0.2
    engine.tick()
    assert engine.mouse._controller.move.call_args.args[1] * direction > 0
    assert engine.mouse._controller.scroll.call_args.args[1] * direction < 0
    engine.navigator = MagicMock()
    engine._handle_stick_nav(0, listener.state.left_stick.y, 0.1)
    (engine.navigator.move_down if direction > 0 else engine.navigator.move_up).assert_called_once()


def test_background_input_enabled_before_pygame_initializes():
    env = os.environ.copy()
    env.pop("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", None)
    subprocess.run([sys.executable, "-c", "import src.controller; import os; assert os.environ['SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS'] == '1'"], env=env, check=True)
