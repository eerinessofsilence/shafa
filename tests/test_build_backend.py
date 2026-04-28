from __future__ import annotations

import types

import build_backend
import pytest


def test_normalize_target_platform_maps_windows_aliases() -> None:
    assert build_backend._normalize_target_platform("windows") == "win32"
    assert build_backend._normalize_target_platform("win") == "win32"


def test_normalize_target_platform_rejects_unknown_value() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_backend._normalize_target_platform("plan9")

    assert "Unsupported SHAFA_BACKEND_TARGET" in str(exc_info.value)


def test_ensure_native_target_rejects_cross_platform_build(monkeypatch) -> None:
    monkeypatch.setattr(build_backend, "_host_platform", lambda: "linux")

    with pytest.raises(SystemExit) as exc_info:
        build_backend._ensure_native_target("win32")

    assert "PyInstaller builds native executables only" in str(exc_info.value)


def test_collect_package_args_includes_recursive_metadata(monkeypatch) -> None:
    pyinstaller_main = types.SimpleNamespace(run=lambda argv: None)

    def fake_collect_all(package: str):
        assert package == "inquirer"
        return [("pkg-data", "inquirer")], [("pkg-bin", ".")], ["inquirer.theme"]

    def fake_copy_metadata(package: str, *, recursive: bool = False):
        assert package == "inquirer"
        assert recursive is True
        return [("readchar.dist-info", "readchar.dist-info")]

    monkeypatch.setattr(
        build_backend,
        "_load_pyinstaller_helpers",
        lambda: (pyinstaller_main, fake_collect_all, fake_copy_metadata),
    )

    assert build_backend._collect_package_args("inquirer", recursive_metadata=True) == [
        "--add-data",
        f"pkg-data{build_backend.os.pathsep}inquirer",
        "--add-binary",
        f"pkg-bin{build_backend.os.pathsep}.",
        "--hidden-import",
        "inquirer.theme",
        "--add-data",
        f"readchar.dist-info{build_backend.os.pathsep}readchar.dist-info",
    ]


def test_load_pyinstaller_helpers_requires_build_dependency(monkeypatch) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "PyInstaller.__main__" or name.startswith("PyInstaller.utils"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(SystemExit) as exc_info:
        build_backend._load_pyinstaller_helpers()

    assert "PyInstaller is required to build the backend" in str(exc_info.value)
