"""键盘模拟模块测试。"""

import pytest
from src.key_sim import KeySimulator, _parse_action, _parse_key


class TestParseKey:
    def test_special_keys(self):
        assert _parse_key("tab") is not None
        assert _parse_key("enter") is not None
        assert _parse_key("escape") is not None
        assert _parse_key("space") is not None
        assert _parse_key("f1") is not None
        assert _parse_key("f12") is not None

    def test_single_character(self):
        assert _parse_key("a") == "a"
        assert _parse_key("Z") == "z"
        assert _parse_key("1") == "1"

    def test_unknown_key(self):
        assert _parse_key("nonexistent_key_xyz") is None


class TestParseAction:
    def test_null_action(self):
        assert _parse_action("null") is None
        assert _parse_action("") is None

    def test_non_key_action(self):
        assert _parse_action("mouse_left") is None
        assert _parse_action("switch_mode.vibe") is None

    def test_single_key(self):
        action = _parse_action("key.tab")
        assert action is not None
        assert action["modifiers"] == []

    def test_combo_key(self):
        action = _parse_action("key.cmd+enter")
        assert action is not None
        assert len(action["modifiers"]) == 1
        assert action["key"] is not None

    def test_multi_modifier(self):
        action = _parse_action("key.cmd+shift+a")
        assert action is not None
        assert len(action["modifiers"]) == 2

    def test_invalid_combo(self):
        action = _parse_action("key.cmd+nonexistent")
        assert action is None


class TestKeySimulator:
    def test_init(self):
        k = KeySimulator()
        assert k._held == []

    def test_tap_null(self):
        """映射为空时不报错。"""
        k = KeySimulator()
        k.tap("null")
        k.tap("")

    def test_tap_single_key(self):
        k = KeySimulator()
        k.tap("key.tab")

    def test_tap_combo(self):
        k = KeySimulator()
        k.tap("key.cmd+enter")

    def test_press_release(self):
        k = KeySimulator()
        k.press("key.shift")
        k.release("key.shift")
        assert len(k._held) == 0

    def test_release_all(self):
        k = KeySimulator()
        k.press("key.cmd")
        k.press("key.shift")
        k.release_all()
        assert len(k._held) == 0

    def test_type_text(self):
        k = KeySimulator()
        k.type_text("hello")

    def test_combo_alias(self):
        k = KeySimulator()
        k.combo("key.cmd+v")
