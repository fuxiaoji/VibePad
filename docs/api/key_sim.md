# key_sim — 键盘模拟模块

## 概述
基于 `pynput.keyboard.Controller`，将手柄按钮映射为键盘单键/组合键。解析 `config.yaml` 中的 `key.<动作>` 配置字符串。

## 配置字符串格式

```
key.<键名>                → 单键
key.<修饰键>+<键名>       → 组合键
null                      → 无映射
```

### 支持的键名

**修饰键**: `cmd`, `ctrl`, `alt`, `shift`（也支持 `command`, `control`, `option`）

**特殊键**: `tab`, `enter`, `escape`, `space`, `backspace`, `delete`, `up`, `down`, `left`, `right`, `home`, `end`, `page_up`, `page_down`, `f1`-`f12`

**普通键**: `a`-`z`, `0`-`9`, `.`, `,`, `/`, `;`, `'`, `[`, `]`, `-`, `=`

### 配置示例
```yaml
mappings:
  A: key.tab               # 按Tab
  X: key.cmd+enter         # Cmd+Enter
  Y: key.cmd+shift+enter   # 多修饰键
  LB: key.cmd+c            # 复制
```

## 公开API

### `KeySimulator`

#### 方法

| 方法 | 说明 |
|------|------|
| `tap(action_str)` | 按下并立即释放 |
| `combo(action_str)` | `tap` 的别名 |
| `press(action_str)` | 按下并保持（用于长按） |
| `release(action_str)` | 释放之前按住的键 |
| `release_all()` | 释放所有按住的键 |
| `type_text(text)` | 输入一段文字 |

### 内部解析函数

- `_parse_action(action_str) -> Optional[dict]` — 解析为 `{'modifiers': [...], 'key': Key}`
- `_parse_key(key_name) -> Key | str | None` — 单键名转 pynput 对象

## 使用示例

```python
from src.key_sim import KeySimulator

keys = KeySimulator()

# 单键
keys.tap("key.tab")
keys.tap("key.escape")

# 组合键
keys.tap("key.cmd+enter")
keys.combo("key.cmd+c")

# 长按（手动配对的 press/release）
keys.press("key.shift")
# ... 其他操作 ...
keys.release("key.shift")

# 安全清理
keys.release_all()
```

## 设计说明

### press/release 配对
`press()` 会追踪按住的键到 `_held` 列表，`release_all()` 在模式切换和引擎停止时调用，确保不会残留按住状态（否则系统会认为 Shift 一直按着）。
