"""手柄调试面板 — 图形化实时显示所有手柄输入。

用法:
    python test_gui.py
    python test_gui.py --config my_config.yaml

需要 PyQt6 + 已连接的手柄。
"""

import math
import sys
import time

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QGroupBox,
    QFrame,
    QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QFont,
    QPainterPath,
)

from src.config import load_config, AppConfig
from src.types import Button, GamepadState
from src.engine import ModeEngine

# 自动选择后端：优先真手柄，不可用则键盘模拟
_using_mock = False
try:
    from src.controller import GamepadListener, find_controllers
    ctrls = find_controllers()
    if ctrls:
        print(f"使用物理手柄: {ctrls[0]}")
    else:
        raise RuntimeError("未找到物理手柄")
except Exception:
    from src.controller_mock import GamepadListener, find_controllers
    _using_mock = True
    print("使用键盘模拟手柄 (WASD=左摇杆 IJKL=右摇杆 Space=A Tab=SELECT)")


# ─── 颜色常量 ───

BG_DARK = QColor(30, 30, 30)
BG_PANEL = QColor(45, 45, 50)
BORDER = QColor(70, 70, 75)
TEXT_PRIMARY = QColor(220, 220, 220)
TEXT_SECONDARY = QColor(150, 150, 155)
ACCENT = QColor(80, 160, 255)        # 蓝
ACCENT_PRESSED = QColor(255, 120, 60)  # 橙 (按下)
STICK_CIRCLE = QColor(180, 200, 220)
STICK_DOT = QColor(255, 255, 255)
TRIGGER_FILL = QColor(80, 180, 120)
DPAD_ACTIVE = QColor(255, 200, 60)
MODE_COLORS = {
    "mouse": QColor(80, 160, 255),
    "vibe": QColor(200, 120, 255),
}


# ─── 摇杆控件 ───

class JoystickWidget(QWidget):
    """可视化摇杆：背景十字线 + 可移动的圆点。"""

    def __init__(self, label="", parent=None):
        super().__init__(parent)
        self._label = label
        self._x = 0.0
        self._y = 0.0
        self.setMinimumSize(160, 160)
        self.setMaximumSize(220, 220)

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

        # 背景
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_PANEL)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        # 网格
        pen = QPen(BORDER, 1, Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
        p.drawLine(QPointF(cx, cy - radius), QPointF(cx, cy + radius))
        p.drawEllipse(QPointF(cx, cy), int(radius * 0.5), int(radius * 0.5))
        p.drawEllipse(QPointF(cx, cy), int(radius), int(radius))

        # 外圈
        pen = QPen(BORDER, 2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # 摇杆点
        dot_x = cx + self._x * radius
        dot_y = cy - self._y * radius  # 翻转Y

        # 原点小十字
        p.setPen(QPen(BORDER, 1))
        p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))

        # 拖动点
        dot_r = 10
        p.setPen(QPen(STICK_DOT, 2))
        p.setBrush(STICK_CIRCLE)
        p.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

        # 标签
        p.setPen(TEXT_SECONDARY)
        p.setFont(QFont("Sans", 10))
        p.drawText(QRectF(0, h - 22, w, 20), Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()


# ─── 按钮网格控件 ───

class ButtonGridWidget(QWidget):
    """手柄全部按钮的状态网格。"""

    # 布局：模拟Xbox手柄按键位置
    # 第一行：LB  LT  [空]  RT  RB
    # 第二行：[空]  SELECT  START  [空]
    # 第三行：DPAD   LEFT_STICK  RIGHT_STICK  Y
    # 第四行：                X    B    A
    BUTTON_LAYOUT = [
        # (row, col, button, label)
        (0, 0, Button.LB, "LB"),
        (0, 1, Button.LT, "LT"),
        (0, 3, Button.RT, "RT"),
        (0, 4, Button.RB, "RB"),
        (1, 1, Button.SELECT, "SEL"),
        (1, 2, Button.START, "STA"),
        (2, 0, Button.DPAD_UP, "↑"),
        (2, 1, Button.DPAD_LEFT, "←"),
        (2, 2, Button.DPAD_RIGHT, "→"),
        (2, 3, Button.DPAD_DOWN, "↓"),
        (3, 1, Button.LEFT_STICK, "LS"),
        (3, 2, Button.RIGHT_STICK, "RS"),
        (3, 3, Button.Y, "Y"),
        (4, 2, Button.X, "X"),
        (4, 3, Button.B, "B"),
        (4, 4, Button.A, "A"),
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

        # 背景条
        bar_h = 14
        bar_y = (h - bar_h) // 2 + 6
        bar_w = w - 30

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(50, 50, 55))
        p.drawRoundedRect(QRectF(10, bar_y, bar_w, bar_h), 4, 4)

        # 填充
        fill_w = int(bar_w * self._value)
        if fill_w > 0:
            color = ACCENT_PRESSED if self._active else TRIGGER_FILL
            p.setBrush(color)
            p.drawRoundedRect(QRectF(10, bar_y, fill_w, bar_h), 4, 4)

        # 阈值线
        threshold_x = 10 + int(bar_w * 0.5)
        p.setPen(QPen(QColor(100, 100, 110), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(threshold_x, bar_y - 2), QPointF(threshold_x, bar_y + bar_h + 2))

        # 标签 + 数值
        p.setPen(TEXT_PRIMARY)
        p.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        p.drawText(QRectF(10, 0, bar_w, bar_y), Qt.AlignmentFlag.AlignLeft, self._label)
        p.drawText(QRectF(10, 0, bar_w, bar_y), Qt.AlignmentFlag.AlignRight, f"{self._value:.2f}")

        p.end()


# ─── 主窗口 ───

class DebugWindow(QMainWindow):
    """手柄调试主窗口。"""

    def __init__(self, config: AppConfig, listener: GamepadListener, engine: ModeEngine, mock: bool = False):
        super().__init__()
        self._config = config
        self._listener = listener
        self._engine = engine
        self._mock = mock
        self._connected = False
        self._mode_log: list[str] = []
        self._frame_count = 0
        self._fps_timer = time.monotonic()
        self._fps = 0

        self.setWindowTitle("手柄调试面板 — Controller Debug")
        self.setMinimumSize(700, 600)
        self.setStyleSheet(f"background: {BG_DARK.name()};")

        self._build_ui()

        # 60fps 刷新
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        # ── 顶部状态栏 ──
        top = QHBoxLayout()

        self._connection_label = QLabel("搜索手柄...")
        self._connection_label.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        self._connection_label.setStyleSheet(f"color: {ACCENT_PRESSED.name()};")
        top.addWidget(self._connection_label)

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
        top.addLayout(mode_layout)

        top.addStretch()

        fps = QLabel("FPS: --")
        fps.setFont(QFont("Sans", 11))
        fps.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        top.addWidget(fps)
        self._fps_label = fps

        main_layout.addLayout(top)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER.name()};")
        main_layout.addWidget(sep)

        # ── 中部：摇杆 + 按钮 ──
        middle = QHBoxLayout()
        middle.setSpacing(20)

        # 左摇杆
        self._left_stick = JoystickWidget("左摇杆")
        middle.addWidget(self._left_stick)

        middle.addStretch()

        # 按钮网格
        btn_group = QGroupBox("手柄按钮")
        btn_group.setFont(QFont("Sans", 10))
        btn_group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_PRIMARY.name()}; border: 1px solid {BORDER.name()}; "
            "border-radius: 8px; padding: 14px 8px 8px 8px; margin-top: 10px; }"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}"
        )
        btn_layout = QVBoxLayout(btn_group)
        self._button_grid = ButtonGridWidget()
        btn_layout.addWidget(self._button_grid)
        middle.addWidget(btn_group)

        middle.addStretch()

        # 右摇杆
        self._right_stick = JoystickWidget("右摇杆")
        middle.addWidget(self._right_stick)

        main_layout.addLayout(middle)

        # ── 底部：扳机 + 十字键 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        # 扳机
        trigger_group = QGroupBox("扳机 / 肩键")
        trigger_group.setFont(QFont("Sans", 10))
        trigger_group.setStyleSheet(btn_group.styleSheet())
        trigger_layout = QVBoxLayout(trigger_group)
        self._lt_bar = TriggerBar("LT 左扳机")
        self._rt_bar = TriggerBar("RT 右扳机")
        trigger_layout.addWidget(self._lt_bar)
        trigger_layout.addWidget(self._rt_bar)
        bottom.addWidget(trigger_group)

        # 十字键
        dpad_group = QGroupBox("十字键")
        dpad_group.setFont(QFont("Sans", 10))
        dpad_group.setStyleSheet(btn_group.styleSheet())
        dpad_layout = QVBoxLayout(dpad_group)
        self._dpad_label = QLabel("●  中心")
        self._dpad_label.setFont(QFont("Sans", 15, QFont.Weight.Bold))
        self._dpad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dpad_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        dpad_layout.addWidget(self._dpad_label)
        bottom.addWidget(dpad_group)

        # 操作提示
        hint_group = QGroupBox("操作")
        hint_group.setFont(QFont("Sans", 10))
        hint_group.setStyleSheet(btn_group.styleSheet())
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

        # 模式切换日志
        log_group = QGroupBox("模式切换日志")
        log_group.setFont(QFont("Sans", 9))
        log_group.setStyleSheet(btn_group.styleSheet())
        log_layout = QVBoxLayout(log_group)
        self._log_label = QLabel("等待手柄连接...")
        self._log_label.setFont(QFont("Sans", 9))
        self._log_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        log_layout.addWidget(self._log_label)
        main_layout.addWidget(log_group)

    def _tick(self):
        """每帧刷新。"""
        self._frame_count += 1
        now = time.monotonic()
        if now - self._fps_timer >= 1.0:
            self._fps = self._frame_count
            self._frame_count = 0
            self._fps_timer = now
            self._fps_label.setText(f"FPS: {self._fps}")

        # 连接状态
        if self._mock:
            self._connected = True
            self._connection_label.setText("键盘模拟手柄 (Mock)")
            self._connection_label.setStyleSheet(f"color: {DPAD_ACTIVE.name()}; font-weight: bold;")
        else:
            controllers = find_controllers()
            was_connected = self._connected
            self._connected = len(controllers) > 0

            if self._connected and not was_connected:
                self._connection_label.setText(f"已连接: {controllers[0]}")
                self._connection_label.setStyleSheet(f"color: {TRIGGER_FILL.name()}; font-weight: bold;")
                self._log("手柄已连接")
                self._engine.start()
            elif not self._connected and was_connected:
                self._connection_label.setText("已断开 — 等待重连...")
                self._connection_label.setStyleSheet(f"color: {ACCENT_PRESSED.name()}; font-weight: bold;")
                self._log("手柄已断开")

            if not self._connected:
                return

        state = self._listener.state

        # 摇杆
        self._left_stick.set_position(state.left_stick.x, state.left_stick.y)
        self._right_stick.set_position(state.right_stick.x, state.right_stick.y)

        # 按钮
        for btn in Button:
            self._button_grid.update_button(btn, state.buttons[btn].pressed)

        # 扳机
        self._lt_bar.set_value(state.left_trigger.value, state.left_trigger.pressed)
        self._rt_bar.set_value(state.right_trigger.value, state.right_trigger.pressed)

        # 十字键
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

        # 模式
        mode = self._engine.current_mode
        self._mode_label.setText(mode)
        self._mode_label.setStyleSheet(
            f"color: {MODE_COLORS.get(mode, ACCENT).name()}; font-weight: bold;"
        )

        # 引擎tick（驱动鼠标移动和滚轮）
        self._engine.tick()

    def _log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self._mode_log.append(f"[{timestamp}] {msg}")
        if len(self._mode_log) > 6:
            self._mode_log = self._mode_log[-6:]
        self._log_label.setText("\n".join(self._mode_log))


# ─── 入口 ───

def main():
    parser_args = sys.argv[1:]
    config_path = "config.yaml"
    if "--config" in parser_args:
        idx = parser_args.index("--config")
        if idx + 1 < len(parser_args):
            config_path = parser_args[idx + 1]

    print(f"加载配置: {config_path}")
    config = load_config(config_path)
    print(f"模式: {config.mode_names}")

    listener = GamepadListener(deadzone=config.global_.deadzone)
    engine = ModeEngine(config, listener)

    # 重写引擎的模式切换方法，把print替换为GUI日志
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

    # 全局暗色主题
    app.setStyleSheet(f"""
        QMainWindow {{ background: {BG_DARK.name()}; }}
        QLabel {{ color: {TEXT_PRIMARY.name()}; }}
        QGroupBox {{ color: {TEXT_PRIMARY.name()}; }}
    """)

    window = DebugWindow(config, listener, engine, mock=_using_mock)
    window.show()

    print(f"调试面板已启动 ({'键盘模拟' if _using_mock else '物理手柄'})")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
