"""CLI入口 — 手柄操控电脑。

启动后监听手柄输入，根据配置文件驱动鼠标和键盘。
按 Ctrl+C 退出。

用法:
    python src/main.py
    python src/main.py --config my_config.yaml
    python src/main.py --list
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

from src.config import load_config
from src.controller import GamepadListener, find_controllers
from src.engine import ModeEngine


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
    print(f"配置: {args.config}")
    print(f"死区: {config.global_.deadzone}")
    print(f"模式: {', '.join(config.mode_names)}")

    listener = GamepadListener(deadzone=config.global_.deadzone)
    engine = ModeEngine(config, listener)

    def on_connect():
        print(f"\r手柄已连接 | 当前模式: {engine.current_mode}")

    def on_disconnect():
        print("\r手柄已断开 — 等待重新连接...")

    listener.on_connect(on_connect)
    listener.on_disconnect(on_disconnect)

    engine.start()
    print("正在等待手柄连接...")

    if not listener.start():
        print("未找到手柄，请连接后重试")
        return

    # 状态显示间隔
    last_status = 0.0

    def cleanup(sig, frame):
        print("\n正在退出...")
        engine.stop()
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    try:
        while True:
            engine.tick()

            # 每2秒显示一次状态
            now = time.monotonic()
            if now - last_status > 2.0:
                state = listener.state
                ls = state.left_stick
                print(f"\r[模式: {engine.current_mode}] "
                      f"摇杆({ls.x:+.2f}, {ls.y:+.2f})  "
                      f"LT:{state.left_trigger.value:.2f} "
                      f"RT:{state.right_trigger.value:.2f}  Ctrl+C退出",
                      end="", flush=True)
                last_status = now

            time.sleep(0.01)  # ~100Hz tick rate

    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        listener.stop()
        print("\n已退出")


if __name__ == "__main__":
    main()
