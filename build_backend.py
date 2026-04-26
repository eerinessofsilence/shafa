from __future__ import annotations

import os
from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_all


def _data_arg(path: Path) -> str:
    return f"{path}{os.pathsep}."


def _add_data_args(path: Path) -> list[str]:
    if not path.exists():
        return []
    return ["--add-data", _data_arg(path)]


def _collect_package_args(package: str) -> list[str]:
    datas, binaries, hiddenimports = collect_all(package)
    args: list[str] = []

    for src, dest in datas:
        args.extend(["--add-data", f"{src}{os.pathsep}{dest}"])
    for src, dest in binaries:
        args.extend(["--add-binary", f"{src}{os.pathsep}{dest}"])
    for hiddenimport in hiddenimports:
        args.extend(["--hidden-import", hiddenimport])

    return args


def main() -> None:
    root = Path(__file__).resolve().parent
    output = root / "dist" / "backend" / "ShafaControlBackend.exe"
    package_args = []
    for package in (
        "uvicorn",
        "fastapi",
        "starlette",
        "pydantic",
        "pydantic_core",
        "anyio",
        "httpx",
        "websockets",
        "httptools",
    ):
        package_args.extend(_collect_package_args(package))

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
            *_add_data_args(root / "accounts_state.json"),
            *_add_data_args(root / "telegram_channel_templates.json"),
            *package_args,
            "--collect-submodules=telegram_accounts_api",
            "--collect-submodules=shafa_control",
            "--collect-submodules=telethon",
        ]
    )
    print(f"Built backend executable: {output}")


if __name__ == "__main__":
    main()
