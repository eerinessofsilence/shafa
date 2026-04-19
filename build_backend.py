from __future__ import annotations

import os
from pathlib import Path

import PyInstaller.__main__


def _data_arg(path: Path) -> str:
    return f"{path}{os.pathsep}."


def main() -> None:
    root = Path(__file__).resolve().parent
    os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(root / ".pyinstaller"))
    PyInstaller.__main__.run(
        [
            str(root / "desktop_backend.py"),
            "--name=ShafaControlBackend",
            "--onefile",
            "--console",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(root / "dist" / "backend"),
            "--workpath",
            str(root / "build" / "backend"),
            "--specpath",
            str(root / "build" / "backend-spec"),
            "--add-data",
            _data_arg(root / "accounts_state.json"),
            "--add-data",
            _data_arg(root / "telegram_channel_templates.json"),
            "--collect-submodules=telegram_accounts_api",
            "--collect-submodules=shafa_control",
            "--collect-submodules=telethon",
            "--collect-submodules=uvicorn",
        ]
    )


if __name__ == "__main__":
    main()
