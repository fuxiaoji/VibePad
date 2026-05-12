# mouse_sim — 鼠标模拟模块

## 概述
基于 `pynput.mouse.Controller`，将手柄摇杆输入转换为光标移动、滚轮和点击。支持三种速度曲线。

## 公开API

### `MouseSimulator`

#### 构造参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| sensitivity | float | 1.0 | 移动灵敏度倍率 |
| scroll_sensitivity | float | 1.0 | 滚轮灵敏度倍率 |
| curve | SpeedCurve | LINEAR | 速度曲线 |
| base_speed | float | 800.0 | 摇杆推满时的基础速度(px/s) |

#### 方法

**光标移动**
- `move(stick_x, stick_y, dt)` — 相对移动光标。`dt` 为帧间隔(秒)，内部计算 `速度 * dt` 得出该帧位移

**点击**
- `click_left()` / `click_right()` / `click_middle()`

**按住/释放（用于拖拽或长按）**
- `press_left()` / `release_left()`
- `press_right()` / `release_right()`

**拖拽**
- `drag_start()` → `drag_move(...)` → `drag_end()`

**滚轮**
- `scroll(dx, dy)` — 水平/垂直滚动

### `SpeedCurve` 枚举

| 值 | 效果 |
|----|------|
| LINEAR | 常用，推多少走多少 |
| QUADRATIC | 精细控制，小幅推动慢，大幅推动快 |
| CUBIC | 更极端的速度差异 |

### 工具函数
- `curve_from_string(name: str) -> SpeedCurve` — "linear"等字符串转枚举

## 使用示例

```python
from src.mouse_sim import MouseSimulator, SpeedCurve

mouse = MouseSimulator(sensitivity=1.5, curve=SpeedCurve.QUADRATIC)

# 在主循环中 (dt 为帧间隔)
mouse.move(stick_x=0.5, stick_y=0.0, dt=0.016)

# 点击
mouse.click_left()
mouse.click_right()

# 滚轮
mouse.scroll(0, -3)  # 向下滚3格
```

## 设计说明

### 速度曲线
`_apply_curve(magnitude)` 公式：
- LINEAR: `m` (原值)
- QUADRATIC: `m²`
- CUBIC: `m³`

QUADRATIC 在摇杆小幅推动 (`m=0.3`) 时输出只有 `0.09`，大幅推动 (`m=0.8`) 时 `0.64`，实现精细+粗调兼具。

### 位移计算
`dx = (stick_x / magnitude) * curve(magnitude) * base_speed * sensitivity * dt`

- `(stick_x / magnitude)`: 归一化方向向量
- `curve(magnitude)`: 速度曲线
- `base_speed * sensitivity`: 基准速度
- `dt`: 帧补偿，保证 30fps 和 120fps 体验一致
