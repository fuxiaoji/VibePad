"""浏览器 UIA 树诊断脚本 — 快速检查前台浏览器窗口的 UIA 结构。

用法:
    python diagnose_browser_uia.py

输出:
    - 前台窗口信息（进程名、窗口标题、UIA 控件类型）
    - 浏览器 ContentView / DocumentControl / RenderHost 搜索路径
    - 可交互元素数量
"""

import sys
import io
import uiautomation as auto

# 修复 Windows GBK 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    print("=" * 60)
    print("浏览器 UIA 树诊断")
    print("=" * 60)

    # 先枚举所有顶层窗口，找浏览器
    desktop = auto.GetRootControl()
    browser_windows = []
    for child in desktop.GetChildren():
        try:
            name = (child.Name or "").strip()
            cls = (getattr(child, "ClassName", "") or "").lower()
            if not name or name == "Program Manager":
                continue
            is_browser = any(kw in name.lower() or kw in cls for kw in [
                "chrome", "edge", "firefox", "browser", "bilibili",
                "youtube", "msedge", "mozilla", "opera", "brave",
            ])
            if is_browser:
                browser_windows.append(child)
        except Exception:
            pass

    if not browser_windows:
        fg = auto.GetForegroundControl()
        name = (fg.Name if fg else "") or ""
        print(f"\n未检测到浏览器窗口。当前前台: {name}")
        print("请打开 Edge 或 Chrome 浏览器访问 bilibili.com 后重试")
        return

    print(f"\n找到 {len(browser_windows)} 个浏览器窗口:")
    for i, w in enumerate(browser_windows):
        name = w.Name or "(无标题)"
        cls = getattr(w, "ClassName", "") or "(未知)"
        print(f"  [{i}] {name} (cls={cls})")

    # 优先选择前台窗口（如果它是浏览器的话）
    fg = auto.GetForegroundControl()
    fg_name = (fg.Name or "") if fg is not None else ""
    ctrl = browser_windows[0]
    for bw in browser_windows:
        bw_name = bw.Name or ""
        if bw_name and fg_name and (bw_name == fg_name or fg_name in bw_name or bw_name in fg_name):
            ctrl = bw
            break
    name = ctrl.Name or "(无标题)"
    cls = getattr(ctrl, "ClassName", "") or "(未知)"
    ctrl_type = ctrl.ControlTypeName
    print(f"\n诊断目标: {name}")
    print(f"控件类型: {ctrl_type}")
    print(f"窗口类名: {cls}")

    # 检测浏览器类型
    name_lower = name.lower()
    cls_lower = cls.lower()
    is_edge = "edge" in name_lower or "msedge" in cls_lower
    is_chrome = "chrome" in name_lower or "chrome" in cls_lower
    is_firefox = "firefox" in name_lower or "mozilla" in name_lower
    browser_type = "Edge" if is_edge else ("Chrome" if is_chrome else ("Firefox" if is_firefox else "未知"))
    print(f"浏览器类型: {browser_type}")

    # 检查是否匹配视频网站
    video_kw = ["bilibili", "哔哩哔哩", "youtube", "netflix", "twitch"]
    for kw in video_kw:
        if kw.lower() in name.lower():
            print(f"OK 检测到视频网站: {kw}")
            break

    # 扫描 ContentView
    print("\n" + "-" * 40)
    print("搜索 ContentView (ClientView / BrowserView)...")
    content_view = _find_by_class(ctrl, {"clientview", "browserview", "rootview"})
    if content_view:
        print(f"OK 找到: {content_view.ControlTypeName} cls={getattr(content_view, 'ClassName', '')}")
    else:
        print("X 未找到")

    # 扫描 DocumentControl
    print("\n搜索 DocumentControl (DOM 根)...")
    doc = _find_by_type(ctrl, "DocumentControl")
    if doc:
        print(f"OK 找到: name={doc.Name or ''} rect={doc.BoundingRectangle.width():.0f}x{doc.BoundingRectangle.height():.0f}")
    else:
        print("X 未找到")

    # 扫描 RenderHost
    print("\n搜索 RenderHost (Chrome_RenderWidgetHostHWND 等)...")
    host = _find_by_class(ctrl, {
        "chrome_renderwidgethosthwnd", "chromerenderwidgethosthwnd",
        "mozillacontentwindowclass", "mozillawindowclass",
    })
    if host:
        print(f"OK 找到: cls={getattr(host, 'ClassName', '')}")
    else:
        print("X 未找到")

    # 统计可交互元素
    print("\n" + "-" * 40)
    print("统计可交互元素 (深度 16)...")

    elements = []
    _walk_tree(ctrl, elements, depth=0, max_depth=16)

    type_counts = {}
    for e in elements:
        t = e.ControlTypeName
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n共 {len(elements)} 个可交互元素:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {t}: {c}")
    if len(type_counts) > 20:
        print(f"  ... 及其他 {len(type_counts) - 20} 种类型")

    # Chrome 特殊诊断
    if is_chrome and len(elements) < 30:
        non_pane = sum(c for t, c in type_counts.items() if t != "PaneControl")
        print("\n" + "=" * 60)
        print("WARNING: Chrome 可访问性诊断")
        print("=" * 60)
        print(f"非 PaneControl 元素: {non_pane}")
        if non_pane < 10:
            print("\nChrome 未开启无障碍访问 —— 网页内容不可达！")
            print("解决方案:")
            print("  1. 改用 Edge 浏览器 (原生支持 UIA)")
            print("  2. Chrome 启动时添加 --force-renderer-accessibility 参数")
            print("     chrome.exe --force-renderer-accessibility")

    # 打印前 5 个元素
    print("\n" + "-" * 40)
    print("前 5 个元素:")
    for e in elements[:5]:
        r = e.BoundingRectangle
        name = (e.Name or "")[:40]
        print(f"  [{e.ControlTypeName}] {name} "
              f"rect=({r.left},{r.top})-({r.right},{r.bottom}) "
              f"size={r.width():.0f}x{r.height():.0f} "
              f"enabled={e.IsEnabled}")

    # 打印 UIA 树结构（前 3 层）
    print("\n" + "-" * 40)
    print("UIA 树结构 (前 4 层, 最多显示每层前 3 个子节点):")
    _dump_tree(ctrl, max_depth=4, max_children=3)


def _find_by_class(ctrl, class_names: set[str]) -> object | None:
    """BFS 搜索特定 ClassName 的控件。"""
    from collections import deque
    visited = set()
    queue = deque([(ctrl, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth > 8:
            continue
        try:
            r = node.BoundingRectangle
            rid = (r.left, r.top, r.right, r.bottom)
        except Exception:
            rid = id(node)
        if rid in visited:
            continue
        visited.add(rid)
        try:
            cls = (getattr(node, "ClassName", "") or "").lower()
            if cls in class_names:
                return node
        except Exception:
            pass
        try:
            for child in node.GetChildren():
                queue.append((child, depth + 1))
        except Exception:
            pass
    return None


def _find_by_type(ctrl, type_name: str) -> object | None:
    """BFS 搜索特定 ControlTypeName 的控件。"""
    from collections import deque
    visited = set()
    queue = deque([(ctrl, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth > 8:
            continue
        try:
            r = node.BoundingRectangle
            rid = (r.left, r.top, r.right, r.bottom)
        except Exception:
            rid = id(node)
        if rid in visited:
            continue
        visited.add(rid)
        try:
            if node.ControlTypeName == type_name:
                return node
        except Exception:
            pass
        try:
            for child in node.GetChildren():
                queue.append((child, depth + 1))
        except Exception:
            pass
    return None


def _walk_tree(ctrl, elements: list, depth: int, max_depth: int):
    if depth > max_depth:
        return
    types = {
        "ButtonControl", "ListItemControl", "TreeItemControl",
        "MenuItemControl", "HyperlinkControl", "EditControl",
        "TabItemControl", "CheckBoxControl", "RadioButtonControl",
        "ComboBoxControl", "SliderControl", "SplitButtonControl",
        "ToggleButtonControl", "CalendarControl", "DataItemControl",
        "ThumbControl", "ListControl", "TextControl",
        "ImageControl", "GroupControl", "CustomControl",
        "DocumentControl", "DataGridControl", "HeaderControl", "PaneControl",
    }
    try:
        type_name = ctrl.ControlTypeName
        if type_name in types:
            if ctrl.IsEnabled:
                rect = ctrl.BoundingRectangle
                if rect.width() > 4 and rect.height() > 4:
                    elements.append(ctrl)
    except Exception:
        pass
    try:
        for child in ctrl.GetChildren():
            _walk_tree(child, elements, depth + 1, max_depth)
    except Exception:
        pass


def _dump_tree(ctrl, max_depth: int, max_children: int, prefix: str = ""):
    if max_depth <= 0:
        return
    try:
        type_name = ctrl.ControlTypeName
        name = (ctrl.Name or "")[:30]
        cls = (getattr(ctrl, "ClassName", "") or "")[:20]
        rect = ctrl.BoundingRectangle
        children_count = 0
        try:
            children_count = len(ctrl.GetChildren())
        except Exception:
            pass
        print(f"{prefix} [{type_name}] cls={cls} name=\"{name}\" "
              f"size={rect.width():.0f}x{rect.height():.0f} "
              f"children={children_count} enabled={ctrl.IsEnabled}")
    except Exception as e:
        print(f"{prefix}? error: {e}")
        return
    try:
        children = ctrl.GetChildren()
        for child in children[:max_children]:
            _dump_tree(child, max_depth - 1, max_children, prefix + "  ")
        if len(children) > max_children:
            print(f"{prefix}  ... ({len(children) - max_children} more children)")
    except Exception:
        pass


if __name__ == "__main__":
    main()
