# VibePad — 手柄操控电脑

[![Platform](https://img.shields.io/badge/platform-Windows-blue)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

把手柄变成电脑遥控器。**鼠标模拟**、**Vibe Coding 快捷键**、**Vim 风格焦点导航**——浏览网页、刷 B站、写代码，完全不用碰键鼠。

> ⚠️ **Vim 导航模式为测试版**，目前存在一些 bug，建议优先使用鼠标模式。欢迎提交 [Issues](../../issues) 反馈问题。

<p align="center">
  <img src="screenshots/dashboard.png" width="800" alt="VibePad 仪表盘">
</p>

---

## 目录

- [安装](#安装)
  - [方式一：开箱即用（推荐）](#方式一开箱即用推荐)
  - [方式二：从源码运行](#方式二从源码运行)
- [使用指南](#使用指南)
  - [鼠标模式](#鼠标模式)
  - [Vibe Coding 子层](#vibe-coding-子层)
  - [Vim 导航模式](#vim-导航模式)
  - [语音输入](#语音输入)
  - [屏幕键盘](#屏幕键盘)
- [GUI 控制面板](#gui-控制面板)
- [自定义配置](#自定义配置)
- [浏览器适配](#浏览器适配)
- [常见问题](#常见问题)
- [项目结构](#项目结构)

---

## 安装

### 方式一：开箱即用（推荐）

无需安装 Python，解压即用：

1. 从 [Releases](../../releases) 下载 `VibePad-v1.0.0.zip`
2. 解压到任意目录（如 `D:\VibePad`）
3. 双击 `VibePad.exe`

> **注意：** 首次启动会弹出 UAC 窗口（"是否允许此应用对设备进行更改"），点击**是**。这是为了能以管理员权限运行，确保手柄点击能正常操作屏幕键盘。

### 方式二：从源码运行

需要 Python 3.10+：

```bash
# 1. 克隆仓库
git clone https://github.com/fuxiaoji/VibePad.git
cd VibePad

# 2. 装依赖
pip install -r requirements.txt

# 3. 启动
python controller_gui.py
```

**requirements.txt 依赖清单：**

```
hidapi>=0.14.0       # HID 手柄读取
pygame>=2.6.1        # SDL2 手柄后端
pynput>=1.7.7        # 键盘/鼠标模拟
PyQt6>=6.8.0         # GUI 界面
PyYAML>=6.0          # 配置文件读写
uiautomation>=2.0.29 # UI Automation (Vim 导航)
```

---

## 使用指南

### 启动与切换模式

1. 插上手柄（Xbox / PS5 / Switch Pro 均可）
2. 双击 `VibePad.exe`，看到控制面板窗口
3. 按手柄 **SELECT** 键在模式间切换

<p align="center">
  <img src="screenshots/bindings.png" width="800" alt="按键绑定编辑界面">
</p>

### 鼠标模式

通用模式，搞定网页浏览、文件管理、日常操作。


| 按键           | 动作                | 说明                     |
| -------------- | ------------------- | ------------------------ |
| **左摇杆**     | 移动光标            | 灵敏度可调               |
| **右摇杆**     | 页面滚动            | 上下=纵向滚，左右=横向滚 |
| **A**          | 长按拖拽 / 短按点击 | 选文字、拖文件一把梭     |
| **B**          | 鼠标右键            | 右键菜单                 |
| **X**          | 空格                | 暂停/播放                |
| **Y**          | 全屏 (F)            | 视频全屏                 |
| **十字键**     | ↑↓←→            | 浏览/音量调节            |
| **LB**         | Ctrl+Shift+Tab      | 上一个标签页             |
| **RB**         | Ctrl+Tab            | 下一个标签页             |
| **LT**         | 音量−              | 降低音量                 |
| **RT 按住**    | 光标加速            | 加速倍率可在仪表盘调整   |
| **START**      | 静音 (M)            | 开关静音                 |
| **SELECT**     | 切换到 Vim 模式     | 模式切换                 |
| **左摇杆按下** | 语音输入            | 触发 Win+H 系统听写      |
| **右摇杆按下** | 系统虚拟键盘        | 触发 Win+Ctrl+O          |

### Vibe Coding 子层

在**鼠标模式**下**按住 LB 约 0.4 秒**进入 Vibe 快捷键层，松开恢复。配合 VSCode + Copilot / Claude Code 使用。


| 按键           | 动作             | 场景                |
| -------------- | ---------------- | ------------------- |
| **A**          | Tab              | 接受 AI 建议        |
| **B**          | Esc              | 拒绝建议 / 关闭面板 |
| **X**          | Ctrl+Enter       | 提交给 AI           |
| **Y**          | Ctrl+Shift+Enter | 强制提交            |
| **十字键↑**   | ↑               | 光标上              |
| **十字键↓**   | ↓               | 光标下              |
| **十字键←**   | Alt+[            | Copilot 上一条建议  |
| **十字键→**   | Alt+]            | Copilot 下一条建议  |
| **LB**         | Ctrl+C           | 复制                |
| **RB**         | Ctrl+V           | 粘贴                |
| **LT**         | Ctrl+Z           | 撤销                |
| **RT**         | Ctrl+Shift+Z     | 重做                |
| **START**      | Ctrl+S           | 保存                |
| **左摇杆按下** | Ctrl+P           | 快速打开文件        |
| **右摇杆按下** | Ctrl+Shift+P     | 命令面板            |

### Vim 导航模式 🧪 测试版

> **已知问题：** 浏览器适配不稳定、部分 UI 元素识别不全、偶发焦点跳转异常。欢迎在 [Issues](../../issues) 反馈具体场景，帮助改进。

纯手柄操作，无需鼠标光标。通过 Windows UI Automation 识别屏幕上所有可交互元素，十字键在各元素间跳转。

三级层级导航：


| 层级        | 名称   | 说明                               |
| ----------- | ------ | ---------------------------------- |
| **Level 1** | 窗口级 | 光圈在应用窗口 + 任务栏间跳转      |
| **Level 2** | 元素级 | 光圈在窗口内按钮/输入框/链接间跳转 |
| **Level 3** | 输入级 | 点击输入框后进入，可输入文字       |


| 按键           | 动作             | 说明                                 |
| -------------- | ---------------- | ------------------------------------ |
| **十字键**     | 方向移动焦点     | Level 1/2 中跳转                     |
| **A**          | 进入 / 点击      | L1→进入窗口, L2→点击元素, L3→点击 |
| **B**          | 返回 / Esc       | L3→L2, L2→L1, L1→Esc              |
| **X**          | Tab              | 在元素间切换                         |
| **Y**          | 右键点击         | 右键菜单                             |
| **LB**         | 上一个标签页     | Ctrl+Shift+Tab                       |
| **RB**         | 下一个标签页     | Ctrl+Tab                             |
| **LT**         | 向上滚动         | 离散滚轮                             |
| **RT 按住**    | 视频倍速         | B站/YouTube 检测到自动二倍速         |
| **START**      | Enter / 切换语言 | L3→Win+Space 切换输入法             |
| **SELECT**     | 切换到鼠标模式   | 模式切换                             |
| **左摇杆按下** | 刷新扫描         | 重新扫描 UI 元素                     |
| **右摇杆按下** | 系统虚拟键盘     | 呼出屏幕键盘                         |
| **左摇杆**     | 快速导航         | 持续推住方向跳转到最远元素           |
| **LT+左摇杆**  | 跳到最远         | 加速跳转                             |
| **右摇杆**     | 页面滚动         | 连续滚轮                             |

<p align="center">
  <img src="screenshots/vim_overlay.png" width="400" alt="Vim 模式焦点高亮环">
</p>

> Vim 模式下屏幕会显示一个**蓝色辉光聚焦环**，标示当前选中的 UI 元素。详细教程见 [VIM_MODE_TUTORIAL.md](VIM_MODE_TUTORIAL.md)

### 语音输入

在鼠标模式下**按下左摇杆**（`LEFT_STICK`），触发 Windows 内置语音听写（Win+H）。

- 弹出一个麦克风框，说话即可
- 识别结果自动输入到当前光标位置
- 再次按下左摇杆或点击关闭
- **无需联网**，Windows 离线语音识别

### 屏幕键盘

在鼠标模式下**按下右摇杆**（`RIGHT_STICK`），呼出 Windows 系统虚拟键盘（Win+Ctrl+O）。

- 用左摇杆移动光标到虚拟按键上
- 按 A 键点击
- 再次按下右摇杆关闭

> **注意：** 屏幕键盘需要管理员权限才能被手柄点击。VibePad 启动时会自动弹 UAC 提权。

---

## GUI 控制面板

启动后看到三个标签页：

### 📊 仪表盘

![1779424530612](images/README/1779424530612.png)

- **左侧**：摇杆位置实时可视化（XY 坐标圈）+ 扳机力度条
- **右侧**：当前模式 + 激活子层 + 按钮状态 + 模式切换事件日志
- **底部**：鼠标灵敏度滑块 + RT 加速倍率滑块

### 🎮 按键绑定

<p align="center">
  <img src="screenshots/bindings.png" width="800" alt="按键绑定编辑器">
</p>

- 选择模式和子层（下拉框切换）
- 双击任意映射项打开编辑器
- 支持的动作类型：鼠标（左键/右键/拖拽/滚轮）、键盘（单键/组合键）、导航、语音、模式切换

### 📖 说明书

<p align="center">
  <img src="screenshots/manual.png" width="800" alt="说明书">
</p>

完整的按键对照表和使用技巧，包含模式概览、快速上手指南、常见场景操作。

---

## 自定义配置

`config.yaml` 是核心配置文件，GUI 修改会自动保存：

```yaml
global:
  mouse_sensitivity: 1.4        # 光标灵敏度 (0.1-5.0)
  scroll_sensitivity: 1.0       # 滚轮灵敏度
  deadzone: 0.15                # 摇杆死区 (0.05-0.5)
  cursor_speed_curve: linear    # 速度曲线: linear / quadratic / cubic
  mode_switch_hold_ms: 500      # 模式切换长按阈值 (毫秒)
  mouse_speed_boost: 3.4        # RT 加速倍率

modes:
  mouse:
    switch_button: SELECT
    layers:                     # 子层（按住特定按键激活）
      vibe:
        hold_button: LB         # 按住 LB 激活 Vibe 子层
        mappings:
          A: key.tab
          B: key.escape
          # ... 层内映射覆盖基础映射
    mappings:
      LEFT_STICK_X: mouse_x
      LEFT_STICK_Y: mouse_y
      A: mouse_drag
      SELECT: switch_mode.vim
      # ...

  vim:
    switch_button: SELECT
    mappings:
      DPAD_UP: nav.up
      A: nav.click
      # ...
```

### 动作字符串格式


| 前缀           | 格式     | 示例                                            |
| -------------- | -------- | ----------------------------------------------- |
| `mouse_`       | 鼠标动作 | `mouse_drag`, `mouse_right`, `mouse_speed_hold` |
| `key.`         | 键盘按键 | `key.tab`, `key.ctrl+c`, `key.win+ctrl+o`       |
| `nav.`         | 导航动作 | `nav.click`, `nav.up`, `nav.enter`              |
| `switch_mode.` | 模式切换 | `switch_mode.vim`                               |
| `voice_input`  | 语音输入 | `voice_input`                                   |
| `null`         | 无映射   | `null`                                          |

---

## 浏览器适配

Vim 导航模式通过 UIA 识别网页元素，不同浏览器支持不同：


| 浏览器      | 网页内容导航 | 说明                                          |
| ----------- | ------------ | --------------------------------------------- |
| **Edge**    | ✅ 原生支持  | **推荐！** 打开 B站即可用手柄导航             |
| **Chrome**  | ⚠️ 需配置  | 启动时加`--force-renderer-accessibility` 参数 |
| **Firefox** | ✅ 支持      | 原生支持 UIA                                  |

诊断浏览器：`python diagnose_browser_uia.py`

---

## 常见问题

### 双击 VibePad.exe 没反应

请在解压目录打开 **PowerShell**（Shift + 右键 → 在此处打开 PowerShell），运行：

```
.\VibePad.exe
```

将错误信息贴到 [Issues](../../issues)。

### 屏幕键盘弹出但手柄无法点击

需要**管理员权限**。VibePad 启动时应会弹 UAC 窗口，请点击"是"。如果禁用了 UAC，请右键 `VibePad.exe` → "以管理员身份运行"。

### 手柄未识别

1. 确保手柄已连接（有线或蓝牙）
2. 到 [Gamepad Tester](https://gamepad-tester.com/) 确认系统能识别
3. Xbox / PS5 手柄通常直接支持；第三方手柄可能需要 XInput 驱动

### Vim 模式在 Chrome 中找不到元素

Chrome 默认不开启无障碍接口。两个解决方案：

- 换用 **Microsoft Edge**（原生支持）
- Chrome 启动时加参数：`chrome.exe --force-renderer-accessibility`

---

## 项目结构

```
VibePad/
├── README.md                   ← 你在这里
├── VIM_MODE_TUTORIAL.md        Vim 导航详细教程
├── config.yaml                 核心配置文件
├── controller_gui.py           GUI 主入口
├── diag_gamepad.py             手柄诊断工具
├── diagnose_browser_uia.py     浏览器 UIA 适配诊断
├── requirements.txt            Python 依赖
├── screenshots/                截图（文档用）
├── src/
│   ├── controller.py           手柄读取 (XInput/SDL2/HID 多后端)
│   ├── controller_mock.py      键盘模拟手柄 (无手柄时调试用)
│   ├── config.py               配置加载/保存
│   ├── engine.py               模式引擎 (输入→输出翻译)
│   ├── mouse_sim.py            鼠标模拟 (SendInput + UIA 回退)
│   ├── key_sim.py              键盘模拟 (pynput)
│   ├── navigator.py            Vim 焦点导航 (UIA + Win32 覆盖层)
│   ├── voice_input.py          语音输入 (SpeechRecognition)
│   ├── types.py                类型定义
│   ├── main.py                 CLI 入口
│   └── ui/                     GUI 子组件
└── tests/                      单元测试
```

## Keywords

`vibecoding` `vibe-coding` `gamepad` `controller` `手柄` `手柄操控电脑` `手柄编程` `gamepad-to-keyboard` `copilot-shortcut` `claude-code` `bilibili` `spatial-navigation` `uiautomation` `win32` `accessibility` `focus-navigation` `screen-keyboard`
