"""配置文件加载模块。

从 YAML 文件加载手柄映射配置，支持热重载。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class GlobalConfig:
    mouse_sensitivity: float = 1.0
    scroll_sensitivity: float = 1.0
    deadzone: float = 0.15
    cursor_speed_curve: str = "linear"
    mode_switch_hold_ms: int = 500


@dataclass
class ModeConfig:
    name: str
    switch_button: str = ""
    mappings: dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    global_: GlobalConfig = field(default_factory=GlobalConfig)
    modes: dict[str, ModeConfig] = field(default_factory=dict)

    def get_mode(self, name: str) -> Optional[ModeConfig]:
        return self.modes.get(name)

    @property
    def mode_names(self) -> list[str]:
        return list(self.modes.keys())

    @property
    def default_mode(self) -> Optional[str]:
        return self.mode_names[0] if self.mode_names else None


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """从YAML文件加载配置。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return AppConfig()

    global_raw = raw.get("global", {})
    global_cfg = GlobalConfig(
        mouse_sensitivity=global_raw.get("mouse_sensitivity", 1.0),
        scroll_sensitivity=global_raw.get("scroll_sensitivity", 1.0),
        deadzone=global_raw.get("deadzone", 0.15),
        cursor_speed_curve=global_raw.get("cursor_speed_curve", "linear"),
        mode_switch_hold_ms=global_raw.get("mode_switch_hold_ms", 500),
    )

    modes = {}
    for name, m in raw.get("modes", {}).items():
        modes[name] = ModeConfig(
            name=name,
            switch_button=m.get("switch_button", ""),
            mappings=m.get("mappings", {}),
        )

    return AppConfig(global_=global_cfg, modes=modes)
