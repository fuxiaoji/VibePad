# engine — 模式引擎

## 概述
手柄操控电脑的核心调度模块。连接输入层（GamepadListener）和输出层（MouseSimulator + KeySimulator），根据当前模式的配置映射将手柄事件路由为键鼠动作。

## 数据流

```
GamepadListener ──┬── on_state (摇杆) ──→ tick() → MouseSimulator.move/scroll
                  │
                  └── on_button (按钮) ──→ _handle_press/release → MouseSimulator.click
                                                                  → KeySimulator.tap/press
                                                                  → 模式切换
```

## 公开API

### `ModeEngine`

#### 构造参数
| 参数 | 类型 | 说明 |
|------|------|------|
| config | AppConfig | 配置对象 |
| listener | GamepadListener | 手柄监听器 |

#### 属性
- `current_mode: str` — 当前模式名
- `mouse: MouseSimulator` — 鼠标模拟器实例
- `keys: KeySimulator` — 键盘模拟器实例

#### 方法
| 方法 | 说明 |
|------|------|
| `start()` | 注册按钮回调到 listener |
| `stop()` | 释放所有按键 |
| `tick()` | 每帧调用，处理摇杆→鼠标移动和滚轮 |

### `ActionType` 枚举
| 值 | 说明 | 配置示例 |
|----|------|----------|
| MOUSE | 鼠标动作 | `mouse_left`, `mouse_x` |
| KEY | 键盘动作 | `key.tab`, `key.cmd+enter` |
| SWITCH | 模式切换 | `switch_mode.vibe` |
| NONE | 无映射 | `null` |

### `classify_action(mapping_value) -> (ActionType, param)`
判断映射值属于哪类动作。

## 模式切换逻辑

1. 配置中定义 `switch_button`（如 SELECT）
2. 按下 SELECT → 记录时间
3. 释放 SELECT → 计算按住时长
4. 时长 < `mode_switch_hold_ms`(默认500ms) → 短按，切换到 `param` 指定模式
5. 时长 ≥ threshold → 长按，忽略（留给未来的长按功能）

## 使用示例

```python
from src.config import load_config
from src.controller import GamepadListener
from src.engine import ModeEngine

config = load_config("config.yaml")
listener = GamepadListener(deadzone=config.global_.deadzone)
engine = ModeEngine(config, listener)

engine.start()
listener.start()

# 主循环
while True:
    engine.tick()
    time.sleep(0.01)  # ~100Hz tick

# 清理
engine.stop()
listener.stop()
```

## 设计说明

### 摇杆→鼠标：帧率补偿
`tick()` 中记录 `dt`（距上次 tick 的秒数），`mouse.move(stick_x, stick_y, dt)` 内部用 `dt` 计算该帧位移。这样无论主循环跑 30fps 还是 120fps，光标移动速度一致。

### 按钮边沿检测
按下的第一帧触发动作（`_handle_press`），持续按住不再重复触发。释放时触发对应的 release 动作。这避免了高频事件导致的重复点击。
