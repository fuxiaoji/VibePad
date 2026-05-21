"""UI 焦点导航模块 — Vim 风格屏幕元素导航。

通过 Windows UI Automation API 枚举可交互元素，
配合透明覆盖层高亮当前焦点，实现手柄十字键在
UI 元素间的方向性跳转导航。

Classes:
    FocusOverlay — 透明覆盖层高亮窗口 (Win32 ctypes)
    Navigator — UI 焦点导航引擎 (UIAutomation)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

# ─── Win32 常量 ───

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000

LWA_COLORKEY = 0x00000001
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77

WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_ERASEBKGND = 0x0014
WM_TIMER = 0x0113
WM_APP = 0x8000
MSG_SHOW = WM_APP + 1
MSG_HIDE = WM_APP + 2
MSG_QUIT = WM_APP + 3

TIMER_ANIM = 1
ANIM_DURATION = 0.15  # 150ms 动画时长

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
SW_SHOWNOACTIVATE = 4
SWP_NOZORDER = 0x0004
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010

COLORKEY_R = 1
COLORKEY_G = 2
COLORKEY_B = 3
COLORKEY_COLORREF = COLORKEY_R | (COLORKEY_G << 8) | (COLORKEY_B << 16)

# 蓝色边框 (#50A0FF) — BGR 格式: B=0xFF, G=0xA0, R=0x50
BORDER_COLOR = 0x00FFA050     # BGR: 主边框 亮蓝
GLOW_MID_COLOR = 0x00964630   # BGR: 中间辉光 半透明深蓝
GLOW_OUTER_COLOR = 0x003A1E14 # BGR: 外圈辉光 最暗最宽
BORDER_WIDTH_MAIN = 5
BORDER_WIDTH_MID = 10
BORDER_WIDTH_OUTER = 18
BORDER_RADIUS_MAIN = 10
BORDER_RADIUS_MID = 14
BORDER_RADIUS_OUTER = 20

# Win32 API 绑定
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32
_ole32 = ctypes.windll.ole32
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.wintypes.LONG

# Win32 子窗口枚举回调类型（模块级，避免每次调用重新定义导致 GC 问题）
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,
                                  ctypes.wintypes.HWND,
                                  ctypes.wintypes.LPARAM)


def _ensure_com_initialized():
    """确保当前线程已初始化 COM（STA 模式），UIA 调用必需。

    使用 ctypes 直接调用 ole32.CoInitializeEx，零外部依赖。
    重复调用无害 — COM 会返回 S_FALSE（已初始化）或 RPC_E_CHANGED_MODE。
    """
    # COINIT_APARTMENTTHREADED = 0x2
    hr = _ole32.CoInitializeEx(None, 0x2)
    if hr < 0 and hr != 0x80010106:  # RPC_E_CHANGED_MODE — 忽略，COM 已初始化
        import warnings
        warnings.warn(f"CoInitializeEx failed: 0x{hr & 0xFFFFFFFF:08X}")

# 64位兼容：设置函数签名
_user32.DefWindowProcW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                                    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.wintypes.LPARAM
_user32.GetMessageW.argtypes = [ctypes.wintypes.LPMSG, ctypes.wintypes.HWND,
                                 ctypes.wintypes.UINT, ctypes.wintypes.UINT]
_user32.PostMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                                  ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.BeginPaint.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]
_user32.EndPaint.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]
_user32.InvalidateRect.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p, ctypes.wintypes.BOOL]
_user32.SetTimer.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                              ctypes.wintypes.UINT, ctypes.c_void_p]
_user32.SetTimer.restype = ctypes.wintypes.UINT
_user32.KillTimer.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]
_user32.KillTimer.restype = ctypes.wintypes.BOOL

WNDPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.LPARAM, ctypes.wintypes.HWND,
                             ctypes.wintypes.UINT, ctypes.wintypes.WPARAM,
                             ctypes.wintypes.LPARAM)

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", ctypes.c_void_p),
        ("fErase", ctypes.c_int),
        ("rcPaint", RECT),
        ("fRestore", ctypes.c_int),
        ("fIncUpdate", ctypes.c_int),
        ("rgbReserved", ctypes.c_byte * 32),
    ]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


# ─── FocusOverlay ───

class FocusOverlay:
    """透明覆盖层高亮窗口。

    覆盖整个虚拟屏幕，通过颜色键实现透明和鼠标穿透，
    仅在焦点元素周围绘制高亮边框。

    线程安全：通过 PostMessageW 将更新请求发送到
    覆盖层线程的消息队列。

    Usage:
        overlay = FocusOverlay()
        overlay.start()
        overlay.show_at(100, 200, 400, 350)  # 高亮一个按钮
        overlay.hide()
        overlay.stop()
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._screen_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._rect: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._visible = False
        self._running = False
        self._destroyed = False  # 防止 stop() 后重复 DestroyWindow
        # 动画状态 — 眼动仪式平滑过渡
        self._anim_from: Optional[tuple[int, int, int, int]] = None
        self._anim_to: Optional[tuple[int, int, int, int]] = None
        self._anim_start: float = 0.0

    # ── public API ──

    def start(self):
        """启动覆盖层线程并等待窗口创建完成。"""
        if self._running:
            return
        self._running = True
        self._ready.clear()
        self._thread = threading.Thread(target=self._message_loop, daemon=True, name="overlay")
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self):
        """关闭覆盖层窗口并等待线程退出。"""
        if not self._running:
            return
        self._running = False  # 先设标志，让消息循环退出
        hwnd = self._hwnd
        if hwnd and not self._destroyed:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._hwnd = None

    def show_at(self, left: int, top: int, right: int, bottom: int):
        """在指定位置显示高亮边框，带眼动仪式平滑动画过渡。"""
        target = (left, top, right, bottom)
        with self._lock:
            if self._visible and self._rect != (0, 0, 0, 0) and self._rect != target:
                self._anim_from = self._rect
            else:
                self._anim_from = None  # 首次显示，直接定位
            self._anim_to = target
            self._anim_start = time.perf_counter()
            self._visible = True

        hwnd = self._hwnd
        if hwnd:
            if self._anim_from:
                # 启动 60fps 动画定时器
                _user32.SetTimer(hwnd, TIMER_ANIM, 16, None)
                _user32.PostMessageW(hwnd, MSG_SHOW, 0, 0)
            else:
                with self._lock:
                    self._rect = target
                _user32.PostMessageW(hwnd, MSG_SHOW, 0, 0)

    def hide(self):
        """隐藏高亮边框（线程安全）。"""
        with self._lock:
            self._visible = False
        hwnd = self._hwnd
        if hwnd:
            _user32.PostMessageW(hwnd, MSG_HIDE, 0, 0)

    @property
    def visible(self) -> bool:
        with self._lock:
            return self._visible

    # ── Win32 窗口管理 ──

    def _message_loop(self):
        """覆盖层线程主循环。"""
        hinst = _kernel32.GetModuleHandleW(None)

        # 注册窗口类
        wnd_class = WNDCLASSEXW()
        wnd_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wnd_class.style = 0
        self._wndproc_cb = WNDPROC(self._wnd_proc)  # 保持引用防止 GC
        wnd_class.lpfnWndProc = self._wndproc_cb
        wnd_class.hInstance = hinst
        wnd_class.hCursor = _user32.LoadCursorW(0, 32512)  # IDC_ARROW
        wnd_class.hbrBackground = _gdi32.CreateSolidBrush(COLORKEY_COLORREF)
        class_name = "FocusOverlay_9a52ac"
        wnd_class.lpszClassName = class_name

        atom = _user32.RegisterClassExW(ctypes.byref(wnd_class))
        if not atom:
            err = ctypes.windll.kernel32.GetLastError()
            if err == 1410:  # ERROR_CLASS_ALREADY_EXISTS
                print("[vim] overlay class already registered, reusing")
            else:
                raise RuntimeError(f"RegisterClassExW failed: {err}")

        # 虚拟屏幕尺寸
        x = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        self._screen_rect = (x, y, x + w, y + h)

        # 创建窗口
        ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | \
                   WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        style = WS_POPUP | WS_CLIPCHILDREN | WS_CLIPSIBLINGS

        hwnd = _user32.CreateWindowExW(
            ex_style, class_name, "", style,
            x, y, w, h, 0, 0, hinst, None
        )
        if not hwnd:
            raise RuntimeError("CreateWindowExW failed")

        # 设置颜色键透明
        _user32.SetLayeredWindowAttributes(hwnd, COLORKEY_COLORREF, 0, LWA_COLORKEY)
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        self._hwnd = hwnd
        self._destroyed = False  # 新窗口，重置标志
        self._ready.set()

        # 消息泵
        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = _user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # 清理（仅在 WM_CLOSE 未触发 DestroyWindow 时）
        if hwnd and not self._destroyed:
            _user32.DestroyWindow(hwnd)
        self._hwnd = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口过程回调。"""
        if msg == WM_PAINT:
            self._on_paint(hwnd)
            return 0

        if msg == WM_DESTROY:
            self._destroyed = True
            _user32.PostQuitMessage(0)
            return 0

        if msg == WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0

        if msg == MSG_SHOW:
            self._handle_show(hwnd)
            return 0

        if msg == MSG_HIDE:
            _user32.ShowWindow(hwnd, SW_HIDE)
            return 0

        if msg == WM_TIMER and wparam == TIMER_ANIM:
            self._on_anim_tick(hwnd)
            return 0

        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_show(self, hwnd):
        """处理显示请求。"""
        x, y, _, _ = self._screen_rect
        _user32.SetWindowPos(hwnd, 0, x, y, 0, 0,
                             SWP_NOZORDER | SWP_NOSIZE | SWP_NOACTIVATE)
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        _user32.InvalidateRect(hwnd, None, True)

    def _on_paint(self, hwnd):
        """绘制眼动仪风格辉光聚焦环 — 三层同心圆角矩形。"""
        with self._lock:
            if not self._visible:
                return
            left, top, right, bottom = self._rect

        sx, sy, _, _ = self._screen_rect
        r_left = left - sx
        r_top = top - sy
        r_right = right - sx
        r_bottom = bottom - sy

        ps = PAINTSTRUCT()
        hdc = _user32.BeginPaint(hwnd, ctypes.byref(ps))
        null_brush = _gdi32.GetStockObject(5)  # NULL_BRUSH
        old_brush = _gdi32.SelectObject(hdc, null_brush)
        try:
            # 外圈辉光 — 最宽最暗
            outer_pen = _gdi32.CreatePen(0, BORDER_WIDTH_OUTER, GLOW_OUTER_COLOR)
            prev_pen = _gdi32.SelectObject(hdc, outer_pen)
            _gdi32.RoundRect(hdc,
                r_left - 6, r_top - 6, r_right + 6, r_bottom + 6,
                BORDER_RADIUS_OUTER, BORDER_RADIUS_OUTER)
            _gdi32.SelectObject(hdc, prev_pen)
            _gdi32.DeleteObject(outer_pen)

            # 中圈辉光
            mid_pen = _gdi32.CreatePen(0, BORDER_WIDTH_MID, GLOW_MID_COLOR)
            prev_pen = _gdi32.SelectObject(hdc, mid_pen)
            _gdi32.RoundRect(hdc,
                r_left - 3, r_top - 3, r_right + 3, r_bottom + 3,
                BORDER_RADIUS_MID, BORDER_RADIUS_MID)
            _gdi32.SelectObject(hdc, prev_pen)
            _gdi32.DeleteObject(mid_pen)

            # 主边框 — 最亮最细
            main_pen = _gdi32.CreatePen(0, BORDER_WIDTH_MAIN, BORDER_COLOR)
            prev_pen = _gdi32.SelectObject(hdc, main_pen)
            _gdi32.RoundRect(hdc,
                r_left, r_top, r_right, r_bottom,
                BORDER_RADIUS_MAIN, BORDER_RADIUS_MAIN)
            _gdi32.SelectObject(hdc, prev_pen)
            _gdi32.DeleteObject(main_pen)

            _gdi32.SelectObject(hdc, old_brush)
        finally:
            _user32.EndPaint(hwnd, ctypes.byref(ps))

    def _on_anim_tick(self, hwnd):
        """动画帧更新 — ease-out 三次缓动插值。"""
        elapsed = time.perf_counter() - self._anim_start
        t = min(elapsed / ANIM_DURATION, 1.0)
        t = 1.0 - (1.0 - t) ** 3  # ease-out cubic

        with self._lock:
            if self._anim_from and self._anim_to:
                fx, fy, fr, fb = self._anim_from
                tx, ty, tr, tb = self._anim_to
                self._rect = (
                    int(fx + (tx - fx) * t),
                    int(fy + (ty - fy) * t),
                    int(fr + (tr - fr) * t),
                    int(fb + (tb - fb) * t),
                )

        _user32.InvalidateRect(hwnd, None, True)

        if t >= 1.0:
            with self._lock:
                if self._anim_to:
                    self._rect = self._anim_to
                self._anim_from = None
            _user32.KillTimer(hwnd, TIMER_ANIM)


# ─── Navigator ───

@dataclass
class _ElementInfo:
    """内部元素信息。"""
    control: object      # uiautomation.Control
    rect: tuple[int, int, int, int]
    center: tuple[int, int]


class Navigator:
    """UI 焦点导航引擎 — 三级层级导航。

    Level 1 (窗口级): 在应用窗口 + 任务栏之间跳转
        A → 进入窗口 (Level 2)
        LT+摇杆 → 跳到最远
        RT → 加速移动

    Level 2 (元素级): 在窗口内可交互元素之间跳转
        B → 返回 Level 1
        A → 点击 / 进入 Level 3 (可编辑控件)

    Level 3 (输入级): 输入文字
        B → 返回 Level 2
        START → 切换输入语言 (Win+Space)
        预留手柄打字接口
    """

    LEVEL_WINDOWS = 0
    LEVEL_ELEMENTS = 1
    LEVEL_INPUT = 2

    # 可交互的控件类型
    INTERACTABLE_TYPES = {
        "ButtonControl", "ListItemControl", "TreeItemControl",
        "MenuItemControl", "HyperlinkControl", "EditControl",
        "TabItemControl", "CheckBoxControl", "RadioButtonControl",
        "ComboBoxControl", "SliderControl", "SplitButtonControl",
        "ToggleButtonControl", "CalendarControl", "DataItemControl",
        "ThumbControl", "ListControl", "TextControl",
    }

    # 浏览器网页内容可导航元素
    # 排除 GroupControl(布局容器) 和 ImageControl(图标/缩略图噪声)
    # 它们数量巨大且互相重叠，会导致方向导航混乱
    BROWSER_INTERACTABLE_TYPES = {
        "ButtonControl", "ListItemControl", "TreeItemControl",
        "MenuItemControl", "HyperlinkControl", "EditControl",
        "TabItemControl", "CheckBoxControl", "RadioButtonControl",
        "ComboBoxControl", "SliderControl", "SplitButtonControl",
        "ToggleButtonControl", "CalendarControl", "DataItemControl",
        "ThumbControl", "ListControl",
        "CustomControl",
        "DocumentControl", "DataGridControl", "HeaderControl",
    }

    # 视频网站窗口标题关键词
    VIDEO_KEYWORDS = [
        "bilibili", "哔哩哔哩", "B站",
        "YouTube", "youtube",
        "Netflix", "netflix",
        "Prime Video", "Disney+",
        "Twitch", "twitch",
        "Vimeo", "vimeo",
        "视频", "播放",
    ]

    def __init__(self):
        self._lock = threading.RLock()
        self._overlay = FocusOverlay()
        self._focused: Optional[_ElementInfo] = None
        self._elements: list[_ElementInfo] = []
        self._windows: list[_ElementInfo] = []
        self._active = False
        self._level: int = self.LEVEL_WINDOWS
        self._focused_window_ctrl = None  # 保存 UIA 控件引用（比 hwnd 更可靠）
        self._input_ctrl = None           # Level 3 输入控件引用
        self._video_context = False
        self._speed_active = False
        self._refreshing = False          # 防止并发 _refresh_elements
        self._last_refresh = 0.0          # 防抖：上次刷新时间戳
        self._refresh_debounce_s = 0.3    # 防抖间隔（秒）

    @property
    def active(self) -> bool:
        return self._active

    @property
    def level(self) -> int:
        return self._level

    @property
    def focused_element(self) -> Optional[object]:
        with self._lock:
            if self._focused:
                return self._focused.control
            return None

    # ── 生命周期 ──

    def start(self):
        """启动导航器：Level 1 窗口级扫描。"""
        with self._lock:
            if self._active:
                return
            self._active = True
            self._level = self.LEVEL_WINDOWS
        _ensure_com_initialized()
        self._overlay.start()
        self._refresh_windows()
        if self._windows:
            self._focus_element(self._windows[0])

    def stop(self):
        """停止导航器：隐藏覆盖层、清理元素。"""
        with self._lock:
            if not self._active:
                return
            self._active = False
        self._overlay.stop()
        with self._lock:
            self._focused = None
            self._elements.clear()
            self._windows.clear()

    # ── 层级操作 ──

    def enter_window(self):
        """从窗口级进入元素级（A 键在 Level 1）。"""
        if self._level != self.LEVEL_WINDOWS:
            return
        with self._lock:
            if not self._focused:
                return
            ctrl = self._focused.control
            self._focused_window_ctrl = ctrl

        # 先将目标窗口拉到前台
        self._bring_to_foreground(ctrl)

        self._level = self.LEVEL_ELEMENTS
        self._refresh_elements()
        if self._elements:
            self._focus_element(self._elements[0])
        else:
            # 无元素 — 回退
            self._level = self.LEVEL_WINDOWS
            self._focused_window_ctrl = None
            print("[vim] 进入失败：窗口无可交互元素，已回退")

    def back(self):
        """B 键 — 输入级→元素级, 元素级→窗口级。"""
        if self._level == self.LEVEL_INPUT:
            self._level = self.LEVEL_ELEMENTS
            self._input_ctrl = None
            print("[vim] 返回 Level 2 元素级")
            return
        if self._level != self.LEVEL_ELEMENTS:
            return
        self._level = self.LEVEL_WINDOWS
        self._focused_window_ctrl = None
        self._refresh_windows()
        if self._windows:
            self._focus_element(self._windows[0])

    # ── 方向导航 ──

    def move_up(self):
        self._move_in_direction(0, -1)

    def move_down(self):
        self._move_in_direction(0, 1)

    def move_left(self):
        self._move_in_direction(-1, 0)

    def move_right(self):
        self._move_in_direction(1, 0)

    def _move_in_direction(self, dx: int, dy: int):
        # Level 3 输入模式：方向导航被阻止
        if self._level == self.LEVEL_INPUT:
            return

        # 视频上下文 — 方向键改为媒体控制
        self._video_context = self._detect_video_context()
        if self._video_context:
            self._send_video_dpad(dx, dy)
            return

        with self._lock:
            if not self._active or not self._focused:
                return
            current = self._focused
            # 使用缓存列表，不重新扫描（响应快）
            candidates = (list(self._windows) if self._level == self.LEVEL_WINDOWS
                          else list(self._elements))

        if not candidates:
            return

        nearest = self._find_nearest(current, dx, dy, candidates)
        if nearest:
            self._focus_element(nearest)

    def jump_to_end(self, dx: int, dy: int):
        """LT+摇杆：跳到目标方向最远元素。"""
        if self._level == self.LEVEL_INPUT:
            return
        with self._lock:
            if not self._active or not self._focused:
                return
            current = self._focused
            candidates = (list(self._windows) if self._level == self.LEVEL_WINDOWS
                          else list(self._elements))

        if not candidates:
            return
        farthest = self._find_farthest(current, dx, dy, candidates)
        if farthest:
            self._focus_element(farthest)

    # ── 元素操作 ──

    def click(self):
        """A 键 — 窗口级:进入, 元素级:点击(可编辑→L3), 输入级:点击。"""
        _ensure_com_initialized()
        if self._level == self.LEVEL_WINDOWS:
            self.enter_window()
        elif self._level == self.LEVEL_ELEMENTS:
            ctrl = self._get_focused_control()
            if ctrl:
                self._do_click(ctrl)
                if self._is_editable_control(ctrl):
                    self._level = self.LEVEL_INPUT
                    self._input_ctrl = ctrl
                    print("[vim] ★ 进入 Level 3 输入模式 (START=切换语言, B=退出)")
        else:  # LEVEL_INPUT
            ctrl = self._get_focused_control()
            if ctrl:
                self._do_click(ctrl)

    @staticmethod
    def _do_click(ctrl) -> None:
        """点击 UIA 元素，多重回退策略。"""
        try:
            ctrl.Click()
            return
        except Exception:
            pass
        # 回退 1: InvokePattern（按钮/超链接的标准点击方式）
        try:
            ip = ctrl.GetInvokePattern()
            if ip:
                ip.Invoke()
                return
        except Exception:
            pass
        # 回退 2: 在元素中心模拟点击
        try:
            rect = ctrl.BoundingRectangle
            import uiautomation as auto
            auto.Click(x=rect.xcenter(), y=rect.ycenter())
        except Exception:
            pass

    def right_click(self):
        _ensure_com_initialized()
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.RightClick()
            except Exception:
                pass

    def double_click(self):
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.DoubleClick()
            except Exception:
                pass

    def enter(self):
        """START — 输入级:切换语言, 其他:发送 Enter。"""
        if self._level == self.LEVEL_INPUT:
            self.switch_input()
        else:
            ctrl = self._get_focused_control()
            if ctrl:
                try:
                    ctrl.SendKeys("{Enter}")
                except Exception:
                    pass

    def escape(self):
        """B 键 — 输入级:返回L2, 元素级:返回L1, 窗口级:发送 Esc。"""
        if self._level in (self.LEVEL_INPUT, self.LEVEL_ELEMENTS):
            self.back()
        else:
            try:
                import uiautomation as auto
                auto.SendKeys("{Esc}")
            except Exception:
                pass

    def tab(self):
        try:
            import uiautomation as auto
            auto.SendKeys("{Tab}")
        except Exception:
            pass

    def switch_input(self):
        """切换输入语言 (Win+Space)。"""
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            kb.press(Key.cmd)
            kb.press(Key.space)
            kb.release(Key.space)
            kb.release(Key.cmd)
            print("[vim] Win+Space — 输入语言已切换")
        except Exception:
            pass

    def scroll_up(self):
        self._scroll(-1)

    def scroll_down(self):
        self._scroll(1)

    def _scroll(self, direction: int):
        """离散滚轮（LT/RT 按钮触发）。direction: 1=下, -1=上。"""
        _ensure_com_initialized()
        ctrl = self._get_focused_control()
        if not ctrl:
            return
        try:
            if direction > 0:
                ctrl.WheelDown(wheelTimes=3, waitTime=0)
            else:
                ctrl.WheelUp(wheelTimes=3, waitTime=0)
        except Exception:
            pass

    def prev_tab(self):
        try:
            import uiautomation as auto
            auto.SendKeys("{Ctrl}{Shift}{Tab}")
        except Exception:
            pass

    def next_tab(self):
        try:
            import uiautomation as auto
            auto.SendKeys("{Ctrl}{Tab}")
        except Exception:
            pass

    def refresh(self):
        if self._level == self.LEVEL_WINDOWS:
            self._refresh_windows()
            if self._windows:
                self._focus_element(self._windows[0])
        else:
            self._refresh_elements()
            if self._elements:
                self._focus_element(self._elements[0])

    def task_view(self):
        """打开 Windows 任务视图 (Win+Tab) — 一次性查看所有窗口。"""
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            kb.press(Key.cmd)
            kb.press(Key.tab)
            kb.release(Key.tab)
            kb.release(Key.cmd)
        except Exception:
            pass

    def open_keyboard(self):
        """打开 Windows 系统虚拟键盘 (Win+Ctrl+O)。"""
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            kb.press(Key.cmd)
            kb.press(Key.ctrl)
            kb.press("o")
            kb.release("o")
            kb.release(Key.ctrl)
            kb.release(Key.cmd)
        except Exception:
            pass

    # ── 视频上下文适配 ──

    def _detect_video_context(self) -> bool:
        try:
            import uiautomation as auto
            fg = auto.GetForegroundControl()
            if fg and fg.Name:
                title = fg.Name.lower()
                for kw in self.VIDEO_KEYWORDS:
                    if kw.lower() in title:
                        return True
        except Exception:
            pass
        return False

    def _send_video_dpad(self, dx: int, dy: int):
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            if dy < 0:
                kb.tap(Key.up)
            elif dy > 0:
                kb.tap(Key.down)
            elif dx < 0:
                kb.tap(Key.left)
            elif dx > 0:
                kb.tap(Key.right)
        except Exception:
            pass

    def speed_start(self):
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            for _ in range(3):
                kb.press(Key.shift)
                kb.press('.')
                kb.release('.')
                kb.release(Key.shift)
                time.sleep(0.03)
        except Exception:
            pass

    def speed_end(self):
        try:
            from pynput.keyboard import Key, Controller as KBController
            kb = KBController()
            for _ in range(3):
                kb.press(Key.shift)
                kb.press(',')
                kb.release(',')
                kb.release(Key.shift)
                time.sleep(0.03)
        except Exception:
            pass

    # ── 内部方法 ──

    def _get_focused_control(self):
        with self._lock:
            if self._focused:
                return self._focused.control
        return None

    @staticmethod
    def _bring_to_foreground(ctrl) -> None:
        """将 UIA 控件对应的窗口拉到前台。"""
        try:
            hwnd = ctrl.NativeWindowHandle
            if hwnd:
                # ShowWindow + SetForegroundWindow 双保险
                _user32.ShowWindow(hwnd, SW_RESTORE)
                _user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    @staticmethod
    def _is_editable_control(ctrl) -> bool:
        """检测控件是否为可编辑输入框（决定是否进入 Level 3）。"""
        try:
            if ctrl.ControlTypeName == "EditControl":
                return True
            # 某些可编辑 ComboBox / Document 支持 ValuePattern
            if hasattr(ctrl, "GetValuePattern"):
                try:
                    vp = ctrl.GetValuePattern()
                    if vp and not getattr(vp, "IsReadOnly", True):
                        return True
                except Exception:
                    pass
            # 检查是否支持 TextPattern（富文本编辑）
            if hasattr(ctrl, "GetTextPattern"):
                try:
                    ctrl.GetTextPattern()
                    return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    @staticmethod
    def _is_browser_window(ctrl) -> bool:
        """检测是否为浏览器窗口（Chrome / Edge / Firefox）。"""
        try:
            name = (ctrl.Name or "").lower()
            cls = (getattr(ctrl, "ClassName", "") or "").lower()
            browser_markers = [
                "chrome", "chromium", "mozilla", "firefox",
                "edge", "msedge", "browser", "opera", "brave",
            ]
            for marker in browser_markers:
                if marker in name or marker in cls:
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _find_document_control(ctrl) -> object | None:
        """递归 BFS 搜索浏览器网页 DocumentControl（DOM 根节点），最多 24 层。"""
        from collections import deque
        visited = set()
        queue = deque()
        queue.append((ctrl, 0))
        while queue:
            node, depth = queue.popleft()
            if depth > 24:
                continue
            try:
                r = node.BoundingRectangle
                cls = (getattr(node, "ClassName", "") or "").lower()
                if r.width() == 0 and r.height() == 0:
                    node_id = id(node)
                else:
                    node_id = (r.left, r.top, r.right, r.bottom, node.ControlTypeName, cls)
            except Exception:
                node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)
            try:
                if node.ControlTypeName == "DocumentControl":
                    return node
            except Exception:
                continue
            try:
                for child in node.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
        return None

    @staticmethod
    def _find_render_host(ctrl) -> object | None:
        """查找浏览器渲染宿主控件（Chrome/Edge 的渲染进程容器）。

        在 Chromium 浏览器中，是 ClassName=Chrome_RenderWidgetHostHWND 的 PaneControl。
        Firefox 使用 MozillaContentWindowClass。
        """
        from collections import deque
        render_host_classes = {
            "chrome_renderwidgethosthwnd",
            "chromerenderwidgethosthwnd",
            "mozillacontentwindowclass",
            "mozillawindowclass",
        }
        visited = set()
        queue = deque()
        queue.append((ctrl, 0))
        while queue:
            node, depth = queue.popleft()
            if depth > 8:
                continue
            try:
                r = node.BoundingRectangle
                cls_name = (getattr(node, "ClassName", "") or "").lower()
                if r.width() == 0 and r.height() == 0:
                    node_id = id(node)
                else:
                    node_id = (r.left, r.top, r.right, r.bottom, node.ControlTypeName, cls_name)
            except Exception:
                node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)
            try:
                if cls_name in render_host_classes:
                    return node
            except Exception:
                pass
            try:
                for child in node.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
        return None

    @staticmethod
    def _find_render_hosts_win32(ctrl) -> list:
        """通过 Win32 子窗口枚举查找 Chrome_RenderWidgetHostHWND 控件。

        Chromium 浏览器把 web 内容渲染在独立的子 HWND 中，
        这些 HWND 是 Chrome_WidgetWin_1 的 Win32 子窗口，
        但不出现在 Chrome_WidgetWin_1 的 UIA 树中。
        需要直接通过 HWND 获取其 UIA 元素。

        Returns:
            UIA 控件列表（可能有多个，如侧边栏 webview + 主内容）
        """
        import ctypes.wintypes
        import uiautomation as auto

        try:
            hwnd = ctrl.NativeWindowHandle
        except Exception:
            return []

        if not hwnd:
            return []

        children_hwnds = []

        def enum_child(h, _):
            children_hwnds.append(h)
            return True

        try:
            _callback = WNDENUMPROC(enum_child)  # 保持引用防止 GC
            _user32.EnumChildWindows(hwnd, _callback, 0)
        except Exception:
            return []

        buffer = ctypes.create_unicode_buffer(256)
        results = []
        for child_hwnd in children_hwnds:
            try:
                _user32.GetClassNameW(child_hwnd, buffer, 256)
                cls_name = buffer.value.lower()
                if cls_name == "chrome_renderwidgethosthwnd":
                    try:
                        uia_ctrl = auto.ControlFromHandle(child_hwnd)
                        if uia_ctrl is not None:
                            r = uia_ctrl.BoundingRectangle
                            if r.width() > 50 and r.height() > 50:
                                results.append(uia_ctrl)
                    except Exception:
                        pass
            except Exception:
                pass

        return results

    @staticmethod
    def _find_content_view(ctrl) -> object | None:
        """查找浏览器内容容器（ClientView / BrowserView）。

        Edge: BrowserView 是主内容区域（包含标签栏+地址栏+网页内容）。
        Chrome: ClientView 是主内容区域。
        """
        from collections import deque
        content_view_classes = {"clientview", "browserview", "rootview"}
        visited = set()
        queue = deque()
        queue.append((ctrl, 0))
        while queue:
            node, depth = queue.popleft()
            if depth > 8:
                continue
            try:
                r = node.BoundingRectangle
                cls = (getattr(node, "ClassName", "") or "").lower()
                if r.width() == 0 and r.height() == 0:
                    node_id = id(node)
                else:
                    node_id = (r.left, r.top, r.right, r.bottom, node.ControlTypeName, cls)
            except Exception:
                node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)
            try:
                if cls in content_view_classes:
                    print(f"[vim] [+] _find_content_view: {node.ControlTypeName} "
                          f"cls={cls} depth={depth}")
                    return node
            except Exception:
                pass
            try:
                for child in node.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
        print("[vim] _find_content_view: 未找到 (max_depth=8)")
        return None

    @staticmethod
    def _dump_tree_structure(ctrl, max_depth: int = 4, prefix: str = ""):
        """诊断：打印 UIA 树结构（前几层），用于排查浏览器适配问题。"""
        if max_depth <= 0:
            return
        try:
            type_name = ctrl.ControlTypeName
            name = (ctrl.Name or "")[:30]
            cls_name = (getattr(ctrl, "ClassName", "") or "")[:30]
            rect = ctrl.BoundingRectangle
            children_count = 0
            try:
                children_count = len(ctrl.GetChildren())
            except Exception:
                pass
            print(f"{prefix}[L{max_depth}] {type_name} cls={cls_name} "
                  f"name=\"{name}\" rect={rect.width():.0f}x{rect.height():.0f} "
                  f"children={children_count} enabled={ctrl.IsEnabled}")
        except Exception as e:
            print(f"{prefix}? error: {e}")
            return

        try:
            for child in ctrl.GetChildren():
                Navigator._dump_tree_structure(child, max_depth - 1, prefix + "  ")
        except Exception:
            pass

    def _refresh_windows(self):
        """扫描所有顶层窗口 + 任务栏（Level 1）。"""
        _ensure_com_initialized()
        windows: list[_ElementInfo] = []
        try:
            import uiautomation as auto
            desktop = auto.GetRootControl()
            if not desktop:
                return
            for child in desktop.GetChildren():
                try:
                    if child.ControlTypeName != "WindowControl":
                        continue
                    name = (child.Name or "").strip()
                    if not name or name in ("Program Manager",):
                        continue
                    rect = child.BoundingRectangle
                    w, h = rect.width(), rect.height()
                    if w < 100 or h < 50:
                        continue
                    if not child.IsEnabled:
                        continue
                    if child.IsOffscreen:
                        continue
                    windows.append(_ElementInfo(
                        control=child,
                        rect=(rect.left, rect.top, rect.right, rect.bottom),
                        center=(rect.xcenter(), rect.ycenter()),
                    ))
                except Exception:
                    continue

            # 任务栏 — 多方法检测
            taskbar_found = False
            taskbar = None
            try:
                taskbar = auto.ControlFromClassName("Shell_TrayWnd")
            except Exception:
                pass
            if taskbar is None:
                try:
                    taskbar = auto.ControlFromClassName("MSTaskSwWClass")
                except Exception:
                    pass
            if taskbar:
                try:
                    rect = taskbar.BoundingRectangle
                    if rect.width() > 0 and rect.height() > 0:
                        windows.append(_ElementInfo(
                            control=taskbar,
                            rect=(rect.left, rect.top, rect.right, rect.bottom),
                            center=(rect.xcenter(), rect.ycenter()),
                        ))
                        taskbar_found = True
                except Exception:
                    pass

            # 回退：从桌面枚举中查找任务栏
            if not taskbar_found:
                for child in desktop.GetChildren():
                    try:
                        if child.ControlTypeName == "PaneControl":
                            name = (child.Name or "").lower()
                            cls = getattr(child, "ClassName", "") or ""
                            if "task" in name or "tray" in cls.lower() or "mstask" in cls.lower():
                                rect = child.BoundingRectangle
                                if rect.width() > 0 and rect.height() > 0:
                                    windows.append(_ElementInfo(
                                        control=child,
                                        rect=(rect.left, rect.top, rect.right, rect.bottom),
                                        center=(rect.xcenter(), rect.ycenter()),
                                    ))
                                    break
                    except Exception:
                        continue

            print(f"[vim] _refresh_windows: {len(windows)} 个窗口 + 任务栏{'OK' if taskbar_found else '[!]'}")
            for w in windows:
                try:
                    name = (w.control.Name or "")[:50]
                    r = w.rect
                    print(f"  [{r[2]-r[0]}x{r[3]-r[1]}] {name}")
                except Exception:
                    pass
        except Exception:
            pass

        with self._lock:
            self._windows = windows

    def _refresh_elements(self):
        """扫描可交互 UI 元素（Level 2，限定窗口内）。

        浏览器窗口特殊处理：
        1. 找 ContentView (BrowserView/ClientView)
        2. 在 ContentView 内找 DocumentControl（DOM 根）— 最佳扫描起点
        3. 从 DOM 根扫描网页元素（超深遍历，覆盖复杂 DOM 树）
        4. 同时扫描浏览器外壳元素（标签栏/地址栏/按钮）
        """
        # 线程安全：防止并发扫描 + 防抖
        with self._lock:
            if self._refreshing:
                return
            now = time.monotonic()
            if now - self._last_refresh < self._refresh_debounce_s:
                return
            self._refreshing = True
            self._last_refresh = now

        _ensure_com_initialized()
        elements: list[_ElementInfo] = []
        try:
            with self._lock:
                ctrl = self._focused_window_ctrl

            if ctrl is None:
                with self._lock:
                    self._elements = elements
                return

            is_browser = self._is_browser_window(ctrl)
            win_name = (ctrl.Name or "")[:50]
            win_cls = getattr(ctrl, "ClassName", "") or ""
            print(f"[vim] _refresh_elements 窗口=\"{win_name}\" cls={win_cls} browser={is_browser}")

            if is_browser:
                types = self.BROWSER_INTERACTABLE_TYPES
                has_web_content = False

                # 路径 1：找 ContentView (Edge BrowserView / Chrome ClientView)
                content_view = self._find_content_view(ctrl)
                if content_view is not None:
                    cv_cls = getattr(content_view, "ClassName", "") or ""
                    cv_rect = content_view.BoundingRectangle
                    print(f"[vim] [+] ContentView cls={cv_cls} "
                          f"size={cv_rect.width():.0f}x{cv_rect.height():.0f}")

                    # 1a: 在 ContentView 内找 DocumentControl（DOM 根，最可靠）
                    doc = self._find_document_control(content_view)
                    if doc is not None:
                        doc_rect = doc.BoundingRectangle
                        print(f"[vim] [+] 在 ContentView 内找到 DocumentControl "
                              f"size={doc_rect.width():.0f}x{doc_rect.height():.0f}")
                        self._walk_tree(doc, elements, depth=0, max_depth=24,
                                        types=types, off_screen_ok=True)
                        has_web_content = True

                    # 1b: 同时从 ContentView 扫描（覆盖非 DOM 内容 + 嵌套元素）
                    self._walk_tree(content_view, elements, depth=0, max_depth=16,
                                    types=types, off_screen_ok=True)

                # 路径 2：Win32 子窗口枚举找 Chrome_RenderWidgetHostHWND
                # Chromium 把 web 内容渲染在独立的子 HWND 中，不在主窗口 UIA 树内
                rwh_ctrls = self._find_render_hosts_win32(ctrl)
                if rwh_ctrls:
                    print(f"[vim] [+] RenderHost (Win32): {len(rwh_ctrls)} 个")
                    active_count = 0
                    for rwh in rwh_ctrls:
                        rwh_cls = getattr(rwh, "ClassName", "") or ""
                        rwh_rect = rwh.BoundingRectangle
                        # 过滤不可见/退化尺寸的 RWH（非活跃标签页）
                        if rwh_rect.width() < 50 or rwh_rect.height() < 50:
                            continue
                        print(f"[vim]   RWH cls={rwh_cls} "
                              f"size={rwh_rect.width():.0f}x{rwh_rect.height():.0f}")
                        # 先尝试从 RWH 内找 DocumentControl
                        rwh_doc = self._find_document_control(rwh)
                        if rwh_doc is not None:
                            doc_rect = rwh_doc.BoundingRectangle
                            if doc_rect.width() > 50 and doc_rect.height() > 50:
                                print(f"[vim]   RWH 内 DocumentControl "
                                      f"size={doc_rect.width():.0f}x{doc_rect.height():.0f}")
                                self._walk_tree(rwh_doc, elements, depth=0, max_depth=24,
                                                types=types, off_screen_ok=True)
                                has_web_content = True
                                active_count += 1
                            else:
                                print(f"[vim]   RWH DocumentControl 退化"
                                      f" ({doc_rect.width():.0f}x{doc_rect.height():.0f}),"
                                      f" 跳过 (非活跃标签页)")
                        else:
                            # 直接遍历 RWH 子树
                            self._walk_tree(rwh, elements, depth=0, max_depth=24,
                                            types=types, off_screen_ok=True)
                            active_count += 1
                    if active_count > 0:
                        has_web_content = True

                # 路径 3 (fallback)：从窗口根 UIA 树找 RenderHost
                if not has_web_content:
                    host = self._find_render_host(ctrl)
                    if host is not None:
                        cls_h = getattr(host, "ClassName", "") or ""
                        print(f"[vim] [+] RenderHost (UIA) cls={cls_h}")
                        self._walk_tree(host, elements, depth=0, max_depth=24,
                                        types=types, off_screen_ok=True)
                        has_web_content = True

                # 路径 4 (fallback)：从窗口根找 DocumentControl
                if not has_web_content:
                    doc = self._find_document_control(ctrl)
                    if doc is not None:
                        print("[vim] [+] DocumentControl (窗口根)")
                        self._walk_tree(doc, elements, depth=0, max_depth=24,
                                        types=types, off_screen_ok=True)
                        has_web_content = True

                # 同时扫描浏览器外壳元素（标签栏/地址栏/按钮）
                self._walk_tree(ctrl, elements, depth=0, max_depth=5,
                                types=self.INTERACTABLE_TYPES)

                if not has_web_content:
                    print("[vim] [!] 未找到任何内容容器，dump 窗口树结构：")
                    self._dump_tree_structure(ctrl, max_depth=6)
                    # 最后尝试：从窗口根深度扫描
                    self._walk_tree(ctrl, elements, depth=0, max_depth=12,
                                    types=types, off_screen_ok=True)
            else:
                self._walk_tree(ctrl, elements, depth=0, max_depth=8,
                                types=self.INTERACTABLE_TYPES)

            # 去重
            seen = set()
            unique = []
            for e in elements:
                try:
                    rid = e.control.BoundingRectangle
                    key = (rid.left, rid.top, rid.right, rid.bottom,
                           getattr(e.control, "Name", ""))
                except Exception:
                    key = id(e.control)
                if key not in seen:
                    seen.add(key)
                    unique.append(e)
            elements = unique

            # 排序：网页内容优先（中下部大面积元素），chrome 按钮靠后
            # 策略：按 Y 坐标中位数分区，底部 60% 的元素优先
            if is_browser and len(elements) > 5:
                self._sort_content_first(elements)

            # 类型统计
            type_counts: dict[str, int] = {}
            for e in elements:
                try:
                    t = e.control.ControlTypeName
                    type_counts[t] = type_counts.get(t, 0) + 1
                except Exception:
                    pass
            # Chrome/Chromium 可访问性提示
            if is_browser and has_web_content and len(elements) < 30:
                non_pane = sum(c for t, c in type_counts.items() if t != "PaneControl")
                if non_pane < 10:
                    print("[vim] [WARN] Chrome 未开启无障碍访问 —— 网页内容不可达。")
                    print("[vim]    方案1: 用 Edge 浏览器打开网页 (Edge 原生支持 UIA)")
                    print("[vim]    方案2: Chrome 启动时加 --force-renderer-accessibility 参数")

            print(f"[vim] _refresh_elements: {len(elements)} 个元素 "
                  f"(browser={is_browser}) 类型: {dict(sorted(type_counts.items()))}"
                  if type_counts else
                  f"[vim] _refresh_elements: {len(elements)} 个元素 (browser={is_browser})")
        except Exception as e:
            print(f"[vim] _refresh_elements 异常: {e}")
        finally:
            with self._lock:
                self._refreshing = False

        with self._lock:
            self._elements = elements

    def _walk_tree(self, control, elements: list[_ElementInfo], depth: int, max_depth: int,
                   types: set[str] | None = None, off_screen_ok: bool = False):
        if depth > max_depth:
            return

        if types is None:
            types = self.INTERACTABLE_TYPES

        # 检查当前控件是否可交互
        try:
            type_name = control.ControlTypeName
            if type_name in types:
                if control.IsEnabled and (off_screen_ok or not control.IsOffscreen):
                    rect = control.BoundingRectangle
                    if rect.width() > 30 and rect.height() > 20:
                        sw, sh = self._get_screen_size()
                        if rect.right > 0 and rect.bottom > 0 and \
                           rect.left < sw and rect.top < sh:
                            elements.append(_ElementInfo(
                                control=control,
                                rect=(rect.left, rect.top, rect.right, rect.bottom),
                                center=(rect.xcenter(), rect.ycenter()),
                            ))
        except Exception:
            pass  # 当前控件异常不阻止遍历子节点

        # 遍历子节点
        try:
            for child in control.GetChildren():
                self._walk_tree(child, elements, depth + 1, max_depth, types, off_screen_ok)
        except Exception:
            pass

    def _focus_element(self, elem: _ElementInfo):
        with self._lock:
            self._focused = elem
            left, top, right, bottom = elem.rect
        self._overlay.show_at(left, top, right, bottom)

    def _find_nearest(self, current: _ElementInfo, dx: int, dy: int,
                      candidates: list[_ElementInfo]) -> Optional[_ElementInfo]:
        """在 candidates 中找指定方向最近的元素。"""
        if not candidates:
            return None

        cx, cy = current.center
        cl, ct, cr, cb = current.rect

        scored = []
        for cand in candidates:
            if cand is current:
                continue
            tl, tt, tr, tb = cand.rect
            tx, ty = cand.center

            if dy < 0:          # 向上
                if tb > ct - 2:
                    continue
                primary_dist = ct - tb
            elif dy > 0:        # 向下
                if tt < cb + 2:
                    continue
                primary_dist = tt - cb
            elif dx < 0:        # 向左
                if tr > cl - 2:
                    continue
                primary_dist = cl - tr
            else:               # 向右
                if tl < cr + 2:
                    continue
                primary_dist = tl - cr

            if dy != 0:
                perp_dist = abs(tx - cx)
                overlap = min(cr, tr) - max(cl, tl)
            else:
                perp_dist = abs(ty - cy)
                overlap = min(cb, tb) - max(ct, tt)

            overlap_bonus = max(0, overlap) * -0.5
            score = primary_dist + perp_dist * 0.3 + overlap_bonus
            scored.append((score, cand))

        if not scored:
            return None

        scored.sort(key=lambda s: s[0])
        return scored[0][1]

    def _find_farthest(self, current: _ElementInfo, dx: int, dy: int,
                       candidates: list[_ElementInfo]) -> Optional[_ElementInfo]:
        """在 candidates 中找指定方向最远的元素（LT+摇杆跳转）。"""
        if not candidates:
            return None

        cx, cy = current.center
        cl, ct, cr, cb = current.rect

        best = None
        best_score = -1e9

        for cand in candidates:
            if cand is current:
                continue
            tl, tt, tr, tb = cand.rect
            tx, ty = cand.center

            if dy < 0:          # 向上：候选底部必须在当前顶部之上
                if tb > ct - 2:
                    continue
                primary_dist = ct - tb
            elif dy > 0:        # 向下
                if tt < cb + 2:
                    continue
                primary_dist = tt - cb
            elif dx < 0:        # 向左
                if tr > cl - 2:
                    continue
                primary_dist = cl - tr
            else:               # 向右
                if tl < cr + 2:
                    continue
                primary_dist = tl - cr

            # 正交偏差惩罚（对齐优先，但权重较低）
            if dy != 0:
                perp_dist = abs(tx - cx)
            else:
                perp_dist = abs(ty - cy)

            # 得分：距离越远越好，但不要太偏
            score = primary_dist - perp_dist * 0.4
            if score > best_score:
                best_score = score
                best = cand

        return best

    @staticmethod
    def _sort_content_first(elements: list[_ElementInfo]) -> None:
        """浏览器模式下：网页内容元素优先于 chrome UI 元素。

        启发式：元素中心 Y 在窗口下 60% 区域的优先（网页内容区），
        上 20% 区域（标题栏/工具栏）靠后。
        """
        if not elements:
            return
        all_y = [e.center[1] for e in elements]
        min_y, max_y = min(all_y), max(all_y)
        y_range = max_y - min_y
        if y_range < 50:
            return

        chrome_cutoff = min_y + y_range * 0.25

        def _sort_key(e: _ElementInfo) -> tuple[int, float, float]:
            _, cy = e.center
            _, top, _, _ = e.rect
            is_content = 0 if cy > chrome_cutoff else 1
            return (is_content, top, e.center[0])

        elements.sort(key=_sort_key)

    def scroll_stick(self, dx: float, dy: float, dt: float):
        """摇杆连续滚动（右摇杆控制页面滚动）。

        在 vim 模式下滚动聚焦的 UIA 元素，而非鼠标光标位置。
        dx/dy 已经过引擎层符号矫正：右/下=正, 左/上=负。
        """
        _ensure_com_initialized()
        ctrl = self._get_focused_control()
        if not ctrl:
            return

        if not hasattr(self, '_scroll_accum'):
            self._scroll_accum = [0.0, 0.0]

        scroll_speed = 20.0  # wheel ticks per second at full stick
        self._scroll_accum[0] += dx * dt * scroll_speed
        self._scroll_accum[1] += dy * dt * scroll_speed

        ix = int(self._scroll_accum[0])
        iy = int(self._scroll_accum[1])

        if ix == 0 and iy == 0:
            return

        self._scroll_accum[0] -= ix
        self._scroll_accum[1] -= iy

        try:
            if iy < 0:
                ctrl.WheelDown(wheelTimes=-iy, waitTime=0)
            elif iy > 0:
                ctrl.WheelUp(wheelTimes=iy, waitTime=0)

            if ix != 0:
                # 水平滚动回退：pynput 移动到元素中心 → 水平滚轮 → 移回
                try:
                    from pynput.mouse import Controller as MouseController
                    rect = ctrl.BoundingRectangle
                    cx, cy = rect.xcenter(), rect.ycenter()
                    mouse = MouseController()
                    old_pos = mouse.position
                    mouse.position = (cx, cy)
                    mouse.scroll(ix, 0)
                    mouse.position = old_pos
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def _get_screen_size() -> tuple[int, int]:
        w = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return (w, h)
