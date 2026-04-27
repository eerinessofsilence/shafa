from __future__ import annotations

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
