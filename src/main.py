"""CLI入口 — 手柄操控电脑（开发期）。

启动后监听手柄输入，在终端打印实时状态。
按 Ctrl+C 退出。

用法:
    python src/main.py
    python src/main.py --config my_config.yaml
"""

import argparse
import signal
import sys
import time

from src.config import load_config
from src.controller import GamepadListener, find_controllers, Button


def main():
    parser = argparse.ArgumentParser(description="手柄操控电脑")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--list", action="store_true", help="列出已连接的手柄")
    args = parser.parse_args()

    if args.list:
        controllers = find_controllers()
        if controllers:
            print("已连接的手柄:")
            for c in controllers:
                print(f"  - {c}")
        else:
            print("未检测到手柄")
        return

    config = load_config(args.config)
    deadzone = config.global_.deadzone
    print(f"配置文件: {args.config}")
    print(f"死区: {deadzone}")
    print(f"可用模式: {', '.join(config.mode_names)}")

    listener = GamepadListener(deadzone=deadzone)

    # 注册按钮回调
    def on_button(btn: Button, pressed: bool):
        state_str = "按下" if pressed else "释放"
        print(f"  [{state_str}] {btn.name}")

    listener.on_button(on_button)

    # 注册连接回调
    def on_connect():
        print("手柄已连接")

    def on_disconnect():
        print("手柄已断开")

    listener.on_connect(on_connect)
    listener.on_disconnect(on_disconnect)

    # 启动
    print("正在等待手柄连接...")
    if not listener.start():
        print("未找到手柄，请连接后重试")
        return

    print("监听中... 按 Ctrl+C 退出")

    # 主循环：打印摇杆状态
    def cleanup(sig, frame):
        print("\n正在退出...")
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    try:
        while True:
            state = listener.state
            ls = state.left_stick
            rs = state.right_stick
            lt = state.left_trigger
            rt = state.right_trigger

            # 只打印非零摇杆
            parts = []
            if abs(ls.x) > 0.01 or abs(ls.y) > 0.01:
                parts.append(f"左摇杆({ls.x:+.2f}, {ls.y:+.2f})")
            if abs(rs.x) > 0.01 or abs(rs.y) > 0.01:
                parts.append(f"右摇杆({rs.x:+.2f}, {rs.y:+.2f})")
            if lt.value > 0.01:
                parts.append(f"LT:{lt.value:.2f}")
            if rt.value > 0.01:
                parts.append(f"RT:{rt.value:.2f}")
            if parts:
                print("\r" + " | ".join(parts), end="", flush=True)

            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("\n已退出")


if __name__ == "__main__":
    main()
