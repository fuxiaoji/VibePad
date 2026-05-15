"""键盘模拟模块。

将手柄按钮映射为键盘按键，支持单键、组合键和长按。
使用 pynput 底层控制。

配置字符串格式:
    key.<keyname>            → 单键
    key.<mod>+<keyname>      → 组合键
    null                     → 无映射

修饰键: cmd, ctrl, alt, shift
特殊键: tab, enter, escape, space, backspace, delete,
        up, down, left, right, home, end, page_up, page_down
F键: f1-f12
字母/数字/符号: a-z, 0-9, ., ,, /, ;, ', [, ], -, =
"""

import sys
from enum import Enum, auto
from typing import Optional

from pynput.keyboard import Controller, Key


# 特殊键名 → pynput Key 映射
_SPECIAL_KEYS = {
    "tab": Key.tab,
    "enter": Key.enter,
    "return": Key.enter,
    "escape": Key.esc,
    "esc": Key.esc,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "page_up": Key.page_up,
    "page_down": Key.page_down,
    "media_volume_up": Key.media_volume_up,
    "media_volume_down": Key.media_volume_down,
    "media_volume_mute": Key.media_volume_mute,
    "media_play_pause": Key.media_play_pause,
    "media_next": Key.media_next,
    "media_previous": Key.media_previous,
}

# F键
for i in range(1, 13):
    _SPECIAL_KEYS[f"f{i}"] = getattr(Key, f"f{i}", None)


# 修饰键名 → pynput Key
_MODIFIERS = {
    "cmd": Key.cmd,
    "command": Key.cmd,
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "alt": Key.alt,
    "option": Key.alt,
    "shift": Key.shift,
}

# 非 macOS 平台上将 cmd/command 映射到 ctrl
if sys.platform != "darwin":
    _MODIFIERS["cmd"] = Key.ctrl
    _MODIFIERS["command"] = Key.ctrl


def _parse_key(key_name: str):
    """将键名字符串解析为 pynput Key 或字符。

    Returns:
        pynput Key 或单字符，不识别的返回 None
    """
    key_name = key_name.strip().lower()

    # 特殊键
    if key_name in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key_name]

    # 单字符（字母、数字、符号）
    if len(key_name) == 1:
        return key_name

    return None


def _parse_action(action_str: str) -> Optional[dict]:
    """解析动作字符串为结构化动作。

    Args:
        action_str: 如 "key.cmd+enter", "key.tab", "key.shift+a"

    Returns:
        {'modifiers': [Key.cmd], 'key': Key.enter} 或 None（无效/null）
    """
    if not action_str or action_str == "null":
        return None

    if not action_str.startswith("key."):
        return None

    key_part = action_str[4:]  # 去掉 "key."

    # 检查是否有修饰键
    if "+" in key_part:
        parts = key_part.split("+")
        modifiers = []
        final_key = None
        for p in parts:
            p = p.strip().lower()
            if p in _MODIFIERS:
                modifiers.append(_MODIFIERS[p])
            else:
                final_key = _parse_key(p)
        if final_key is None:
            return None
        return {"modifiers": modifiers, "key": final_key}
    else:
        k = _parse_key(key_part)
        if k is None:
            return None
        return {"modifiers": [], "key": k}


class KeySimulator:
    """键盘模拟器。

    用法:
        keys = KeySimulator()
        keys.tap("key.tab")              # 按一下Tab
        keys.combo("key.cmd+enter")      # 组合键
        keys.hold("key.shift")           # 按住Shift
        keys.release("key.shift")        # 释放Shift
    """

    def __init__(self):
        self._controller = Controller()
        self._held: list = []  # 当前按住的键

    def tap(self, action_str: str):
        """按下并释放一个键。"""
        action = _parse_action(action_str)
        if action is None:
            return
        self._do_combo(action["modifiers"], action["key"])

    def combo(self, action_str: str):
        """按下组合键（按住修饰键，按主键，释放修饰键）。"""
        self.tap(action_str)

    def press(self, action_str: str):
        """按下一个键并保持（用于长按场景）。"""
        action = _parse_action(action_str)
        if action is None:
            return
        for mod in action["modifiers"]:
            self._controller.press(mod)
        self._controller.press(action["key"])
        self._held.append(action)

    def release(self, action_str: str):
        """释放之前按下的键。"""
        action = _parse_action(action_str)
        if action is None:
            return
        if action in self._held:
            self._held.remove(action)
        self._controller.release(action["key"])
        for mod in reversed(action["modifiers"]):
            self._controller.release(mod)

    def release_all(self):
        """释放所有按住的键。"""
        for action in list(self._held):
            self._controller.release(action["key"])
            for mod in reversed(action["modifiers"]):
                self._controller.release(mod)
        self._held.clear()

    def type_text(self, text: str):
        """输入一段文字。"""
        self._controller.type(text)

    # --- 内部 ---

    def _do_combo(self, modifiers: list, key):
        """执行一次组合键（按下修饰键→按主键→释放修饰键）。"""
        for mod in modifiers:
            self._controller.press(mod)
        self._controller.press(key)
        self._controller.release(key)
        for mod in reversed(modifiers):
            self._controller.release(mod)
