# controller — 手柄输入捕获模块

## 概述
基于 `inputs` 库，在后台线程中循环读取手柄原始事件，维护 `GamepadState` 状态快照，通过回调通知上层模块。

## 公开API

### 数据类型

#### `Button` (Enum)
手柄按钮枚举（Xbox标准命名）。
| 成员 | 说明 |
|------|------|
| A, B, X, Y | 右侧四键 |
| LB, RB | 左/右肩键 (Bumper) |
| LT, RT | 左/右扳机 (Trigger) |
| START, SELECT | 功能键 |
| LEFT_STICK, RIGHT_STICK | 摇杆按下 |
| DPAD_UP/DOWN/LEFT/RIGHT | 十字键 |

#### `Stick` (Enum)
摇杆轴：`LEFT_X`, `LEFT_Y`, `RIGHT_X`, `RIGHT_Y`

#### `StickState`
| 字段 | 类型 | 说明 |
|------|------|------|
| x | float | X轴值 [-1.0, 1.0] |
| y | float | Y轴值 [-1.0, 1.0] |

#### `TriggerState`
| 字段 | 类型 | 说明 |
|------|------|------|
| value | float | 扳机深度 [0.0, 1.0] |
| pressed | bool | 是否超过阈值 |
| threshold | float | 按下判定阈值（默认0.5） |

#### `ButtonState`
| 字段 | 类型 | 说明 |
|------|------|------|
| pressed | bool | 当前是否按下 |
| pressed_at | float | 按下时刻 (time.monotonic) |
| released_at | float | 释放时刻 |
| hold_duration | float | 按住时长(ms) |

#### `GamepadState`
完整手柄状态快照。
| 字段 | 类型 | 说明 |
|------|------|------|
| left_stick | StickState | 左摇杆 |
| right_stick | StickState | 右摇杆 |
| left_trigger | TriggerState | 左扳机 |
| right_trigger | TriggerState | 右扳机 |
| buttons | dict[Button, ButtonState] | 所有按钮状态 |
| dpad | tuple[int, int] | 十字键 (x, y)，值∈{-1,0,1} |
| timestamp | float | 快照时刻 |

方法：
- `is_pressed(button) -> bool` — 某按钮是否按下
- `hold_ms(button) -> float` — 按钮已按住毫秒数

### 核心类

#### `GamepadListener(deadzone=0.15)`
手柄监听器。

**回调注册**:
- `on_state(cb: (GamepadState) -> None)` — 状态更新（高频，每帧）
- `on_button(cb: (Button, bool) -> None)` — 按钮按下/释放
- `on_connect(cb: () -> None)` — 手柄连接
- `on_disconnect(cb: () -> None)` — 手柄断开

**生命周期**:
- `start() -> bool` — 启动后台线程，阻塞直到连接手柄
- `stop()` — 停止监听
- `state -> GamepadState` — 获取当前状态（线程安全）

### 工具函数

#### `find_controllers() -> list[str]`
返回已连接手柄名称列表。

## 使用示例

```python
from src.controller import GamepadListener, Button

listener = GamepadListener(deadzone=0.15)

def on_button(btn: Button, pressed: bool):
    if pressed and btn == Button.A:
        print("A键按下！")

def on_connect():
    print("手柄已连接")

listener.on_button(on_button)
listener.on_connect(on_connect)
listener.start()

# 主循环中使用状态
state = listener.state
if abs(state.left_stick.x) > 0.5:
    print("左摇杆大幅右推")

listener.stop()
```

## 内部实现

### 事件循环
`_loop()` 在 daemon 线程中运行：
1. 等待手柄设备出现（`inputs.devices.gamepads`）
2. 调用 `get_gamepad()` 获取设备
3. 循环 `gamepad.read()` 读取事件
4. `_handle_event(code, value)` 更新内部状态
5. 触发 `_fire_state()` → 所有 on_state 回调

### 死区处理
`_apply_deadzone(value)` 将输入值重新映射：
- 绝对值 < deadzone → 0.0
- 绝对值 ≥ deadzone → 线性重映射到 [0.0, 1.0]

### 重新连接
`UnpluggedError` 时触发 on_disconnect 回调，然后循环等待重新连接。

## 测试
运行 `python3 -m pytest tests/test_controller.py -v`
当前覆盖: 17 tests passed (死区计算、状态管理、回调注册、生命周期)
