from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

APP_MODES = ("clothes", "sneakers")


def validate_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in APP_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    return normalized


@dataclass
class AppConfig:
    mode: str = "clothes"

    def __post_init__(self) -> None:
        self.mode = validate_mode(self.mode)


class AppConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppConfig()
        mode = payload.get("mode", "clothes")
        try:
            return AppConfig(mode=validate_mode(mode))
        except ValueError:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        mode = validate_mode(config.mode)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"mode": mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
