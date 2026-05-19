# Vim 模式使用教程

## 概述

Vim 模式是 Controller 项目的核心创新功能，灵感来自 Switch/Apple TV 的 UI 导航逻辑。它通过 Windows UI Automation API 枚举屏幕上所有可交互元素（按钮、链接、输入框、菜单项等），让你用手柄十字键在元素间跳转，用蓝色光圈标识当前焦点。

**适用场景**：窗口环境单一（例如只有浏览器 + VSCode），不想频繁在手柄和鼠标之间切换。

---

## 模式切换

三模式循环，按 **SELECT** 切换：

```
  Mouse（鼠标）  →  Vibe（编码）  →  Vim（导航）
       ↑                                  |
       └──────────── SELECT ──────────────┘
```

仪表盘顶部显示当前模式名称和颜色：
- Mouse：蓝色
- Vibe：橙色
- Vim：绿色

---

## 按键映射

### 十字键 — 焦点导航

| 按键 | 动作 | 说明 |
|------|------|------|
| ↑ | `nav.up` | 焦点移到上方元素 |
| ↓ | `nav.down` | 焦点移到下方元素 |
| ← | `nav.left` | 焦点移到左侧元素 |
| → | `nav.right` | 焦点移到右侧元素 |

导航算法基于 W3C Spatial Navigation 规范：在目标方向找最近的元素，综合考虑主轴向距离、正交偏差和重叠量。

### 面部按钮 — 元素操作

| 按键 | 动作 | 说明 |
|------|------|------|
| A | `nav.click` | 左键点击当前焦点元素 |
| B | `nav.escape` | 发送 Esc — 关闭弹窗/退出焦点 |
| X | `nav.tab` | 发送 Tab — 原生焦点回退 |
| Y | `nav.right_click` | 右键点击当前焦点元素 |

### 肩键 — 标签页

| 按键 | 动作 | 说明 |
|------|------|------|
| LB | `nav.prev_tab` | Ctrl+Shift+Tab 上一个标签页 |
| RB | `nav.next_tab` | Ctrl+Tab 下一个标签页 |

### 扳机

| 按键 | 动作 | 说明 |
|------|------|------|
| LT | `nav.scroll_up` | 向上滚动焦点区域 |
| RT | `nav.speed_hold` | 按住倍速播放（视频上下文）|

### 功能键

| 按键 | 动作 | 说明 |
|------|------|------|
| START | `nav.enter` | 发送 Enter — 确认 |
| SELECT | `switch_mode.mouse` | 切回鼠标模式 |
| 左摇杆按下 | `nav.refresh` | 重新扫描 UI 元素（弹窗打开后刷新）|

---

## 视频上下文感知

当 Vim 模式检测到前台窗口是视频网站时，十字键自动切换为媒体控制：

### 支持的视频平台

B站 (bilibili)、YouTube、Netflix、Prime Video、Disney+、Twitch、Vimeo 等。

检测方式：读取前台窗口标题，匹配关键词列表。

### 视频模式下的十字键

| 按键 | 动作 | 说明 |
|------|------|------|
| ↑ | 音量增大 | 发送 ↑ 键（B站/YouTube 通用）|
| ↓ | 音量减小 | 发送 ↓ 键 |
| ← | 快退 5 秒 | 发送 ← 键 |
| → | 快进 5 秒 | 发送 → 键 |

### 按住 RT — 倍速播放

在视频模式下按住右扳机，自动发送 `>` 键（Shift+.）三次，将播放速度提升至约 2x。松开 RT 时发送 `<` 键（Shift+,）三次，恢复原速。

> B站和 YouTube 的 `>` / `<` 快捷键调节播放速度：
> 1x → 1.25x → 1.5x → 2x

---

## 蓝色光圈（FocusOverlay）

- 透明置顶窗口，鼠标可穿透点击
- 蓝色圆角矩形边框（3px 宽，8px 圆角）
- 通过 Win32 `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST` 实现
- 独立线程运行，通过 `PostMessageW` 跨线程安全更新位置

---

## 常见操作流程

### 浏览网页（B站）

1. SELECT 切换到 Vim 模式
2. 蓝框出现在第一个可交互元素上
3. 十字键移动到视频封面 → A 点击打开
4. 视频全屏后，D-pad 自动切换为媒体控制
5. ↑↓ 调音量，←→ 快进快退
6. 按住 RT 倍速播放，看完松开恢复
7. B 键退出全屏 / 关闭弹窗
8. SELECT 切回鼠标模式继续浏览

### 使用 VSCode

1. SELECT 切换到 Vibe 模式编码（推荐）
2. 或在 Vim 模式下用十字键在文件树/编辑器/终端间导航
3. A 点击聚焦元素，START 发送 Enter 确认
4. LT 滚动代码，LB/RB 切换标签页

### 切换标签页

1. 在 Vim 模式下，LB 上一个标签页，RB 下一个
2. 也可以切到 Mouse 模式用 LB/RB（同样是 Ctrl+Tab）

---

## 配置

Vim 模式的按键映射可在 GUI「按键绑定」标签页中编辑。

视频检测关键词在 `src/navigator.py` 的 `VIDEO_KEYWORDS` 列表中，可以自行添加或修改。

```python
VIDEO_KEYWORDS = [
    "bilibili", "哔哩哔哩", "B站",
    "YouTube", "youtube",
    "Netflix", "netflix",
    ...
]
```

---

## 调试

启动程序后，终端每秒会输出 RT 扳机调试信息：

```
[RT debug] raw=1.000 smoothed=1.000 active=True boost=True mode=mouse
```

- `raw`：RT 原始模拟值（0.0 松开 ~ 1.0 按满）
- `smoothed`：EMA 平滑后的值
- `active`：平滑值 > 0.25 阈值
- `boost`：光标加速/视频倍速是否激活
- `mode`：当前模式

如果 RT 按满但 `raw` 始终为 0.000，说明手柄扳机轴未被正确读取，请检查手柄驱动/连接。
