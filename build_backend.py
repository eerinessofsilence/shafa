from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_all

SUPPORTED_TARGET_PLATFORMS = {"darwin", "linux", "win32"}


def _host_platform() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _normalize_target_platform(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "darwin": "darwin",
        "linux": "linux",
        "mac": "darwin",
        "macos": "darwin",
        "win": "win32",
        "win32": "win32",
        "windows": "win32",
    }
    target_platform = aliases.get(normalized)
    if target_platform is None:
        supported = ", ".join(sorted(SUPPORTED_TARGET_PLATFORMS))
        raise SystemExit(
            f"Unsupported SHAFA_BACKEND_TARGET '{value}'. Expected one of: {supported}."
        )
    return target_platform


def _resolve_target_platform() -> str:
    configured = os.getenv("SHAFA_BACKEND_TARGET", "").strip()
    if not configured:
        return _host_platform()
    return _normalize_target_platform(configured)


def _ensure_native_target(target_platform: str) -> None:
    host_platform = _host_platform()
    if target_platform == host_platform:
        return

    raise SystemExit(
        "PyInstaller builds native executables only. "
        f"Cannot build a {target_platform} backend from {host_platform}. "
        "Run this build on the target OS or provide a prebuilt backend binary."
    )


def _output_name(target_platform: str) -> str:
    if target_platform == "win32":
        return "ShafaControlBackend.exe"
    return "ShafaControlBackend"


def _write_build_info(
    path: Path,
    *,
    executable_name: str,
    host_platform: str,
    target_platform: str,
) -> None:
    payload = {
        "executableName": executable_name,
        "hostPlatform": host_platform,
        "pythonVersion": ".".join(str(part) for part in sys.version_info[:3]),
        "targetPlatform": target_platform,
    }
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def _data_arg(path: Path, destination: str = ".") -> str:
    return f"{path}{os.pathsep}{destination}"


def _add_data_args(path: Path, destination: str = ".") -> list[str]:
    if not path.exists():
        return []
    return ["--add-data", _data_arg(path, destination)]


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
    host_platform = _host_platform()
    target_platform = _resolve_target_platform()
    _ensure_native_target(target_platform)

    output_dir = root / "dist" / "backend"
    output = output_dir / _output_name(target_platform)
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
        "inquirer",
        "PIL",
        "playwright",
        "dotenv",
        "Levenshtein",
        "multipart",
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
            *_add_data_args(root / "shafa_logic" / "main.py", "shafa_logic"),
            *_add_data_args(root / "shafa_logic" / "data", "shafa_logic/data"),
            *_add_data_args(root / "shafa_logic" / "core", "shafa_logic/core"),
            *_add_data_args(
                root / "shafa_logic" / "controller",
                "shafa_logic/controller",
            ),
            *_add_data_args(root / "shafa_logic" / "models", "shafa_logic/models"),
            *_add_data_args(root / "shafa_logic" / "utils", "shafa_logic/utils"),
            *_add_data_args(
                root / "shafa_logic" / "telegram_subscription",
                "shafa_logic/telegram_subscription",
            ),
            *package_args,
            "--collect-submodules=telegram_accounts_api",
            "--collect-submodules=shafa_control",
            "--collect-submodules=telethon",
        ]
    )
    _write_build_info(
        output_dir / "backend-build-info.json",
        executable_name=output.name,
        host_platform=host_platform,
        target_platform=target_platform,
    )
    print(f"Built backend executable: {output}")


if __name__ == "__main__":
    main()
