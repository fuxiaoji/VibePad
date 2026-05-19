# 手柄操控电脑 (Controller)

## 项目概述

用手柄（游戏控制器）操控电脑，替代/补充键鼠操作。最终交付一个 PyQt6 图形化桌面软件。

三大核心功能：

1. **鼠标模拟模式** — 摇杆移动光标，按钮映射点击，集成vibe coding快捷键
2. **Vim操作逻辑模式** — 方向键在可交互UI元素间焦点导航（类似Switch UI）
3. **手柄打字法** — 按钮组合映射字母，类似键盘ASDFJKL手位

## GitHub

https://github.com/fuxiaoji/controller

## 平台策略

- **Windows** (当前): pygame/SDL2 后端优先（XInput + DirectInput 原生支持），hidapi 备选
- **macOS**: 仅官方手柄可用（Xbox Series/PS5/Switch Pro），第三方手柄(VID:0x413D 等)不被系统识别
- **Linux**: hidapi + pygame 后端均可工作

## 技术栈


| 层             | 选择                                                  | 说明                                           |
| -------------- | ----------------------------------------------------- | ---------------------------------------------- |
| 语言           | Python 3.8+                                           |                                                |
| 手柄输入(物理) | pygame/SDL2 优先, hidapi 备选                         | `src/controller.py` — 自动选择最佳后端        |
| 手柄输入(模拟) | `pygame` 键盘事件                                     | `src/controller_mock.py` — 无手柄时用键盘测试 |
| 鼠标模拟       | `pynput.mouse.Controller`                             | `src/mouse_sim.py`                             |
| 键盘模拟       | `pynput.keyboard.Controller`                          | `src/key_sim.py` — 非macOS上cmd→ctrl自动映射 |
| UI导航         | macOS:`pyobjc`; Windows: `uiautomation` / `pywinauto` | Phase 2 用到                                   |
| GUI            | `PyQt6`                                               | Phase 4 最终交付                               |
| 配置           | YAML                                                  | `config.yaml`                                  |
| 测试           | pytest                                                | 58 tests passed @ Windows                      |

## 架构

```
config.yaml ──→ config.py (AppConfig)
                     │
                     ▼
controller.py ──→ GamepadListener ──→ GamepadState
(后台线程读HID)     (回调通知)         (状态快照)
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
engine.py ───→ MouseSimulator    KeySimulator
(模式路由)      (移动/点击)       (按键/组合键)
```

### 模块清单


| 文件                     | 职责                                          | 状态                  |
| ------------------------ | --------------------------------------------- | --------------------- |
| `src/types.py`           | 共享数据类型 (Button, GamepadState, 回调类型) | 完成                  |
| `src/controller.py`      | 多后端物理手柄 (pygame优先, hidapi备选)       | 完成(Windows验证通过) |
| `src/controller_mock.py` | 键盘模拟手柄 (WASD/IJKL/Space...)             | 完成                  |
| `src/config.py`          | YAML配置加载                                  | 完成                  |
| `src/engine.py`          | 模式引擎，输入→输出路由                      | 完成                  |
| `src/mouse_sim.py`       | 鼠标模拟 (移动/点击/滚轮/拖拽/速度曲线)       | 完成                  |
| `src/key_sim.py`         | 键盘模拟 (单键/组合键/长按)                   | 完成                  |
| `src/main.py`            | CLI入口                                       | 完成                  |
| `test_gui.py`            | PyQt6 调试面板                                | 完成                  |
| `src/app.py`             | GUI应用入口                                   | 未开始(Phase 4)       |
| `src/navigator.py`       | Vim风格焦点导航                               | 未开始(Phase 2)       |
| `src/typer.py`           | 手柄打字法                                    | 未开始(Phase 3)       |

### test_gui.py 调试面板

- 运行: `python test_gui.py`
- 自动检测手柄：有物理手柄就用 `controller.py`，没有则用 `controller_mock.py`(键盘模拟)
- 显示所有手柄输入：两个摇杆可视化、16按钮状态、扳机条、十字键、模式、FPS
- 完全集成 ModeEngine，真实驱动鼠标和键盘

## macOS 手柄踩坑记录

- **VID:0x413D PID:0x2104** (第三方 Xbox 360 兼容): macOS 上**完全不支持**。蓝牙能配对但无任何API可读取输入
- 尝试过的方案: `inputs`(0设备) → `pygame/SDL2`(0设备) → `hidapi`(能枚举不能打开) → `GCController`(0控制器) → `IOKit HID`(ctypes太复杂)
- **结论**: macOS 只认官方手柄 (Microsoft/索尼/任天堂)，第三方手柄需要 360Controller 驱动（但新版macOS可能不兼容）
- **Windows上**: 以上所有方案预计都能工作（XInput/DirectInput）

## Windows 转移指南

### 环境搭建

```bash
git clone https://github.com/fuxiaoji/controller.git
cd controller
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 手柄检测

Windows 上三种方式都应该有效：

1. `inputs` 库 — 直接读 evdev/XInput
2. `pygame/SDL2` — 游戏行业标准
3. `hidapi` — 底层HID

如果当前 `controller.py` 在 Windows 上不work，修改 `src/controller.py` 换用 `pygame` 后端（已有SDL2事件循环经验）。

vim模式还是有很大的问题。我想重申一下我的设计思路最通用的应该是鼠标模式其核心功能就是模拟鼠标，vim模式应该是这样的，通过鼠标模式调整分屏了之后，屏幕上会有各个窗口，在最初的层级，光圈只在这些窗口之间切换（yong左摇杆控制方向，按住右板机可以加快移动速度，按住卓喷漆配合左摇杆可以直接到达那个方向最远处）比如说现在屏幕上有B站和VSCOde两个窗口，那么光圈就会只在这两个窗口，还有windows最底下的这一排任务栏进行跳转，当光圈停留在一个窗口的时候点击进入下一级层级，比如说浏览器B站这个时候光圈就只在浏览器内部的这些可点击元素之间流转，你可以考察一下浏览器B站的前端界面，做一下适配，然后以一个钱左右返回键可以返回更上一级层级，也可以用按住快捷键配合左摇杆直接在各个窗口之间切换

### 参考

- 调研报告: `JJC-20260311-009-手柄操控电脑调研报告 2.md`
- 实施计划: `plantodo.md`
- 模块文档: `docs/api/`
