# 实施计划

## 总体里程碑
- [x] **Phase 0**: Git/GitHub初始化 + 项目骨架
- [ ] **Phase 1** (1-2周): 基础框架 + 鼠标模拟 + vibe coding快捷键映射
- [ ] **Phase 2** (2-3周): Vim风格UI焦点导航
- [ ] **Phase 3** (1-2周): 手柄打字法
- [ ] **Phase 4** (2-3周): GUI桌面应用集成

---

## Phase 0: Git/GitHub + 项目骨架（当前）

### 0.1 版本控制
- [ ] 初始化 Git 仓库
- [ ] 创建 `.gitignore`
- [ ] 创建 GitHub 仓库并推送

### 0.2 项目文件
- [ ] 编写 `README.md`
- [ ] 创建 `src/` 目录结构和空模块文件
- [ ] 编写 `requirements.txt`
- [ ] 编写 `config.yaml` 默认配置
- [ ] 创建 `docs/api/` 文档目录

---

## Phase 1: 鼠标模拟 + vibe coding

### 1.1 手柄输入捕获
- [ ] 使用 `inputs` 库捕获手柄连接/断开事件
- [ ] 读取摇杆（左摇杆）、按钮、扳机等原始事件
- [ ] 对手柄输入做死区（deadzone）处理，避免漂移
- [ ] 实现输入事件的生产者模型（供下游模块消费）

> 📝 **文档checkpoint**: 完成后写 `docs/api/controller.md`，测试捕获延迟和死区精度

### 1.2 鼠标模拟
- [ ] 左摇杆 → 光标移动（支持灵敏度调节）
- [ ] 右摇杆 → 滚轮（上下滚动）
- [ ] A按钮 → 鼠标左键点击
- [ ] B按钮 → 鼠标右键点击
- [ ] 模式切换键：长按或双击进入/退出鼠标模式

> 📝 **文档checkpoint**: 完成后写 `docs/api/mouse_sim.md`，手动测试光标跟随和点击准确性

### 1.3 键盘模拟
- [ ] 单键映射（手柄按钮 → 键盘按键）
- [ ] 组合键支持（如 `Cmd+Enter`、`Cmd+C/V`）
- [ ] 按住连发/长按区分

> 📝 **文档checkpoint**: 完成后写 `docs/api/key_sim.md`，测试按键映射准确率

### 1.4 vibe coding 快捷键映射
- [ ] 定义vibe coding常用按键映射表：
  - 语音识别键（Whisker 触发键）
  - Accept 键（Tab / Enter）
  - 撤销/重做
  - 复制/粘贴
  - 代码补全触发
- [ ] 与键盘模拟模块集成
- [ ] 配置文件中自定义映射

> 📝 **文档checkpoint**: 完成后写 `docs/api/vibe_mappings.md`，在VS Code中实测

### 1.5 配置与管理
- [ ] YAML配置文件加载与热重载
- [ ] 多配置文件支持（鼠标模式 / coding模式 / 打字模式）
- [ ] 模式切换逻辑（手柄按钮切换不同配置层）

> 📝 **文档checkpoint**: Phase 1整体测试 + `docs/api/phase1_integration.md`

### 1.6 Phase 1 收尾
- [ ] 整理 `docs/api/` 全部接口文档
- [ ] 端到端测试：手柄→鼠标移动→快捷键输入
- [ ] Git commit + push
- [ ] **推荐 Phase 2 启动条件**

---

## Phase 2: Vim风格UI焦点导航

### 2.1 技术预研
- [ ] 调研 `pyobjc` + `AXUIElement` API 可行性
- [ ] 调研 Web 页面焦点获取（AppleScript / JS注入）

### 2.2 核心实现
- [ ] 通过 Accessibility API 获取当前窗口UI元素树
- [ ] 方向键在可交互元素间上下左右导航
- [ ] 高亮当前焦点元素（绘制覆盖层）
- [ ] 支持原生App、系统对话框

### 2.3 Web页面适配
- [ ] Web页面焦点导航
- [ ] 输入框、按钮、链接识别

> 📝 **文档checkpoint**: 完成后写 `docs/api/navigator.md`

### 2.4 Phase 2 收尾
- [ ] 整理文档
- [ ] 端到端测试
- [ ] Git commit + push
- [ ] **推荐 Phase 3 启动条件**

---

## Phase 3: 手柄打字法

### 3.1 核心实现
- [ ] 设计按钮-字母映射表（参考键盘ASDFJKL手位）
- [ ] 实现长按按钮弹出轮盘选择（摇杆选字母）
- [ ] 实现功能键组合（Shift/Ctrl修饰）
- [ ] 输入法模式切换（英文 / 符号 / 数字）

> 📝 **文档checkpoint**: 完成后写 `docs/api/typer.md`

### 3.2 Phase 3 收尾
- [ ] 整理文档
- [ ] 打字效率测试
- [ ] Git commit + push
- [ ] **推荐 Phase 4 启动条件**

---

## Phase 4: GUI桌面应用

### 4.1 GUI框架搭建
- [ ] PyQt6 主窗口骨架
- [ ] 系统托盘图标
- [ ] 手柄连接状态指示

### 4.2 功能面板
- [ ] 配置页面：可视化编辑按键映射
- [ ] 模式切换面板：鼠标 / 导航 / 打字模式
- [ ] 灵敏度调节滑块

### 4.3 集成与打包
- [ ] 集成全部Phase 1-3功能到GUI
- [ ] macOS .app 打包（py2app / PyInstaller）
- [ ] 权限引导（辅助功能、输入监控）

### 4.4 Phase 4 收尾
- [ ] 整体测试 + bug修复
- [ ] 用户文档编写
- [ ] Release 发布

---

> 每完成一个任务将 `[ ]` 改为 `[x]`。每个功能实现后停一下 — 写文档、测准确、再继续。
