"""模式引擎测试。"""

import pytest
from src.engine import ModeEngine, classify_action, ActionType
from src.config import load_config, AppConfig, GlobalConfig, ModeConfig
from src.controller import GamepadListener, Button


class TestClassifyAction:
    def test_none_action(self):
        assert classify_action("null") == (ActionType.NONE, "")
        assert classify_action("") == (ActionType.NONE, "")

    def test_mouse_action(self):
        assert classify_action("mouse_left") == (ActionType.MOUSE, "left")
        assert classify_action("mouse_right") == (ActionType.MOUSE, "right")
        assert classify_action("mouse_middle") == (ActionType.MOUSE, "middle")
        assert classify_action("mouse_x") == (ActionType.MOUSE, "x")
        assert classify_action("mouse_y") == (ActionType.MOUSE, "y")

    def test_key_action(self):
        assert classify_action("key.tab") == (ActionType.KEY, "key.tab")
        assert classify_action("key.cmd+enter") == (ActionType.KEY, "key.cmd+enter")

    def test_switch_action(self):
        assert classify_action("switch_mode.vibe") == (ActionType.SWITCH, "vibe")
        assert classify_action("switch_mode.mouse") == (ActionType.SWITCH, "mouse")


class TestModeEngine:
    @pytest.fixture
    def sample_config(self):
        return AppConfig(
            global_=GlobalConfig(deadzone=0.15, mode_switch_hold_ms=500),
            modes={
                "mouse": ModeConfig(
                    name="mouse",
                    switch_button="SELECT",
                    mappings={
                        "LEFT_STICK_X": "mouse_x",
                        "LEFT_STICK_Y": "mouse_y",
                        "A": "mouse_left",
                        "B": "mouse_right",
                        "SELECT": "switch_mode.vibe",
                    },
                ),
                "vibe": ModeConfig(
                    name="vibe",
                    switch_button="SELECT",
                    mappings={
                        "A": "key.tab",
                        "B": "key.escape",
                        "SELECT": "switch_mode.mouse",
                    },
                ),
            },
        )

    @pytest.fixture
    def engine(self, sample_config):
        listener = GamepadListener(deadzone=0.15)
        return ModeEngine(sample_config, listener)

    def test_init(self, engine, sample_config):
        assert engine.current_mode == "mouse"
        assert engine.config is sample_config

    def test_tick_no_mode(self):
        """没有模式时 tick 不报错。"""
        config = AppConfig()
        listener = GamepadListener()
        engine = ModeEngine(config, listener)
        engine.tick()  # 应该安全返回

    def test_tick_with_mode(self, engine):
        engine.tick()

    def test_start_stop(self, engine):
        engine.start()
        engine.stop()

    def test_mode_switch_via_engine(self, engine):
        """模拟短按SELECT切换模式。"""
        engine.start()
        engine._switch_mode("vibe")
        assert engine.current_mode == "vibe"
        engine._switch_mode("mouse")
        assert engine.current_mode == "mouse"
        engine.stop()

    def test_invalid_mode_switch_ignored(self, engine):
        engine._switch_mode("nonexistent")
        assert engine.current_mode == "mouse"

    def test_button_callback_registered_after_start(self, engine):
        """start() 后按钮回调应被注册。"""
        initial = len(engine.listener._on_button)
        engine.start()
        assert len(engine.listener._on_button) > initial
