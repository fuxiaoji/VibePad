"""Frozen entry point, with a non-interactive packaged startup check."""

import json
import os
from pathlib import Path
import sys
import traceback


def self_test(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        import controller_gui as gui
        import pygame
        from pygame._sdl2 import controller

        app = gui.QApplication([])
        config_path = str(Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "config.yaml")
        config = gui.load_config(config_path)
        listener = gui.GamepadListener(deadzone=config.global_.deadzone)
        engine = gui.ModeEngine(config, listener)
        window = gui.MainWindow(config, config_path, listener, engine)
        # Exercise GUI construction and painting without generating desktop input.
        window._timer.stop()
        assert not window.grab().isNull()
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.HIDDEN)
        controller.init()
        report.update(ok=True, controllers=controller.get_count(),
                      background_input=os.environ.get("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"))
        assert report["background_input"] == "1"
        pygame.quit()
        window.close()
        app.quit()
    except Exception:
        report.update(ok=False, error=traceback.format_exc())
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2]))
    from controller_gui import main
    main()
