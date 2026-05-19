"""浏览器 UIA 适配诊断脚本。请在 B站 页面打开时运行此脚本。"""
import sys
import uiautomation as auto
from collections import deque

print("=== 浏览器 UIA 适配诊断 ===\n")

desktop = auto.GetRootControl()
browser_windows = []

for child in desktop.GetChildren():
    try:
        cls = (getattr(child, "ClassName", "") or "")
        name = (child.Name or "")[:60]
        if ("chrome" in cls.lower() or "edge" in cls.lower() or
            "mozilla" in cls.lower() or "browser" in cls.lower() or
            "msedge" in cls.lower()):
            browser_windows.append((child, cls, name))
    except Exception:
        pass

if not browser_windows:
    print("未找到浏览器窗口。请确保浏览器已打开。")
    sys.exit(1)

for win, cls, name in browser_windows:
    print(f"浏览器: cls={cls}")
    print(f"  标题: {name}")
    print()

    # 检测浏览器类型
    cls_lower = cls.lower()
    if "edge" in cls_lower or "msedge" in cls_lower:
        print("  → 检测为 Edge 浏览器")
    elif "mozilla" in cls_lower or "firefox" in cls_lower:
        print("  → 检测为 Firefox 浏览器")
    else:
        print("  → 检测为 Chrome/Chromium 浏览器")

    # 查找 ContentView
    print("\n--- 搜索 ContentView ---")
    content_view_classes = {"clientview", "browserview", "rootview"}
    q = deque()
    q.append((win, 0))
    found_cv = None
    while q:
        node, depth = q.popleft()
        if depth > 6:
            break
        try:
            node_cls = (getattr(node, "ClassName", "") or "").lower()
            if node_cls in content_view_classes:
                found_cv = node
                print(f"  ✓ 找到: {node.ControlTypeName} cls={getattr(node, 'ClassName', '')} depth={depth}")
                break
        except Exception:
            continue
        try:
            for c in node.GetChildren():
                q.append((c, depth + 1))
        except Exception:
            continue
    if not found_cv:
        print("  ✗ 未找到 ContentView")

    # 查找 DocumentControl
    print("\n--- 搜索 DocumentControl ---")
    q = deque()
    q.append((win, 0))
    found_doc = None
    while q:
        node, depth = q.popleft()
        if depth > 6:
            break
        try:
            if node.ControlTypeName == "DocumentControl":
                found_doc = node
                print(f"  ✓ 找到 DocumentControl depth={depth}")
                break
        except Exception:
            continue
        try:
            for c in node.GetChildren():
                q.append((c, depth + 1))
        except Exception:
            continue
    if not found_doc:
        print("  ✗ 未找到 DocumentControl")

    # 查找 RenderHost
    print("\n--- 搜索 RenderHost ---")
    render_classes = {"chrome_renderwidgethosthwnd", "mozillacontentwindowclass"}
    q = deque()
    q.append((win, 0))
    found_rh = None
    while q:
        node, depth = q.popleft()
        if depth > 5:
            break
        try:
            node_cls = (getattr(node, "ClassName", "") or "").lower()
            if node_cls in render_classes:
                found_rh = node
                print(f"  ✓ 找到: {node.ControlTypeName} cls={getattr(node, 'ClassName', '')} depth={depth}")
                break
        except Exception:
            continue
        try:
            for c in node.GetChildren():
                q.append((c, depth + 1))
        except Exception:
            continue
    if not found_rh:
        print("  ✗ 未找到 RenderHost")

    # 尝试从 ContentView/DocumentControl/RenderHost 扫描
    entry = found_cv or found_doc or found_rh or win
    entry_name = ("ContentView" if entry is found_cv else
                  "DocumentControl" if entry is found_doc else
                  "RenderHost" if entry is found_rh else "窗口根")

    types = {"ButtonControl", "HyperlinkControl", "EditControl", "ListItemControl",
             "ImageControl", "TextControl", "GroupControl", "CustomControl",
             "PaneControl", "TabItemControl", "CheckBoxControl", "RadioButtonControl",
             "ComboBoxControl", "MenuItemControl", "ListControl", "ThumbControl",
             "DataItemControl", "TreeItemControl", "SplitButtonControl", "HeaderControl",
             "DocumentControl", "DataGridControl"}

    print(f"\n--- 从 {entry_name} 扫描元素 (depth=16) ---")
    count = [0]
    type_stats = {}

    def walk(node, d, maxd):
        if d > maxd:
            return
        try:
            tn = node.ControlTypeName
            if tn in types:
                try:
                    if node.IsEnabled:
                        r = node.BoundingRectangle
                        if r.width() > 8 and r.height() > 8:
                            w2, h2 = r.width(), r.height()
                            if w2 < 4000 and h2 < 4000:
                                count[0] += 1
                                type_stats[tn] = type_stats.get(tn, 0) + 1
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for c in node.GetChildren():
                walk(c, d + 1, maxd)
        except Exception:
            pass

    walk(entry, 0, 16)
    print(f"  共计 {count[0]} 个可交互元素")
    if type_stats:
        print(f"  类型分布: {dict(sorted(type_stats.items(), key=lambda x: -x[1]))}")

    # 判断
    non_pane = sum(c for t, c in type_stats.items() if t != "PaneControl")
    if count[0] < 30 or non_pane < 10:
        print(f"\n  ⚠ 诊断结论: 网页内容不可达 (仅 {count[0]} 元素, {non_pane} 非容器)")
        cls_lower = cls.lower()
        if "edge" not in cls_lower and "msedge" not in cls_lower and "mozilla" not in cls_lower:
            print("  原因: Chrome 默认关闭无障碍接口，UIA 无法访问网页内容")
            print("  解决方案:")
            print("    1. 用 Edge 浏览器打开 B站 (Edge 原生支持 UIA)")
            print("    2. 或用管理员运行: chrome --force-renderer-accessibility")
        else:
            print("  原因: 浏览器无障碍可能被禁用")
    else:
        print(f"\n  ✓ 网页内容可访问 ({count[0]} 个元素)")
        # 打印一些示例元素
        hyperlinks = [t for t in type_stats if t == "HyperlinkControl"]
        images = [t for t in type_stats if t == "ImageControl"]
        print(f"  超链接: {type_stats.get('HyperlinkControl', 0)} 个")
        print(f"  图片: {type_stats.get('ImageControl', 0)} 个")
        print(f"  按钮: {type_stats.get('ButtonControl', 0)} 个")
        print(f"  文本: {type_stats.get('TextControl', 0)} 个")

    print()
