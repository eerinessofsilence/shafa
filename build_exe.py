from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


def main() -> None:
    root = Path(__file__).resolve().parent
    PyInstaller.__main__.run(
        [
            str(root / "ui.py"),
            "--name=ShafaControl",
            "--windowed",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(root / "dist"),
            "--workpath",
            str(root / "build"),
            "--specpath",
            str(root),
            "--add-data",
            f"{root / 'shafa'}:shafa",
        ]
    )


if __name__ == "__main__":
    main()
