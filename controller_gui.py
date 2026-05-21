"""手柄控制面板 GUI — 实时状态监控 + 按键绑定编辑器。

用法:
    python controller_gui.py
    python controller_gui.py --config my_config.yaml

需要 PyQt6 + pygame (SDL2)。
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QTabWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QFrame,
    QPushButton,
    QSlider,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QLineEdit,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QFont,
)

from src.config import load_config, save_config, AppConfig
from src.types import Button
from src.engine import ModeEngine, classify_action, ActionType

# 自动选择后端：优先真手柄，不可用则键盘模拟
_using_mock = False
_force_mock = "--mock" in sys.argv
if _force_mock:
    from src.controller_mock import GamepadListener, find_controllers
    _using_mock = True
    print("强制使用键盘模拟手柄 (WASD=左摇杆 IJKL=右摇杆 Space=A Tab=SELECT)")
else:
    try:
        from src.controller import GamepadListener, find_controllers, enumerate_hid_devices
        ctrls = find_controllers()
        if ctrls:
            print(f"使用物理手柄: {ctrls[0]}")
        else:
            print("未检测到手柄 — 使用物理监听器（插上手柄后自动识别）")
        enumerate_hid_devices()
    except ImportError:
        from src.controller_mock import GamepadListener, find_controllers
        _using_mock = True
        print("使用键盘模拟手柄 (WASD=左摇杆 IJKL=右摇杆 Space=A Tab=SELECT)")


# ─── 颜色常量 ───

BG_DARK = QColor(30, 30, 30)
BG_PANEL = QColor(45, 45, 50)
BORDER = QColor(70, 70, 75)
TEXT_PRIMARY = QColor(220, 220, 220)
TEXT_SECONDARY = QColor(150, 150, 155)
ACCENT = QColor(80, 160, 255)
ACCENT_PRESSED = QColor(255, 120, 60)
STICK_CIRCLE = QColor(180, 200, 220)
STICK_DOT = QColor(255, 255, 255)
TRIGGER_FILL = QColor(80, 180, 120)
DPAD_ACTIVE = QColor(255, 200, 60)
MODE_COLORS = {
    "mouse": QColor(80, 160, 255),
    "vibe": QColor(200, 120, 255),  # vibe 现在是 mouse 的子层
    "vim": QColor(80, 255, 160),
}
LAYER_COLORS = {
    "vibe": QColor(200, 120, 255),
}

# ─── 可映射的手柄输入列表 ───

CONTROLLER_INPUTS = [
    # (标识符, 显示名称, 分类)
    ("LEFT_STICK_X", "左摇杆 X", "摇杆"),
    ("LEFT_STICK_Y", "左摇杆 Y", "摇杆"),
    ("RIGHT_STICK_X", "右摇杆 X", "摇杆"),
    ("RIGHT_STICK_Y", "右摇杆 Y", "摇杆"),
    ("A", "A 键", "按钮"),
    ("B", "B 键", "按钮"),
    ("X", "X 键", "按钮"),
    ("Y", "Y 键", "按钮"),
    ("LB", "LB 左肩键", "肩键"),
    ("RB", "RB 右肩键", "肩键"),
    ("LT", "LT 左扳机", "扳机"),
    ("RT", "RT 右扳机", "扳机"),
    ("START", "START", "功能"),
    ("SELECT", "SELECT", "功能"),
    ("LEFT_STICK", "左摇杆按下", "摇杆按钮"),
    ("RIGHT_STICK", "右摇杆按下", "摇杆按钮"),
    ("DPAD_UP", "十字键 上", "十字键"),
    ("DPAD_DOWN", "十字键 下", "十字键"),
    ("DPAD_LEFT", "十字键 左", "十字键"),
    ("DPAD_RIGHT", "十字键 右", "十字键"),
]

# ─── 鼠标动作列表 ───

MOUSE_ACTIONS = {
    "left": "鼠标左键",
    "right": "鼠标右键",
    "middle": "鼠标中键",
    "drag": "长按拖拽/短按点击",
    "x": "鼠标水平移动",
    "y": "鼠标垂直移动",
    "scroll_up": "滚轮上滚",
    "scroll_down": "滚轮下滚",
    "scroll_left": "滚轮左滚",
    "scroll_right": "滚轮右滚",
    "scroll_x": "水平滚轮 (模拟)",
    "scroll_y": "垂直滚轮 (模拟)",
    "speed_hold": "按住光标加速",
}

# ─── 导航动作列表 ───

NAV_ACTIONS = {
    "up": "向上移动焦点",
    "down": "向下移动焦点",
    "left": "向左移动焦点",
    "right": "向右移动焦点",
    "click": "左键点击焦点元素",
    "right_click": "右键点击焦点元素",
    "double_click": "双击焦点元素",
    "escape": "按 Escape 关闭弹窗",
    "tab": "按 Tab 焦点回退",
    "enter": "按 Enter 确认",
    "scroll_up": "向上滚动",
    "scroll_down": "向下滚动",
    "prev_tab": "上一个标签页",
    "next_tab": "下一个标签页",
    "refresh": "重新扫描UI元素",
    "speed_hold": "按住倍速播放 (视频)",
    "task_view": "Win+Tab 任务视图",
    "switch_input": "切换输入语言 (Win+Space)",
    "open_keyboard": "打开系统虚拟键盘",
}


# ─── 摇杆控件 ───

class JoystickWidget(QWidget):
    """可视化摇杆：背景十字线 + 可移动的圆点。"""

    def __init__(self, label="", parent=None):
        super().__init__(parent)
        self._label = label
        self._x = 0.0
        self._y = 0.0
        self.setMinimumSize(140, 140)
        self.setMaximumSize(200, 200)

    def set_position(self, x: float, y: float):
        self._x = max(-1.0, min(1.0, x))
        self._y = max(-1.0, min(1.0, y))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 20

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_PANEL)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        pen = QPen(BORDER, 1, Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
        p.drawLine(QPointF(cx, cy - radius), QPointF(cx, cy + radius))
        p.drawEllipse(QPointF(cx, cy), int(radius * 0.5), int(radius * 0.5))
        p.drawEllipse(QPointF(cx, cy), int(radius), int(radius))

        pen = QPen(BORDER, 2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        dot_x = cx + self._x * radius
        dot_y = cy - self._y * radius

        p.setPen(QPen(BORDER, 1))
        p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))

        dot_r = 10
        p.setPen(QPen(STICK_DOT, 2))
        p.setBrush(STICK_CIRCLE)
        p.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

        p.setPen(TEXT_SECONDARY)
        p.setFont(QFont("Sans", 10))
        p.drawText(QRectF(0, h - 22, w, 20), Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()


# ─── 按钮网格控件 ───

class ButtonGridWidget(QWidget):
    """手柄全部按钮的状态网格。"""

    BUTTON_LAYOUT = [
        (0, 0, Button.LB, "LB"), (0, 1, Button.LT, "LT"),
        (0, 3, Button.RT, "RT"), (0, 4, Button.RB, "RB"),
        (1, 1, Button.SELECT, "SEL"), (1, 2, Button.START, "STA"),
        (2, 0, Button.DPAD_UP, "↑"), (2, 1, Button.DPAD_LEFT, "←"),
        (2, 2, Button.DPAD_RIGHT, "→"), (2, 3, Button.DPAD_DOWN, "↓"),
        (3, 1, Button.LEFT_STICK, "LS"), (3, 2, Button.RIGHT_STICK, "RS"),
        (3, 3, Button.Y, "Y"),
        (4, 2, Button.X, "X"), (4, 3, Button.B, "B"), (4, 4, Button.A, "A"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._button_states: dict[Button, bool] = {}
        layout = QGridLayout(self)
        layout.setSpacing(6)
        self._labels: dict[Button, QLabel] = {}

        for row, col, btn, text in self.BUTTON_LAYOUT:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(48, 36)
            lbl.setFont(QFont("Sans", 11, QFont.Weight.Bold))
            self._style_button(lbl, False)
            layout.addWidget(lbl, row, col)
            self._labels[btn] = lbl

        self.setFixedSize(310, 230)

    def _style_button(self, lbl: QLabel, pressed: bool):
        if pressed:
            lbl.setStyleSheet(
                f"background: {ACCENT_PRESSED.name()}; color: white; "
                "border-radius: 8px; border: 2px solid #ff6030;"
            )
        else:
            lbl.setStyleSheet(
                f"background: {BG_PANEL.name()}; color: {TEXT_SECONDARY.name()}; "
                "border-radius: 8px; border: 1px solid #404045;"
            )

    def update_button(self, btn: Button, pressed: bool):
        if btn in self._labels:
            self._style_button(self._labels[btn], pressed)

    def clear_all(self):
        for btn in self._labels:
            self._style_button(self._labels[btn], False)


# ─── 扳机条 ───

class TriggerBar(QWidget):
    """显示单个扳机值的进度条。"""

    def __init__(self, label="", parent=None):
        super().__init__(parent)
        self._label = label
        self._value = 0.0
        self._active = False
        self.setMinimumHeight(50)

    def set_value(self, value: float, active: bool):
        self._value = value
        self._active = active
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        bar_h = 14
        bar_y = (h - bar_h) // 2 + 6
        bar_w = w - 30

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(50, 50, 55))
        p.drawRoundedRect(QRectF(10, bar_y, bar_w, bar_h), 4, 4)

        fill_w = int(bar_w * self._value)
        if fill_w > 0:
            color = ACCENT_PRESSED if self._active else TRIGGER_FILL
            p.setBrush(color)
            p.drawRoundedRect(QRectF(10, bar_y, fill_w, bar_h), 4, 4)

        threshold_x = 10 + int(bar_w * 0.5)
        p.setPen(QPen(QColor(100, 100, 110), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(threshold_x, bar_y - 2), QPointF(threshold_x, bar_y + bar_h + 2))

        p.setPen(TEXT_PRIMARY)
        p.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        p.drawText(QRectF(10, 0, bar_w, bar_y), Qt.AlignmentFlag.AlignLeft, self._label)
        p.drawText(QRectF(10, 0, bar_w, bar_y), Qt.AlignmentFlag.AlignRight, f"{self._value:.2f}")

        p.end()


# ─── 按键绑定编辑对话框 ───

class BindingEditorDialog(QDialog):
    """编辑单个按键绑定的弹出对话框。"""

    def __init__(self, input_name: str, input_display: str, current_action: str,
                 mode_names: list[str], parent=None):
        super().__init__(parent)
        self._input_name = input_name
        self._mode_names = mode_names
        self._result_action = current_action

        self.setWindowTitle(f"编辑绑定 — {input_display}")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background: {BG_DARK.name()};")

        self._build_ui(current_action)

    def _build_ui(self, current_action: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        # 输入名称
        name_lbl = QLabel(self._input_name)
        name_lbl.setFont(QFont("Sans", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {ACCENT.name()};")
        layout.addWidget(name_lbl)

        # 解析当前动作
        action_type, param = classify_action(current_action)

        # --- 动作类型 ---
        type_layout = QHBoxLayout()
        type_lbl = QLabel("动作类型:")
        type_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        type_layout.addWidget(type_lbl)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["null", "mouse", "key", "switch_mode", "nav", "voice"])
        self._type_combo.setStyleSheet(self._combo_style())
        type_layout.addWidget(self._type_combo, 1)
        layout.addLayout(type_layout)

        # --- 鼠标子选项 ---
        self._mouse_group = QWidget()
        mouse_layout = QHBoxLayout(self._mouse_group)
        mouse_layout.setContentsMargins(0, 0, 0, 0)
        mouse_lbl = QLabel("鼠标动作:")
        mouse_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        mouse_layout.addWidget(mouse_lbl)
        self._mouse_combo = QComboBox()
        self._mouse_combo.addItems(list(MOUSE_ACTIONS.keys()))
        self._mouse_combo.setStyleSheet(self._combo_style())
        mouse_layout.addWidget(self._mouse_combo, 1)
        layout.addWidget(self._mouse_group)

        # --- 键盘子选项 ---
        self._key_group = QWidget()
        key_layout = QVBoxLayout(self._key_group)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)

        # 修饰键
        mod_layout = QHBoxLayout()
        mod_lbl = QLabel("修饰键:")
        mod_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        mod_layout.addWidget(mod_lbl)
        self._ctrl_cb = QCheckBox("Ctrl")
        self._shift_cb = QCheckBox("Shift")
        self._alt_cb = QCheckBox("Alt")
        for cb in (self._ctrl_cb, self._shift_cb, self._alt_cb):
            cb.setStyleSheet(self._checkbox_style())
            mod_layout.addWidget(cb)
        mod_layout.addStretch()
        key_layout.addLayout(mod_layout)

        # 按键名
        key_name_layout = QHBoxLayout()
        key_name_lbl = QLabel("按键:")
        key_name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        key_name_layout.addWidget(key_name_lbl)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("例如: enter, tab, a, space...")
        self._key_edit.setStyleSheet(self._lineedit_style())
        key_name_layout.addWidget(self._key_edit, 1)
        key_layout.addLayout(key_name_layout)

        layout.addWidget(self._key_group)

        # --- 模式切换子选项 ---
        self._switch_group = QWidget()
        switch_layout = QHBoxLayout(self._switch_group)
        switch_layout.setContentsMargins(0, 0, 0, 0)
        switch_lbl = QLabel("目标模式:")
        switch_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        switch_layout.addWidget(switch_lbl)
        self._switch_combo = QComboBox()
        self._switch_combo.addItems(self._mode_names)
        self._switch_combo.setStyleSheet(self._combo_style())
        switch_layout.addWidget(self._switch_combo, 1)
        layout.addWidget(self._switch_group)

        # --- 导航子选项 ---
        self._nav_group = QWidget()
        nav_layout = QHBoxLayout(self._nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_lbl = QLabel("导航动作:")
        nav_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        nav_layout.addWidget(nav_lbl)
        self._nav_combo = QComboBox()
        self._nav_combo.addItems(list(NAV_ACTIONS.keys()))
        self._nav_combo.setStyleSheet(self._combo_style())
        nav_layout.addWidget(self._nav_combo, 1)
        layout.addWidget(self._nav_group)

        # --- 预览 ---
        preview_layout = QHBoxLayout()
        preview_lbl = QLabel("预览:")
        preview_lbl.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        preview_layout.addWidget(preview_lbl)
        self._preview_label = QLabel("")
        self._preview_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self._preview_label.setStyleSheet(f"color: {TRIGGER_FILL.name()};")
        preview_layout.addWidget(self._preview_label, 1)
        layout.addLayout(preview_layout)

        # --- 设置初始值 ---
        if action_type == ActionType.MOUSE:
            self._type_combo.setCurrentText("mouse")
            idx = self._mouse_combo.findText(param)
            if idx >= 0:
                self._mouse_combo.setCurrentIndex(idx)
        elif action_type == ActionType.KEY:
            self._type_combo.setCurrentText("key")
            key_str = param[4:]  # 去掉 "key."
            self._parse_key_string(key_str)
        elif action_type == ActionType.SWITCH:
            self._type_combo.setCurrentText("switch_mode")
            idx = self._switch_combo.findText(param)
            if idx >= 0:
                self._switch_combo.setCurrentIndex(idx)
        elif action_type == ActionType.NAVIGATE:
            self._type_combo.setCurrentText("nav")
            idx = self._nav_combo.findText(param)
            if idx >= 0:
                self._nav_combo.setCurrentIndex(idx)
        elif action_type == ActionType.VOICE:
            self._type_combo.setCurrentText("voice")
        else:
            self._type_combo.setCurrentText("null")

        self._update_visibility()
        self._update_preview()

        # 信号连接
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._mouse_combo.currentTextChanged.connect(self._on_sub_changed)
        self._key_edit.textChanged.connect(self._on_sub_changed)
        self._ctrl_cb.toggled.connect(self._on_sub_changed)
        self._shift_cb.toggled.connect(self._on_sub_changed)
        self._alt_cb.toggled.connect(self._on_sub_changed)
        self._switch_combo.currentTextChanged.connect(self._on_sub_changed)
        self._nav_combo.currentTextChanged.connect(self._on_sub_changed)

        # --- 按钮 ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(f"""
            QPushButton {{
                background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()};
                border: 1px solid {BORDER.name()}; border-radius: 6px;
                padding: 8px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {ACCENT.name()}; color: white; }}
        """)
        layout.addWidget(buttons)

    def _parse_key_string(self, key_str: str):
        """解析 key.ctrl+shift+enter 格式。"""
        parts = key_str.split("+")
        for p in parts:
            p = p.strip()
            if p == "ctrl":
                self._ctrl_cb.setChecked(True)
            elif p == "shift":
                self._shift_cb.setChecked(True)
            elif p == "alt":
                self._alt_cb.setChecked(True)
            else:
                self._key_edit.setText(p)

    def _update_visibility(self):
        t = self._type_combo.currentText()
        self._mouse_group.setVisible(t == "mouse")
        self._key_group.setVisible(t == "key")
        self._switch_group.setVisible(t == "switch_mode")
        self._nav_group.setVisible(t == "nav")
        # voice 类型无子选项

    def _on_type_changed(self, _text: str):
        self._update_visibility()
        self._update_preview()

    def _on_sub_changed(self, *_args):
        self._update_preview()

    def _update_preview(self):
        action = self._build_action_string()
        self._preview_label.setText(action)

    def _build_action_string(self) -> str:
        t = self._type_combo.currentText()
        if t == "null":
            return "null"
        elif t == "mouse":
            return f"mouse_{self._mouse_combo.currentText()}"
        elif t == "key":
            modifiers = []
            if self._ctrl_cb.isChecked():
                modifiers.append("ctrl")
            if self._shift_cb.isChecked():
                modifiers.append("shift")
            if self._alt_cb.isChecked():
                modifiers.append("alt")
            key_name = self._key_edit.text().strip()
            parts = modifiers + ([key_name] if key_name else [])
            return f"key.{'+'.join(parts)}" if parts else "key."
        elif t == "switch_mode":
            return f"switch_mode.{self._switch_combo.currentText()}"
        elif t == "nav":
            return f"nav.{self._nav_combo.currentText()}"
        elif t == "voice":
            return "voice_input"
        return "null"

    def _on_accept(self):
        self._result_action = self._build_action_string()
        self.accept()

    def get_action_string(self) -> str:
        return self._result_action

    # ── 样式 ──

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"border: 1px solid {BORDER.name()}; border-radius: 4px; padding: 4px 8px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ "
            f"background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"selection-background: {ACCENT.name()}; border: 1px solid {BORDER.name()}; }}"
        )

    def _checkbox_style(self) -> str:
        return f"color: {TEXT_PRIMARY.name()};"

    def _lineedit_style(self) -> str:
        return (
            f"QLineEdit {{ background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"border: 1px solid {BORDER.name()}; border-radius: 4px; padding: 4px 8px; }}"
        )


# ─── 仪表盘标签页 ───

class DashboardTab(QWidget):
    """手柄实时状态可视化。"""

    def __init__(self, listener: GamepadListener, engine: ModeEngine,
                 config: AppConfig, config_path: str,
                 mock: bool, log_fn, parent=None):
        super().__init__(parent)
        self._listener = listener
        self._engine = engine
        self._config = config
        self._config_path = config_path
        self._mock = mock
        self._log_fn = log_fn
        self._connected = False
        self._frame_count = 0
        self._fps_timer = time.monotonic()
        self._fps = 0

        self.setStyleSheet(f"background: {BG_DARK.name()};")
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        # ── 顶部状态栏 ──
        top = QHBoxLayout()

        self._connection_label = QLabel("搜索手柄...")
        self._connection_label.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        self._connection_label.setStyleSheet(f"color: {ACCENT_PRESSED.name()};")
        top.addWidget(self._connection_label)

        self._find_btn = QPushButton("🔍 查找手柄")
        self._find_btn.setFont(QFont("Sans", 10))
        self._find_btn.setFixedWidth(100)
        self._find_btn.setFixedHeight(28)
        self._find_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a; color: #ddd; border: 1px solid #555;
                border-radius: 4px; padding: 4px 8px;
            }
            QPushButton:hover { background-color: #4a4a4a; border-color: #77a; }
            QPushButton:pressed { background-color: #555; }
        """)
        self._find_btn.clicked.connect(self._on_find_controller)
        top.addWidget(self._find_btn)

        top.addStretch()

        mode_layout = QVBoxLayout()
        mode_title = QLabel("当前模式")
        mode_title.setFont(QFont("Sans", 9))
        mode_title.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        mode_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_layout.addWidget(mode_title)
        self._mode_label = QLabel("mouse")
        self._mode_label.setFont(QFont("Sans", 18, QFont.Weight.Bold))
        self._mode_label.setStyleSheet(f"color: {MODE_COLORS['mouse'].name()};")
        self._mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_layout.addWidget(self._mode_label)
        self._layer_label = QLabel("")
        self._layer_label.setFont(QFont("Sans", 9))
        self._layer_label.setStyleSheet(f"color: {QColor(200, 120, 255).name()};")
        self._layer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_layout.addWidget(self._layer_label)
        top.addLayout(mode_layout)

        top.addStretch()

        self._fps_label = QLabel("FPS: --")
        self._fps_label.setFont(QFont("Sans", 11))
        self._fps_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        top.addWidget(self._fps_label)

        main_layout.addLayout(top)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER.name()};")
        main_layout.addWidget(sep)

        # ── 中部：摇杆 + 按钮 ──
        middle = QHBoxLayout()
        middle.setSpacing(20)

        self._left_stick = JoystickWidget("左摇杆")
        middle.addWidget(self._left_stick)

        middle.addStretch()

        btn_group = QGroupBox("手柄按钮")
        btn_group.setFont(QFont("Sans", 10))
        btn_group.setStyleSheet(self._group_style())
        btn_layout = QVBoxLayout(btn_group)
        self._button_grid = ButtonGridWidget()
        btn_layout.addWidget(self._button_grid)
        middle.addWidget(btn_group)

        middle.addStretch()

        self._right_stick = JoystickWidget("右摇杆")
        middle.addWidget(self._right_stick)

        main_layout.addLayout(middle)

        # ── 底部：扳机 + 十字键 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        trigger_group = QGroupBox("扳机 / 肩键")
        trigger_group.setFont(QFont("Sans", 10))
        trigger_group.setStyleSheet(self._group_style())
        trigger_layout = QVBoxLayout(trigger_group)
        self._lt_bar = TriggerBar("LT 左扳机")
        self._rt_bar = TriggerBar("RT 右扳机")
        trigger_layout.addWidget(self._lt_bar)
        trigger_layout.addWidget(self._rt_bar)
        bottom.addWidget(trigger_group)

        dpad_group = QGroupBox("十字键")
        dpad_group.setFont(QFont("Sans", 10))
        dpad_group.setStyleSheet(self._group_style())
        dpad_layout = QVBoxLayout(dpad_group)
        self._dpad_label = QLabel("●  中心")
        self._dpad_label.setFont(QFont("Sans", 15, QFont.Weight.Bold))
        self._dpad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dpad_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        dpad_layout.addWidget(self._dpad_label)
        bottom.addWidget(dpad_group)

        hint_group = QGroupBox("操作")
        hint_group.setFont(QFont("Sans", 10))
        hint_group.setStyleSheet(self._group_style())
        hint_layout = QVBoxLayout(hint_group)
        if self._mock:
            hints = [
                "WASD → 左摇杆",
                "IJKL → 右摇杆",
                "Space → A  Shift → B",
                "E → X  R → Y",
                "Q → LB  U → RB",
                "1 → LT  2 → RT",
                "Tab → SELECT  Enter → START",
                "方向键 → 十字键",
            ]
        else:
            hints = [
                "SELECT 短按 → 切换模式",
                "左摇杆 → 移动光标",
                "右摇杆 → 滚轮",
                "A → 左键  B → 右键",
                "鼠标模式: 全键鼠操作",
                "Vibe模式: 快捷键映射",
            ]
        for h in hints:
            lbl = QLabel(h)
            lbl.setFont(QFont("Sans", 10))
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
            hint_layout.addWidget(lbl)
        bottom.addWidget(hint_group)

        main_layout.addLayout(bottom)

        # ── 鼠标设置 ──
        mouse_group = QGroupBox("鼠标设置")
        mouse_group.setFont(QFont("Sans", 10))
        mouse_group.setStyleSheet(self._group_style())
        mouse_layout = QVBoxLayout(mouse_group)

        sens_layout = QHBoxLayout()
        sens_label = QLabel("光标移速")
        sens_label.setFont(QFont("Sans", 10))
        sens_label.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        sens_layout.addWidget(sens_label)

        self._sens_slider = QSlider(Qt.Orientation.Horizontal)
        self._sens_slider.setRange(1, 50)  # 0.1 ~ 5.0
        raw_sens = getattr(self._engine.mouse, 'sensitivity', 1.0)
        self._sens_slider.setValue(int(raw_sens * 10))
        self._sens_slider.valueChanged.connect(self._on_sensitivity_changed)
        self._sens_slider.setStyleSheet(self._slider_style())
        sens_layout.addWidget(self._sens_slider, 1)

        self._sens_value_label = QLabel(f"{raw_sens:.1f}x")
        self._sens_value_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._sens_value_label.setStyleSheet(f"color: {ACCENT.name()};")
        self._sens_value_label.setFixedWidth(45)
        self._sens_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        sens_layout.addWidget(self._sens_value_label)
        mouse_layout.addLayout(sens_layout)

        boost_layout = QHBoxLayout()
        boost_label = QLabel("加速倍率")
        boost_label.setFont(QFont("Sans", 10))
        boost_label.setStyleSheet(f"color: {TEXT_PRIMARY.name()};")
        boost_layout.addWidget(boost_label)

        self._boost_slider = QSlider(Qt.Orientation.Horizontal)
        self._boost_slider.setRange(10, 50)  # 1.0 ~ 5.0
        raw_boost = getattr(self._engine.mouse, 'speed_boost', 2.0)
        self._boost_slider.setValue(int(raw_boost * 10))
        self._boost_slider.valueChanged.connect(self._on_boost_changed)
        self._boost_slider.setStyleSheet(self._slider_style())
        boost_layout.addWidget(self._boost_slider, 1)

        self._boost_value_label = QLabel(f"{raw_boost:.1f}x")
        self._boost_value_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._boost_value_label.setStyleSheet(f"color: {ACCENT.name()};")
        self._boost_value_label.setFixedWidth(45)
        self._boost_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        boost_layout.addWidget(self._boost_value_label)
        mouse_layout.addLayout(boost_layout)

        main_layout.addWidget(mouse_group)

        # 模式切换日志
        log_group = QGroupBox("模式切换日志")
        log_group.setFont(QFont("Sans", 9))
        log_group.setStyleSheet(self._group_style())
        log_layout = QVBoxLayout(log_group)
        self._log_label = QLabel("等待手柄连接...")
        self._log_label.setFont(QFont("Sans", 9))
        self._log_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        log_layout.addWidget(self._log_label)
        main_layout.addWidget(log_group)

    def _group_style(self) -> str:
        return (
            f"QGroupBox {{ color: {TEXT_PRIMARY.name()}; border: 1px solid {BORDER.name()}; "
            "border-radius: 8px; padding: 14px 8px 8px 8px; margin-top: 10px; }"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}"
        )

    def _slider_style(self) -> str:
        return (
            f"QSlider::groove:horizontal {{ background: {BG_PANEL.name()}; height: 6px; "
            "border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{ background: {ACCENT.name()}; width: 14px; "
            "height: 14px; margin: -5px 0; border-radius: 7px; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT.name()}; border-radius: 3px; }}"
        )

    def _on_sensitivity_changed(self, value: int):
        sens = value / 10.0
        self._engine.mouse.sensitivity = sens
        self._config.global_.mouse_sensitivity = sens
        self._sens_value_label.setText(f"{sens:.1f}x")
        save_config(self._config, self._config_path)

    def _on_boost_changed(self, value: int):
        boost = value / 10.0
        self._engine.mouse.speed_boost = boost
        self._config.global_.mouse_speed_boost = boost
        self._boost_value_label.setText(f"{boost:.1f}x")
        save_config(self._config, self._config_path)

    def _on_find_controller(self):
        """查找手柄按钮回调 — 强制重新扫描。"""
        self._log_fn("正在查找手柄...")
        self._connection_label.setText("扫描中...")
        self._connection_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()}; font-weight: bold;")
        # 枚举所有HID设备（调试）
        enumerate_hid_devices()
        # 如果使用的是物理监听器，调用 reconnect
        if not self._mock and hasattr(self._listener, 'reconnect'):
            self._listener.reconnect()
        # 立即触发一次检测
        controllers = find_controllers()
        if controllers:
            self._connected = True
            self._connection_label.setText(f"已连接: {controllers[0]}")
            self._connection_label.setStyleSheet(f"color: {TRIGGER_FILL.name()}; font-weight: bold;")
            self._log_fn(f"找到手柄: {controllers[0]}")
        else:
            self._connection_label.setText("未找到手柄 — 请检查连接")
            self._connection_label.setStyleSheet(f"color: {ACCENT_PRESSED.name()}; font-weight: bold;")
            self._log_fn("未找到手柄")

    def tick(self, now: float):
        self._frame_count += 1
        if now - self._fps_timer >= 1.0:
            self._fps = self._frame_count
            self._frame_count = 0
            self._fps_timer = now
            self._fps_label.setText(f"FPS: {self._fps}")

        if self._mock:
            self._connected = True
            self._connection_label.setText("键盘模拟手柄 (Mock)")
            self._connection_label.setStyleSheet(f"color: {DPAD_ACTIVE.name()}; font-weight: bold;")
        else:
            if now - getattr(self, '_last_check', 0) > 2.0:
                self._last_check = now
                controllers = find_controllers()
                was_connected = self._connected
                self._connected = len(controllers) > 0

                if self._connected and not was_connected:
                    self._connection_label.setText(f"已连接: {controllers[0]}")
                    self._connection_label.setStyleSheet(f"color: {TRIGGER_FILL.name()}; font-weight: bold;")
                    self._log_fn("手柄已连接")
                elif not self._connected and was_connected:
                    self._connection_label.setText("已断开 — 等待重连...")
                    self._connection_label.setStyleSheet(f"color: {ACCENT_PRESSED.name()}; font-weight: bold;")
                    self._log_fn("手柄已断开")

            # 不 return — 监听器后台线程持续重试，插上手柄后自动识别

        state = self._listener.state

        self._left_stick.set_position(state.left_stick.x, state.left_stick.y)
        self._right_stick.set_position(state.right_stick.x, state.right_stick.y)

        for btn in Button:
            self._button_grid.update_button(btn, state.buttons[btn].pressed)

        self._lt_bar.set_value(state.left_trigger.value, state.left_trigger.pressed)
        self._rt_bar.set_value(state.right_trigger.value, state.right_trigger.pressed)

        dx, dy = state.dpad
        dpad_names = {
            (0, 1): "▲  上", (0, -1): "▼  下",
            (-1, 0): "◀  左", (1, 0): "▶  右",
            (-1, 1): "◤  左上", (1, 1): "◥  右上",
            (-1, -1): "◣  左下", (1, -1): "◢  右下",
            (0, 0): "●  中心",
        }
        dpad_text = dpad_names.get((dx, dy), f"({dx}, {dy})")
        self._dpad_label.setText(dpad_text)
        if (dx, dy) != (0, 0):
            self._dpad_label.setStyleSheet(f"color: {DPAD_ACTIVE.name()}; font-weight: bold;")
        else:
            self._dpad_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()}; font-weight: bold;")

        mode = self._engine.current_mode
        self._mode_label.setText(mode)
        self._mode_label.setStyleSheet(
            f"color: {MODE_COLORS.get(mode, ACCENT).name()}; font-weight: bold;"
        )
        # 子层状态
        layer = getattr(self._engine, '_layer_active', '')
        if layer:
            self._layer_label.setText(f"子层: {layer}")
            self._layer_label.setStyleSheet(
                f"color: {LAYER_COLORS.get(layer, ACCENT).name()}; font-weight: bold;"
            )
        else:
            self._layer_label.setText("")
            self._layer_label.setStyleSheet("")

    def set_log(self, text: str):
        self._log_label.setText(text)


# ─── 按键绑定标签页 ───

class BindingsTab(QWidget):
    """按键绑定编辑器。"""

    def __init__(self, config: AppConfig, config_path: str, parent=None):
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self._current_mode = config.default_mode or "mouse"
        self._current_layer = ""  # 空字符串 = 基础映射

        self.setStyleSheet(f"background: {BG_DARK.name()};")
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()

        mode_lbl = QLabel("编辑模式:")
        mode_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()}; font-size: 13px;")
        toolbar.addWidget(mode_lbl)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(self._config.mode_names)
        self._mode_combo.setCurrentText(self._current_mode)
        self._mode_combo.setStyleSheet(self._combo_style())
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self._mode_combo)

        # 层选择器（只在当前模式有层时显示）
        layer_lbl = QLabel("子层:")
        layer_lbl.setStyleSheet(f"color: {TEXT_PRIMARY.name()}; font-size: 13px;")
        toolbar.addWidget(layer_lbl)

        self._layer_combo = QComboBox()
        self._layer_combo.setStyleSheet(self._combo_style())
        self._layer_combo.currentTextChanged.connect(self._on_layer_changed)
        toolbar.addWidget(self._layer_combo)

        toolbar.addStretch()

        save_btn = QPushButton("💾 保存配置")
        save_btn.setStyleSheet(self._btn_style())
        save_btn.clicked.connect(self._save_config)
        toolbar.addWidget(save_btn)

        layout.addLayout(toolbar)

        # ── 绑定表格 ──
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["手柄输入", "当前绑定", "类型", "操作"])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(3, 70)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"border: 1px solid {BORDER.name()}; border-radius: 6px; gridline-color: {BORDER.name()}; }}"
            f"QTableWidget::item {{ padding: 6px 8px; }}"
            f"QHeaderView::section {{ background: {QColor(40, 40, 45).name()}; "
            f"color: {TEXT_SECONDARY.name()}; border: none; padding: 6px; font-weight: bold; }}"
        )
        self._table.setRowCount(len(CONTROLLER_INPUTS))
        layout.addWidget(self._table, 1)

    def _refresh_table(self):
        mode = self._config.get_mode(self._current_mode)
        if mode is None:
            return
        # 根据是否选中子层选择映射来源
        if self._current_layer:
            layer = mode.get_layer(self._current_layer)
            mappings = layer.mappings if layer else {}
        else:
            mappings = mode.mappings

        # 更新层选择器
        layer_names = ["(基础映射)"] + list(mode.layers.keys())
        current_layer_display = f"({self._current_layer})" if self._current_layer else "(基础映射)"
        self._layer_combo.blockSignals(True)
        self._layer_combo.clear()
        self._layer_combo.addItems(layer_names)
        self._layer_combo.setCurrentText(current_layer_display)
        self._layer_combo.blockSignals(False)

        for row, (input_id, input_display, category) in enumerate(CONTROLLER_INPUTS):
            action = mappings.get(input_id, "")

            # 输入名称
            name_item = QTableWidgetItem(input_display)
            name_item.setToolTip(f"{input_id} ({category})")
            self._table.setItem(row, 0, name_item)

            # 当前绑定
            binding_item = QTableWidgetItem(action if action else "(未设置)")
            if not action:
                binding_item.setForeground(QColor(100, 100, 105))
            self._table.setItem(row, 1, binding_item)

            # 类型
            at, _ = classify_action(action)
            type_names = {
                ActionType.MOUSE: "鼠标", ActionType.KEY: "键盘",
                ActionType.SWITCH: "切换", ActionType.NAVIGATE: "导航",
                ActionType.VOICE: "语音", ActionType.NONE: "无",
            }
            type_item = QTableWidgetItem(type_names.get(at, "?"))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, type_item)

            # 编辑按钮
            edit_btn = QPushButton("编辑")
            edit_btn.setStyleSheet(self._btn_small_style())
            edit_btn.clicked.connect(lambda checked, r=row, iid=input_id, idp=input_display:
                                     self._edit_binding(r, iid, idp))
            self._table.setCellWidget(row, 3, edit_btn)

    def _edit_binding(self, row: int, input_id: str, input_display: str):
        mode = self._config.get_mode(self._current_mode)
        if mode is None:
            return
        if self._current_layer:
            layer = mode.get_layer(self._current_layer)
            current_action = layer.mappings.get(input_id, "") if layer else ""
        else:
            current_action = mode.mappings.get(input_id, "")

        dialog = BindingEditorDialog(
            input_id, input_display, current_action,
            self._config.mode_names, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_action = dialog.get_action_string()
            if self._current_layer:
                layer = mode.get_layer(self._current_layer)
                if layer:
                    if new_action == "null":
                        layer.mappings.pop(input_id, None)
                    else:
                        layer.mappings[input_id] = new_action
            else:
                if new_action == "null":
                    mode.mappings.pop(input_id, None)
                else:
                    mode.mappings[input_id] = new_action
            self._refresh_table()

    def _on_mode_changed(self, mode_name: str):
        self._current_mode = mode_name
        self._current_layer = ""
        self._refresh_table()

    def _on_layer_changed(self, layer_display: str):
        if layer_display.startswith("(") and layer_display.endswith(")"):
            layer_display = layer_display[1:-1]
        if layer_display == "基础映射":
            self._current_layer = ""
        else:
            self._current_layer = layer_display
        self._refresh_table()

    def _save_config(self):
        try:
            save_config(self._config, self._config_path)
            QMessageBox.information(self, "保存成功",
                                    f"配置已保存到 {self._config_path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ── 样式 ──

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"border: 1px solid {BORDER.name()}; border-radius: 4px; padding: 4px 8px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ "
            f"background: {BG_PANEL.name()}; color: {TEXT_PRIMARY.name()}; "
            f"selection-background: {ACCENT.name()}; border: 1px solid {BORDER.name()}; }}"
        )

    def _btn_style(self) -> str:
        return (
            f"QPushButton {{ background: {ACCENT.name()}; color: white; "
            "border: none; border-radius: 6px; padding: 8px 16px; "
            "font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {QColor(60, 140, 240).name()}; }}"
        )

    def _btn_small_style(self) -> str:
        return (
            f"QPushButton {{ background: {BG_PANEL.name()}; color: {ACCENT.name()}; "
            f"border: 1px solid {ACCENT.name()}; border-radius: 4px; "
            "padding: 3px 10px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {ACCENT.name()}; color: white; }}"
        )


# ─── 说明书标签页 ───

class ManualTab(QWidget):
    """使用说明书 — 包含模式对照表和操作指南。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from PyQt6.QtWidgets import QTextBrowser
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {BG_DARK.name()};
                color: {TEXT_PRIMARY.name()};
                border: none;
                font-size: 14px;
                padding: 20px;
            }}
        """)
        browser.setHtml(_MANUAL_HTML)
        layout.addWidget(browser)


_MANUAL_HTML = r"""
<style>
h1 { color: #50a0ff; font-size: 22px; margin-top: 20px; }
h2 { color: #50c878; font-size: 18px; margin-top: 16px; }
h3 { color: #c878ff; font-size: 15px; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; }
th { background: #2a2a35; color: #50a0ff; padding: 8px 12px; text-align: left;
     border: 1px solid #3a3a45; font-size: 13px; }
td { padding: 6px 12px; border: 1px solid #3a3a45; font-size: 13px; }
td.code { font-family: 'Consolas', 'Courier New', monospace; color: #e0c060; }
td.desc { color: #c0c0d0; }
code { background: #2a2a35; padding: 1px 5px; border-radius: 3px;
       color: #e0c060; font-size: 13px; }
.note { background: #1a2a1a; border-left: 3px solid #50c878; padding: 10px 14px;
        margin: 10px 0; color: #90c090; font-size: 13px; }
.warn { background: #2a1a1a; border-left: 3px solid #ff5050; padding: 10px 14px;
        margin: 10px 0; color: #ff9090; font-size: 13px; }
</style>

<h1>手柄控制面板 — 使用说明书</h1>
<p>本项目将游戏手柄映射为鼠标/键盘，支持三大操作层：<b>鼠标模式</b>、<b>Vibe 编码子层</b>、
<b>Vim 焦点导航模式</b>。</p>

<h2>模式切换</h2>
<p>按 <code>SELECT</code> 短按在 <b>mouse</b> ↔ <b>vim</b> 之间切换。
在 mouse 模式下 <b>长按 LB</b> 进入 vibe 编码子层，松开回到基础鼠标。</p>

<h2>1. 鼠标模式 (mouse)</h2>
<p>用左摇杆控制光标移动，右摇杆滚屏。适用于网页浏览、文件操作等日常场景。</p>

<h3>基础层按键</h3>
<table>
<tr><th>手柄按键</th><th>功能</th><th>配置值</th></tr>
<tr><td class="desc">左摇杆</td><td class="desc">移动光标</td><td class="code">mouse_x / mouse_y</td></tr>
<tr><td class="desc">右摇杆</td><td class="desc">滚轮 (上下+水平)</td><td class="code">scroll_x / scroll_y</td></tr>
<tr><td class="desc">A (短按=点击，长按=拖拽)</td><td class="desc">鼠标左键 拖拽/点击</td><td class="code">mouse_drag</td></tr>
<tr><td class="desc">B</td><td class="desc">鼠标右键</td><td class="code">mouse_right</td></tr>
<tr><td class="desc">X</td><td class="desc">空格键 (播放/暂停)</td><td class="code">key.space</td></tr>
<tr><td class="desc">Y</td><td class="desc">F 键 (全屏)</td><td class="code">key.f</td></tr>
<tr><td class="desc">十字键</td><td class="desc">方向键 ↑↓←→</td><td class="code">key.up/down/left/right</td></tr>
<tr><td class="desc">LB (短按</td><td class="desc">Ctrl+Shift+Tab (上一标签页)</td><td class="code">key.ctrl+shift+tab</td></tr>
<tr><td class="desc">RB</td><td class="desc">Ctrl+Tab (下一标签页)</td><td class="code">key.ctrl+tab</td></tr>
<tr><td class="desc">LT</td><td class="desc">减小音量</td><td class="code">key.media_volume_down</td></tr>
<tr><td class="desc">RT (按住)</td><td class="desc">光标加速 3.4×</td><td class="code">mouse_speed_hold</td></tr>
<tr><td class="desc">START</td><td class="desc">M 键 (静音)</td><td class="code">key.m</td></tr>
<tr><td class="desc">SELECT</td><td class="desc">切换到 vim 模式</td><td class="code">switch_mode.vim</td></tr>
<tr><td class="desc">LEFT_STICK 按下</td><td class="desc">语音听写 (Win+H)</td><td class="code">voice_input</td></tr>
<tr><td class="desc">RIGHT_STICK 按下</td><td class="desc">虚拟键盘 (Win+Ctrl+O)</td><td class="code">mouse_open_keyboard</td></tr>
</table>

<div class="note"><b>拖拽说明：</b>A 键短按=左键点击，按住不放=鼠标拖拽（配合左摇杆选中文字/拖放文件）。
松手即为释放左键。</div>

<h3>Vibe 编码子层 (长按 LB)</h3>
<p>在鼠标模式下 <b>长按 LB (~0.4秒)</b> 进入 Vibe 编码层，按键映射临时切换为 IDE/AI 编码
快捷键。松开 LB 回到基础鼠标模式。</p>
<table>
<tr><th>手柄按键</th><th>功能</th><th>配置值</th></tr>
<tr><td class="desc">A</td><td class="desc">Tab (接受 AI 建议)</td><td class="code">key.tab</td></tr>
<tr><td class="desc">B</td><td class="desc">Escape (关闭)</td><td class="code">key.escape</td></tr>
<tr><td class="desc">X</td><td class="desc">Ctrl+Enter (提交给 AI)</td><td class="code">key.ctrl+enter</td></tr>
<tr><td class="desc">Y</td><td class="desc">Ctrl+Shift+Enter (强制提交)</td><td class="code">key.ctrl+shift+enter</td></tr>
<tr><td class="desc">十字键 ↑↓</td><td class="desc">上下移动</td><td class="code">key.up/down</td></tr>
<tr><td class="desc">十字键 ←→</td><td class="desc">Alt+[/] (上/下一条 AI 建议)</td><td class="code">key.alt+[ / key.alt+]</td></tr>
<tr><td class="desc">LB</td><td class="desc">Ctrl+C (复制)</td><td class="code">key.ctrl+c</td></tr>
<tr><td class="desc">RB</td><td class="desc">Ctrl+V (粘贴)</td><td class="code">key.ctrl+v</td></tr>
<tr><td class="desc">LT</td><td class="desc">Ctrl+Z (撤销)</td><td class="code">key.ctrl+z</td></tr>
<tr><td class="desc">RT</td><td class="desc">Ctrl+Shift+Z (重做)</td><td class="code">key.ctrl+shift+z</td></tr>
<tr><td class="desc">START</td><td class="desc">Ctrl+S (保存)</td><td class="code">key.ctrl+s</td></tr>
<tr><td class="desc">LEFT_STICK 按下</td><td class="desc">Ctrl+P (快速打开文件)</td><td class="code">key.ctrl+p</td></tr>
<tr><td class="desc">RIGHT_STICK 按下</td><td class="desc">Ctrl+Shift+P (命令面板)</td><td class="code">key.ctrl+shift+p</td></tr>
</table>

<h2>2. Vim 焦点导航模式 (vim)</h2>
<p>通过 Windows UI Automation API 枚举屏幕上所有可交互元素，蓝色光环标识当前焦点。
用十字键在元素间跳转，A 键点击。类似 Switch/Apple TV 的 UI 导航。</p>

<h3>三级层级</h3>
<table>
<tr><th>层级</th><th>范围</th><th>进入方式</th><th>退出方式</th></tr>
<tr><td class="desc">Level 1 窗口级</td><td class="desc">应用窗口 + 任务栏</td><td class="desc">切换到 vim 模式自动进入</td><td class="desc">—</td></tr>
<tr><td class="desc">Level 2 元素级</td><td class="desc">窗口内可交互元素</td><td class="desc">在窗口上按 A</td><td class="desc">按 B 回到 Level 1</td></tr>
<tr><td class="desc">Level 3 输入级</td><td class="desc">文本编辑状态</td><td class="desc">对输入框/编辑区按 A</td><td class="desc">按 B 回到 Level 2</td></tr>
</table>

<h3>按键映射</h3>
<table>
<tr><th>手柄按键</th><th>功能</th><th>配置值</th></tr>
<tr><td class="desc">十字键</td><td class="desc">方向焦点导航</td><td class="code">nav.up/down/left/right</td></tr>
<tr><td class="desc">A</td><td class="desc">点击/进入下一层</td><td class="code">nav.click</td></tr>
<tr><td class="desc">B</td><td class="desc">返回上一层 / Esc</td><td class="code">nav.escape</td></tr>
<tr><td class="desc">X</td><td class="desc">Tab 键</td><td class="code">nav.tab</td></tr>
<tr><td class="desc">Y</td><td class="desc">右键点击</td><td class="code">nav.right_click</td></tr>
<tr><td class="desc">LB</td><td class="desc">上一标签页 Ctrl+Shift+Tab</td><td class="code">nav.prev_tab</td></tr>
<tr><td class="desc">RB</td><td class="desc">下一标签页 Ctrl+Tab</td><td class="code">nav.next_tab</td></tr>
<tr><td class="desc">LT</td><td class="desc">向上滚动</td><td class="code">nav.scroll_up</td></tr>
<tr><td class="desc">RT (按住)</td><td class="desc">视频倍速播放</td><td class="code">nav.speed_hold</td></tr>
<tr><td class="desc">START</td><td class="desc">Enter 键</td><td class="code">nav.enter</td></tr>
<tr><td class="desc">SELECT</td><td class="desc">切换回 mouse 模式</td><td class="code">switch_mode.mouse</td></tr>
<tr><td class="desc">LEFT_STICK 按下</td><td class="desc">重新扫描 UI 元素</td><td class="code">nav.refresh</td></tr>
<tr><td class="desc">RIGHT_STICK 按下</td><td class="desc">呼出虚拟键盘 osk.exe</td><td class="code">nav.open_keyboard</td></tr>
<tr><td class="desc">右摇杆</td><td class="desc">页面滚轮</td><td class="code">scroll_x / scroll_y</td></tr>
<tr><td class="desc">左摇杆</td><td class="desc">方向导航 (持续推动)</td><td class="code">内置引擎处理</td></tr>
<tr><td class="desc">左摇杆 + LT</td><td class="desc">跳到目标方向最远</td><td class="code">内置引擎处理</td></tr>
</table>

<h3>Level 3 输入级说明</h3>
<p>进入输入级后方向导航被锁定。此时：</p>
<ul>
<li><b>B</b> — 退出输入级，回到元素级</li>
<li><b>START</b> — 切换输入语言 (Win+Space)</li>
<li><b>RIGHT_STICK 按下</b> — 打开 Windows 虚拟键盘</li>
</ul>

<h2>3. 语音输入</h2>
<p>按下左摇杆 <b>LEFT_STICK</b> 触发 <b>Win+H</b>（Windows 内置语音听写），
直接说话即可输入文字到当前光标位置。</p>
<div class="note"><b>提示：</b>Win+H 是 Windows 10/11 自带的离线语音识别，
无需联网，中文英文混合识别。首次使用需在系统设置中开启在线语音识别。</div>

<h2>4. 常见操作指南</h2>
<table>
<tr><th>场景</th><th>模式</th><th>操作</th></tr>
<tr><td class="desc">浏览网页</td><td class="code">mouse</td><td class="desc">左摇杆=光标, A=点击, 右摇杆=滚屏, LT/RT=音量/加速</td></tr>
<tr><td class="desc">选中文字</td><td class="code">mouse</td><td class="desc">左摇杆移光标到起点, 按住A, 左摇杆拖到终点, 松A</td></tr>
<tr><td class="desc">拖放文件</td><td class="code">mouse</td><td class="desc">同理：A按住+移动+松A</td></tr>
<tr><td class="desc">AI 编码</td><td class="code">mouse (长按LB)</td><td class="desc">X=提交, A=接受建议, B=拒绝, ←→=切换建议</td></tr>
<tr><td class="desc">键盘输入文字</td><td class="code">vim</td><td class="desc">导航到输入框 → A 进入 → 按右摇杆呼出 OSK → 用光标点虚拟键盘</td></tr>
<tr><td class="desc">切换标签页</td><td class="code">mouse</td><td class="desc">LB/RB = 上/下一个标签页</td></tr>
<tr><td class="desc">视频全屏</td><td class="code">mouse</td><td class="desc">Y = F 键</td></tr>
</table>
"""


# ─── 主窗口 ───

class MainWindow(QMainWindow):
    """手柄控制面板主窗口。"""

    def __init__(self, config: AppConfig, config_path: str,
                 listener: GamepadListener, engine: ModeEngine, mock: bool = False):
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._listener = listener
        self._engine = engine
        self._mock = mock
        self._mode_log: list[str] = []

        self.setWindowTitle("手柄控制面板 — Controller Panel")
        self.setMinimumSize(780, 640)
        self.setStyleSheet(f"background: {BG_DARK.name()};")

        self._build_ui()

        # 60fps 刷新
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _build_ui(self):
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {BORDER.name()}; background: {BG_DARK.name()}; }}
            QTabBar::tab {{ background: {BG_PANEL.name()}; color: {TEXT_SECONDARY.name()};
                padding: 8px 20px; border: 1px solid {BORDER.name()};
                border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
            QTabBar::tab:selected {{ background: {BG_DARK.name()}; color: {ACCENT.name()};
                font-weight: bold; }}
        """)

        self._dashboard = DashboardTab(
            self._listener, self._engine, self._config, self._config_path,
            self._mock, self._log
        )
        self._bindings = BindingsTab(self._config, self._config_path)
        self._manual = ManualTab()

        self._tabs.addTab(self._dashboard, "📊 仪表盘")
        self._tabs.addTab(self._bindings, "🎮 按键绑定")
        self._tabs.addTab(self._manual, "📖 说明书")

        self.setCentralWidget(self._tabs)

    def _tick(self):
        now = time.monotonic()
        self._dashboard.tick(now)

        # 引擎tick（驱动鼠标移动和滚轮）
        self._engine.tick()

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self._mode_log.append(f"[{timestamp}] {msg}")
        if len(self._mode_log) > 6:
            self._mode_log = self._mode_log[-6:]
        self._dashboard.set_log("\n".join(self._mode_log))


# ─── 入口 ───

def _is_admin() -> bool:
    """检测当前进程是否以管理员权限运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate_to_admin():
    """以管理员权限重启当前脚本。

    使用 ShellExecuteW + runas 谓词触发 UAC 提权。
    提权后原进程退出。
    """
    import ctypes.wintypes
    script = os.path.abspath(sys.argv[0])
    cwd = os.path.abspath(os.getcwd())
    params = " ".join(f'"{a}"' if " " in a else a for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        f'"{script}" {params}', cwd, 1  # SW_SHOWNORMAL
    )
    # ret > 32 表示成功
    if ret > 32:
        sys.exit(0)
    else:
        print(f"[!] 提权失败 (ShellExecuteW 返回 {ret})，继续以普通权限运行")


def main():
    # 管理员权限检测 — OSK 屏幕键盘需要管理员权限才能交互
    if not _is_admin():
        print("=" * 56)
        print("[!] 未以管理员身份运行！")
        print("[!] 屏幕键盘 (OSK) 点击将无法使用。")
        print("[!] 正在尝试提权重启...")
        print("=" * 56)
        _elevate_to_admin()
        # 如果还在这里，说明用户拒绝了 UAC 或提权失败
        print("[!] 已取消提权，OSK 屏幕键盘点击将不可用")

    parser_args = sys.argv[1:]
    config_path = "config.yaml"
    if "--config" in parser_args:
        idx = parser_args.index("--config")
        if idx + 1 < len(parser_args):
            config_path = parser_args[idx + 1]

    if not os.path.exists(config_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(script_dir, "config.yaml")
        if os.path.exists(alt_path):
            config_path = alt_path
        else:
            # PyInstaller one-file 模式：从 _MEIPASS 提取默认配置
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                bundled = os.path.join(meipass, "config.yaml")
                if os.path.exists(bundled):
                    # 复制到 exe 所在目录以便用户编辑
                    import shutil
                    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                    shutil.copy2(bundled, os.path.join(exe_dir, "config.yaml"))
                    config_path = os.path.join(exe_dir, "config.yaml")

    print(f"加载配置: {config_path}")
    config = load_config(config_path)
    print(f"模式: {config.mode_names}")

    listener = GamepadListener(deadzone=config.global_.deadzone)
    engine = ModeEngine(config, listener)

    # 重写引擎的模式切换方法，将print替换为GUI日志
    original_switch = engine._switch_mode

    def gui_switch(target_mode: str):
        if target_mode in config.modes:
            old = engine._current_mode
            original_switch(target_mode)
            window._log(f"模式切换: {old} → {target_mode}")

    engine._switch_mode = gui_switch  # type: ignore

    engine.start()
    listener.start()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    app.setStyleSheet(f"""
        QMainWindow {{ background: {BG_DARK.name()}; }}
        QLabel {{ color: {TEXT_PRIMARY.name()}; }}
        QGroupBox {{ color: {TEXT_PRIMARY.name()}; }}
    """)

    window = MainWindow(config, config_path, listener, engine, mock=_using_mock)
    window.show()

    print(f"控制面板已启动 ({'键盘模拟' if _using_mock else '物理手柄'})")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
