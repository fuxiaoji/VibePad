# Controller — 手柄操控电脑 / Vibe Coding 快捷映射

[![Platform](https://img.shields.io/badge/platform-Windows-blue)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

🎮 把手柄变成编程和浏览的高效工具。支持**鼠标模拟**、**Vibe Coding 一键快捷键**（Copilot / Claude Code）、**Vim 风格三级焦点导航**（类似 Switch/Apple TV UI）。左手刷 B站，右手写代码，无需放下手柄。

---

## 为什么用这个？

- **Vibe Coding**：用 AI 写代码时频繁按 Tab / Esc / Ctrl+Enter，手柄比键盘更顺手
- **刷 B站 / YouTube**：摇杆移动光标、滚轮浏览，十字键控制音量和快进快退
- **完全不用键鼠**：Vim 导航模式通过 Windows UI Automation 识别屏幕上所有可交互元素，手柄在窗口和元素间跳转
- **高度可定制**：所有按键映射通过 GUI 或 YAML 配置，适配任何手柄

## 环境要求

- Windows 10/11
- Python 3.10+
- 手柄（Xbox / PS5 DualSense / Switch Pro / 兼容 XInput）

## 快速开始

```bash
pip install -r requirements.txt
python controller_gui.py
```

插上手柄，按 **SELECT** 在三模式间循环切换。

---

## 三种模式

### 鼠标模式（Mouse）— 媒体浏览

通用模式，搞定 B站 / YouTube / 网页浏览。

| 按键 | 动作 |
|------|------|
| 左摇杆 | 移动光标 |
| 右摇杆 | 页面滚动 |
| A | 鼠标左键 |
| B | 鼠标右键 |
| X | 暂停/播放 |
| Y | 全屏 |
| 十字键 | 方向键（音量 / 快进快退） |
| LB / RB | 上/下一个标签页 |
| RT 按住 | 光标加速（倍率可调） |

### Vibe Coding 模式 — AI 编程

VSCode + GitHub Copilot + Claude Code 专用快捷键布局。

| 按键 | 动作 | 场景 |
|------|------|------|
| **A** | `Tab` | 接受 AI 建议 |
| **B** | `Esc` | 拒绝建议 / 关闭面板 |
| **X** | `Ctrl+Enter` | 提交给 AI / 应用差异 |
| **Y** | `Ctrl+Shift+Enter` | 强制提交 |
| 十字键↑↓ | 光标上下 | 代码导航 |
| 十字键←→ | `Alt+[` / `Alt+]` | Copilot 上/下一条建议 |
| LB | `Ctrl+C` | 复制 |
| RB | `Ctrl+V` | 粘贴 |
| LT | `Ctrl+Z` | 撤销 |
| RT | `Ctrl+Shift+Z` | 重做 |
| START | `Ctrl+S` | 保存 |
| 左摇杆按下 | `Ctrl+P` | 快速打开文件 |
| 右摇杆按下 | `Ctrl+Shift+P` | 命令面板 |

### Vim 导航模式 — 纯手柄操作

三级层级导航，手柄完全替代键鼠：

- **Level 1（窗口级）**：光圈在应用窗口 + 任务栏之间跳转，A 进入窗口
- **Level 2（元素级）**：光圈在窗口内可交互元素间跳转，A 点击，B 返回
- **Level 3（输入级）**：点击输入框后进入，START 切换输入法，B 退出
- **视频感知**：检测到 B站/YouTube 时，十字键自动切换为媒体控制，RT 按住二倍速
- **右摇杆**：滚动页面

详见 [VIM_MODE_TUTORIAL.md](VIM_MODE_TUTORIAL.md)

---

## 浏览器适配

| 浏览器 | 网页内容 UIA 访问 | 说明 |
|--------|------------------|------|
| **Edge** | ✅ 原生支持 | 推荐！打开 B站 即可用手柄导航 |
| **Chrome** | ⚠️ 需配置 | 需加 `--force-renderer-accessibility` 启动参数 |
| **Firefox** | ✅ 支持 | 原生支持 UIA |

运行 `python diagnose_browser.py` 可诊断当前浏览器是否支持手柄导航。

---

## GUI 控制面板

- **仪表盘**：实时显示摇杆、扳机、按钮状态 + 鼠标灵敏度和加速倍率滑块
- **按键绑定**：图形化编辑所有按键映射，支持 mouse / key / nav / switch_mode 四种动作类型

---

## 自定义配置

`config.yaml` 是核心配置文件，可直接编辑或通过 GUI 修改：

```yaml
global:
  mouse_sensitivity: 1.0        # 光标灵敏度 (0.1-5.0)
  mouse_speed_boost: 2.0        # RT 按住时光标加速倍率
  deadzone: 0.15                # 摇杆死区

modes:
  mouse:     # 鼠标模式配置
  vibe:      # Vibe Coding 配置
  vim:       # Vim 导航配置
```

---

## 项目结构

```
controller/
├── README.md
├── VIM_MODE_TUTORIAL.md
├── config.yaml
├── controller_gui.py          # GUI 主入口
├── diagnose_browser.py        # 浏览器 UIA 适配诊断
├── requirements.txt
├── src/
│   ├── controller.py          # 手柄读取 (多后端)
│   ├── config.py              # 配置加载/保存
│   ├── engine.py              # 模式引擎 (输入→输出翻译)
│   ├── mouse_sim.py           # 鼠标模拟
│   ├── key_sim.py             # 键盘模拟
│   └── navigator.py           # Vim 焦点导航 (UIA + Win32)
└── tests/
```

## Keywords

`vibecoding` `vibe-coding` `controller` `gamepad` `手柄` `手柄操控电脑` `手柄编程` `gamepad-to-keyboard` `copilot-shortcut` `claude-code` `bilibili` `spatial-navigation` `uiautomation` `win32` `accessibility` `focus-navigation`
