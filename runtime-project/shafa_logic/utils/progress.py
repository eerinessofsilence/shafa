import os
import sys

from utils.logging import format_tag

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in _TRUTHY_VALUES


def verbose_photo_logs_enabled() -> bool:
    return env_flag("SHAFA_VERBOSE_PHOTO_LOGS", default=False)


class ProgressBar:
    def __init__(
        self,
        total: int,
        label: str,
        width: int = 24,
        enabled: bool = True,
    ) -> None:
        self.total = max(int(total), 0)
        self.label = label
        self.width = max(width, 10)
        self.current = 0
        self.enabled = enabled and self.total > 0 and sys.stdout.isatty()
        self._line_open = False
        self._last_line_length = 0

    def __enter__(self) -> "ProgressBar":
        self.render()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def render(self) -> None:
        if not self.enabled:
            return
        ratio = self.current / self.total if self.total else 0.0
        filled = int(round(self.width * ratio))
        bar = "#" * filled + "-" * (self.width - filled)
        percent = int(ratio * 100)
        line = (
            f"{format_tag('INFO')} {self.label}: [{bar}] "
            f"{percent:3d}% ({self.current}/{self.total})"
        )
        if len(line) < self._last_line_length:
            line += " " * (self._last_line_length - len(line))
        self._last_line_length = len(line)
        sys.stdout.write(f"\r{line}")
        sys.stdout.flush()
        self._line_open = True

    def advance(self, step: int = 1) -> None:
        if self.total <= 0:
            return
        self.current = min(self.total, self.current + max(step, 0))
        self.render()

    def close(self) -> None:
        if not self.enabled or not self._line_open:
            return
        sys.stdout.write("\n")
        sys.stdout.flush()
        self._line_open = False
        self._last_line_length = 0
