import os
import sys

_COLORS = {
    "INFO": "\033[34m",
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
    "OK": "\033[32m",
}
_RESET = "\033[0m"


def supports_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def log(level: str, message: str) -> None:
    tag = f"[{level}]"
    if supports_color() and level in _COLORS:
        tag = f"{_COLORS[level]}{tag}{_RESET}"
    print(f"{tag} {message}")
