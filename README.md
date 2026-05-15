# Controller - 手柄操控电脑

用手柄（游戏控制器）替代键鼠操控电脑。支持鼠标模拟、Vim风格焦点导航、手柄打字法。

## 功能
- **鼠标模拟** — 摇杆移动光标，按钮点击，集成vibe coding快捷键
- **Vim导航** — 方向键在UI元素间焦点切换（Switch UI风格）
- **手柄打字** — 按钮组合映射键盘输入

## 平台
Windows（当前） → macOS / Linux 兼容

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
# CLI模式（开发期）
python src/main.py

# GUI模式（交付后）
python src/app.py
```

## 手柄连接
- 蓝牙连接：系统蓝牙配对
- USB有线：即插即用
- 推荐：Xbox Wireless Controller / PS5 DualSense / Switch Pro

## 项目结构
```
controler/
├── README.md
├── agent.md           # 项目知识库
├── plantodo.md        # 实施计划
├── config.yaml        # 按键映射配置
├── src/               # 源代码
├── docs/api/          # 模块接口文档
└── tests/             # 测试
```

## 开发状态
Phase 0 — 项目初始化中。详见 [plantodo.md](plantodo.md)

## 参考
- 调研报告: `JJC-20260311-009-手柄操控电脑调研报告 2.md`
- AntiMicroX: https://github.com/AntiMicroX/antimicrox
