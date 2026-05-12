# 新电脑环境搭建指南

> 从 macOS 转移到 Windows 继续开发本项目的完整步骤。

## 1. 克隆项目

```bash
git clone https://github.com/fuxiaoji/controller.git
cd controller
```

## 2. Python 环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# 或直接用 conda
conda create -n controller python=3.11
conda activate controller
```

## 3. 安装依赖

```bash
pip install -r requirements.txt
```

如果某些包安装失败，核心依赖手动装：
```bash
pip install pyyaml pynput pyautogui pygame PyQt6 pytest
# 手柄输入（三选一，都装上也没事）
pip install inputs hidapi pygame
```

## 4. 验证安装

```bash
# 运行测试
python -m pytest tests/ -v

# 启动调试面板
python test_gui.py

# CLI模式
python src/main.py
```

## 5. 手柄检测

连接手柄后运行：
```bash
python diag_gamepad.py
```

Windows 上预计 `pygame` 或 `inputs` 能直接检测到。如果 `controller.py` 当前使用的 hidapi 后端不work，参考 `controller_mock.py` 的 pygame 事件循环写法来改写。

## 6. 项目状态（2026-05-12）

- **Phase 0**: ✅ Git/GitHub/项目骨架
- **Phase 1**: ✅ 手柄捕获 + 鼠标模拟 + 键盘模拟 + 模式引擎 + 配置 + 调试面板
- **Phase 2**: 未开始 — Vim风格UI焦点导航
- **Phase 3**: 未开始 — 手柄打字法
- **Phase 4**: 未开始 — PyQt6 GUI桌面应用

## 7. 继续开发的入口

1. 读懂 `agent.md` — 项目知识库
2. 读懂 `plantodo.md` — 下一步任务
3. 运行 `python test_gui.py` — 看调试面板效果
4. 连接手柄验证 `controller.py`，如不work则换pygame后端
5. 开始 Phase 2: `src/navigator.py`

## 8. 关键文件

| 文件 | 用途 |
|------|------|
| `agent.md` | 项目架构、技术决策、约定 |
| `plantodo.md` | 任务清单，勾选进度 |
| `TRANSFER.md` | 本文件 |
| `README.md` | 对外说明 |
| `config.yaml` | 手柄映射配置 |
| `docs/api/` | 每个模块的接口文档 |
| `tests/` | 58个单元测试 |
