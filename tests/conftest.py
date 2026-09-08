"""Keep unit tests from sending real mouse/keyboard input to the desktop."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_desktop_input(monkeypatch):
    monkeypatch.setattr("src.mouse_sim.Controller", MagicMock)
    monkeypatch.setattr("src.key_sim.Controller", MagicMock)
    monkeypatch.setattr("src.mouse_sim.MouseSimulator._click_via_uia", lambda *a, **k: False)
