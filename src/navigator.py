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
WM_APP = 0x8000
MSG_SHOW = WM_APP + 1
MSG_HIDE = WM_APP + 2
MSG_QUIT = WM_APP + 3

SW_HIDE = 0
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

BORDER_COLOR = 0x00C8A000  # BGR: A0=160, C8=200 → #00A0C8
BORDER_WIDTH = 3
BORDER_RADIUS = 8

# Win32 API 绑定
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

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
        hwnd = self._hwnd
        if hwnd:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._hwnd = None

    def show_at(self, left: int, top: int, right: int, bottom: int):
        """在指定位置显示高亮边框（线程安全）。"""
        with self._lock:
            self._rect = (left, top, right, bottom)
            self._visible = True
        hwnd = self._hwnd
        if hwnd:
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
            raise RuntimeError("RegisterClassExW failed")

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
        self._ready.set()

        # 消息泵
        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = _user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # 清理
        if hwnd:
            _user32.DestroyWindow(hwnd)
        self._hwnd = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口过程回调。"""
        if msg == WM_PAINT:
            self._on_paint(hwnd)
            return 0

        if msg == WM_DESTROY:
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

        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_show(self, hwnd):
        """处理显示请求。"""
        x, y, _, _ = self._screen_rect
        _user32.SetWindowPos(hwnd, 0, x, y, 0, 0,
                             SWP_NOZORDER | SWP_NOSIZE | SWP_NOACTIVATE)
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        _user32.InvalidateRect(hwnd, None, True)

    def _on_paint(self, hwnd):
        """绘制高亮边框。"""
        with self._lock:
            if not self._visible:
                return
            left, top, right, bottom = self._rect

        sx, sy, _, _ = self._screen_rect
        # 转换为窗口相对坐标
        r_left = left - sx
        r_top = top - sy
        r_right = right - sx
        r_bottom = bottom - sy

        ps = PAINTSTRUCT()
        hdc = _user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            pen = _gdi32.CreatePen(0, BORDER_WIDTH, BORDER_COLOR)  # PS_SOLID=0
            old_pen = _gdi32.SelectObject(hdc, pen)
            old_brush = _gdi32.SelectObject(hdc, _gdi32.GetStockObject(5))  # NULL_BRUSH
            _gdi32.RoundRect(hdc, r_left, r_top, r_right, r_bottom,
                             BORDER_RADIUS, BORDER_RADIUS)
            _gdi32.SelectObject(hdc, old_brush)
            _gdi32.SelectObject(hdc, old_pen)
            _gdi32.DeleteObject(pen)
        finally:
            _user32.EndPaint(hwnd, ctypes.byref(ps))


# ─── Navigator ───

@dataclass
class _ElementInfo:
    """内部元素信息。"""
    control: object      # uiautomation.Control
    rect: tuple[int, int, int, int]
    center: tuple[int, int]


class Navigator:
    """UI 焦点导航引擎。

    通过 Windows UI Automation 枚举可交互元素，
    实现方向性焦点跳转和元素操作。

    Usage:
        nav = Navigator()
        nav.start()          # 启动覆盖层 + 扫描元素
        nav.move_down()      # 焦点移到下方元素
        nav.click()          # 点击当前焦点元素
        nav.stop()           # 停止并清理
    """

    # 可交互的控件类型
    INTERACTABLE_TYPES = {
        "ButtonControl", "ListItemControl", "TreeItemControl",
        "MenuItemControl", "HyperlinkControl", "EditControl",
        "TabItemControl", "CheckBoxControl", "RadioButtonControl",
        "ComboBoxControl", "SliderControl", "SplitButtonControl",
        "ToggleButtonControl", "CalendarControl", "DataItemControl",
        "ThumbControl", "ListControl",
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._overlay = FocusOverlay()
        self._focused: Optional[_ElementInfo] = None
        self._elements: list[_ElementInfo] = []
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def focused_element(self) -> Optional[object]:
        with self._lock:
            if self._focused:
                return self._focused.control
            return None

    # ── 生命周期 ──

    def start(self):
        """启动导航器：创建覆盖层、扫描元素、聚焦第一个。"""
        with self._lock:
            if self._active:
                return
            self._active = True
        self._overlay.start()
        self._refresh_elements()
        if self._elements:
            self._focus_element(self._elements[0])

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
        with self._lock:
            if not self._active or not self._focused:
                return
            current = self._focused

        # 重新扫描（元素树可能已变化）
        self._refresh_elements()

        nearest = self._find_nearest(current, dx, dy)
        if nearest:
            self._focus_element(nearest)

    # ── 元素操作 ──

    def click(self):
        """左键点击当前焦点元素。"""
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.Click()
            except Exception:
                pass

    def right_click(self):
        """右键点击当前焦点元素。"""
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.RightClick()
            except Exception:
                pass

    def double_click(self):
        """双击当前焦点元素。"""
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.DoubleClick()
            except Exception:
                pass

    def enter(self):
        """对焦点元素发送 Enter。"""
        ctrl = self._get_focused_control()
        if ctrl:
            try:
                ctrl.SendKeys("{Enter}")
            except Exception:
                pass

    def escape(self):
        """发送 Escape 键（关闭弹窗/退出焦点）。"""
        try:
            import uiautomation as auto
            auto.SendKeys("{Esc}")
        except Exception:
            pass

    def tab(self):
        """发送 Tab 键（原生焦点顺序回退）。"""
        try:
            import uiautomation as auto
            auto.SendKeys("{Tab}")
        except Exception:
            pass

    def scroll_up(self):
        self._scroll(-1)

    def scroll_down(self):
        self._scroll(1)

    def _scroll(self, direction: int):
        """滚动焦点元素。direction: -1=上, 1=下。"""
        ctrl = self._get_focused_control()
        if not ctrl:
            return
        try:
            if hasattr(ctrl, "WheelVertical"):
                ctrl.WheelVertical(direction)
            else:
                import uiautomation as auto
                rect = ctrl.BoundingRectangle
                cx, cy = rect.xcenter(), rect.ycenter()
                auto.Click(x=cx, y=cy)
                auto.SendKeys("{Wheel}" if direction > 0 else "{Wheel}")
        except Exception:
            pass

    def prev_tab(self):
        """Ctrl+Shift+Tab — 上一个标签页。"""
        try:
            import uiautomation as auto
            auto.SendKeys("{Ctrl}{Shift}{Tab}")
        except Exception:
            pass

    def next_tab(self):
        """Ctrl+Tab — 下一个标签页。"""
        try:
            import uiautomation as auto
            auto.SendKeys("{Ctrl}{Tab}")
        except Exception:
            pass

    def refresh(self):
        """重新扫描元素树（如弹窗打开后）。"""
        self._refresh_elements()
        if self._elements:
            self._focus_element(self._elements[0])

    # ── 内部方法 ──

    def _get_focused_control(self):
        with self._lock:
            if self._focused:
                return self._focused.control
        return None

    def _refresh_elements(self):
        """扫描前台窗口的可交互 UI 元素。"""
        elements: list[_ElementInfo] = []
        try:
            import uiautomation as auto

            # 获取前台窗口
            fg_hwnd = _user32.GetForegroundWindow()
            if not fg_hwnd:
                with self._lock:
                    self._elements = elements
                return

            fg_ctrl = auto.ControlFromHandle(fg_hwnd)
            if not fg_ctrl:
                with self._lock:
                    self._elements = elements
                return

            self._walk_tree(fg_ctrl, elements, depth=0, max_depth=8)
        except Exception:
            pass

        with self._lock:
            self._elements = elements

    def _walk_tree(self, control, elements: list[_ElementInfo], depth: int, max_depth: int):
        """递归遍历 UIA 控件树，收集可交互元素。"""
        if depth > max_depth:
            return

        import uiautomation as auto

        try:
            type_name = control.ControlTypeName
            if type_name in self.INTERACTABLE_TYPES:
                if control.IsEnabled and not control.IsOffscreen:
                    rect = control.BoundingRectangle
                    if rect.width() > 4 and rect.height() > 4:
                        # 检查元素在屏幕范围内
                        sw, sh = self._get_screen_size()
                        if rect.right > 0 and rect.bottom > 0 and \
                           rect.left < sw and rect.top < sh:
                            elements.append(_ElementInfo(
                                control=control,
                                rect=(rect.left, rect.top, rect.right, rect.bottom),
                                center=(rect.xcenter(), rect.ycenter()),
                            ))
        except Exception:
            return  # 跳过无法访问的元素

        try:
            for child in control.GetChildren():
                self._walk_tree(child, elements, depth + 1, max_depth)
        except Exception:
            pass

    def _focus_element(self, elem: _ElementInfo):
        """设置焦点元素并更新覆盖层。"""
        with self._lock:
            self._focused = elem
            left, top, right, bottom = elem.rect
        self._overlay.show_at(left, top, right, bottom)

    def _find_nearest(self, current: _ElementInfo, dx: int, dy: int) -> Optional[_ElementInfo]:
        """在指定方向找最近的候选元素。

        算法：基于 W3C Spatial Navigation + BBC LRUD 启发式。
        1. 过滤：仅保留在目标方向的候选
        2. 计分：主轴向距离 + 正交偏差 × 0.3 - 重叠奖励
        """
        with self._lock:
            candidates = list(self._elements)

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

            if dy < 0:  # 向上
                if tb > ct - 2:
                    continue  # 不在上方
                primary_dist = ct - tb
            elif dy > 0:  # 向下
                if tt < cb + 2:
                    continue  # 不在下方
                primary_dist = tt - cb
            elif dx < 0:  # 向左
                if tr > cl - 2:
                    continue
                primary_dist = cl - tr
            else:  # 向右
                if tl < cr + 2:
                    continue
                primary_dist = tl - cr

            # 正交偏差
            if dy != 0:  # 垂直移动
                perp_dist = abs(tx - cx)
                # 重叠奖励
                overlap = min(cr, tr) - max(cl, tl)
            else:  # 水平移动
                perp_dist = abs(ty - cy)
                overlap = min(cb, tb) - max(ct, tt)

            overlap_bonus = max(0, overlap) * -0.5
            score = primary_dist + perp_dist * 0.3 + overlap_bonus
            scored.append((score, cand))

        if not scored:
            return None

        scored.sort(key=lambda s: s[0])
        return scored[0][1]

    @staticmethod
    def _get_screen_size() -> tuple[int, int]:
        w = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return (w, h)
