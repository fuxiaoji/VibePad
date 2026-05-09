# 手柄操控电脑 (Controller)

## 项目概述
用手柄（游戏控制器）操控电脑，替代/补充键鼠操作。最终交付一个带图形化界面的桌面软件。核心三大功能：
1. **鼠标模拟模式** — 摇杆移动光标，按钮映射点击，集成vibe coding快捷键
2. **Vim操作逻辑模式** — 方向键在可交互UI元素间焦点导航（类似Switch UI）
3. **手柄打字法** — 按钮组合映射字母，类似键盘ASDFJKL手位

## 技术栈
- **语言**: Python 3.9+
- **手柄输入**: `inputs`（首选，跨平台且轻量），备选 `pygame`
- **鼠标/键盘模拟**: `pyautogui` + `pynput`
- **UI导航**: macOS `pyobjc` (Accessibility API)
- **GUI应用**: `PyQt6`（最终交付形态）
- **配置文件**: YAML

## 核心决策
| 决策 | 选择 | 理由 |
|------|------|------|
| 方案路线 | Python完全自研（方案B） | 跨平台灵活，无C++依赖，快速迭代 |
| 优先平台 | macOS | 当前开发环境，跑通后扩展Win/Linux |
| Phase 1范围 | 鼠标模拟 + vibe coding快捷键 | 最高频场景，快速出MVP |
| GUI框架 | PyQt6 | 成熟稳定，跨平台，组件丰富 |
| 版本控制 | Git + GitHub | 代码留痕，版本回溯 |

详见 `JJC-20260311-009-手柄操控电脑调研报告 2.md`

## 目录结构约定
```
controler/
├── agent.md              # 项目知识库
├── plantodo.md           # 实施计划与任务追踪
├── README.md             # 项目说明
├── requirements.txt      # Python依赖
├── config.yaml           # 手柄映射配置
├── src/
│   ├── __init__.py
│   ├── main.py           # CLI入口（开发期）
│   ├── app.py            # GUI应用入口（交付期）
│   ├── controller.py     # 手柄输入捕获
│   ├── mouse_sim.py      # 鼠标模拟
│   ├── key_sim.py        # 键盘模拟
│   ├── navigator.py      # Vim风格焦点导航
│   ├── typer.py          # 手柄打字法
│   └── ui/
│       └── main_window.py  # GUI主窗口
├── docs/
│   └── api/              # 模块接口文档（每实现一个功能后更新）
├── tests/
│   ├── test_controller.py
│   ├── test_mouse_sim.py
│   └── ...
└── .gitignore
```

## 工作流约定

### 版本控制
- 代码根目录即 Git 仓库，关联 GitHub 远程
- 每个功能模块完成后做一次提交，提交信息格式：`feat(模块名): 简述`
- 不提交虚拟环境、`.DS_Store`、`__pycache__`、IDE 配置

### 开发流程（每个功能模块循环）
```
实现 → 编写接口文档(docs/api/) → 整理成果 → 测试 → 提交 → 推荐下一步
```
- **实现**: 写代码到功能可用
- **文档**: 在 `docs/api/` 下写模块接口文档（公开API、配置项、使用示例）
- **整理**: 回顾本轮产出，更新 plantodo.md 进度
- **测试**: 写单元测试 + 手动验证
- **提交**: Git commit + push
- **推荐**: 明确建议下一个要做的模块，等待用户确认

### 规划留痕
- 任何非平凡实现前，先更新 `plantodo.md`
- 完成后勾选对应任务（`[ ]` → `[x]`）

### 项目知识留痕
- 技术决策（含理由）记录到本文 `agent.md` 的核心决策表
- 踩坑经验、API注意事项补充到对应章节
- 新会话通过本文 + `plantodo.md` 快速恢复上下文

### 开发节奏

| 阶段 | 内容 | 产出 |
|------|------|------|
| Phase 1 | 鼠标模拟 + vibe coding | CLI可用的手柄鼠标 |
| Phase 2 | Vim风格焦点导航 | 方向键切换UI焦点 |
| Phase 3 | 手柄打字法 | 按钮→字母映射 |
| Phase 4 | GUI应用 | PyQt6桌面软件，集成全部功能 |
