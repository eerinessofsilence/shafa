from __future__ import annotations

import importlib
import sys
import types

import pytest


def _load_desktop_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SHAFA_DESKTOP_DATA_DIR", str(tmp_path / "desktop-data"))
    sys.modules.pop("desktop_backend", None)
    return importlib.import_module("desktop_backend")


def _stub_api_app(monkeypatch) -> object:
    app = object()
    monkeypatch.setitem(sys.modules, "telegram_accounts_api.main", types.SimpleNamespace(app=app))
    return app


def test_resolve_backend_port_uses_configured_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_BACKEND_PORT", "8123")
    module = _load_desktop_backend(tmp_path, monkeypatch)

    port, used_fallback = module._resolve_backend_port("127.0.0.1")

    assert port == 8123
    assert used_fallback is False


def test_resolve_backend_port_falls_back_when_preferred_port_is_busy(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SHAFA_BACKEND_PORT", raising=False)
    module = _load_desktop_backend(tmp_path, monkeypatch)

    def fake_reserve_port(host: str, port: int) -> int:
        assert host == "127.0.0.1"
        if port == 8123:
            raise OSError(98, "Address already in use")
        assert port == 0
        return 9001

    monkeypatch.setattr(module, "_reserve_port", fake_reserve_port)

    port, used_fallback = module._resolve_backend_port(
        "127.0.0.1",
        preferred_port=8123,
    )

    assert used_fallback is True
    assert port == 9001


def test_main_retries_with_free_port_when_bind_races(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SHAFA_BACKEND_PORT", raising=False)
    module = _load_desktop_backend(tmp_path, monkeypatch)
    expected_app = _stub_api_app(monkeypatch)

    calls: list[int] = []

    def fake_resolve_backend_port(host: str, preferred_port: int = 8000) -> tuple[int, bool]:
        assert host == "127.0.0.1"
        assert preferred_port == 8000
        return 8000, False

    def fake_reserve_port(host: str, port: int) -> int:
        assert host == "127.0.0.1"
        assert port == 0
        return 8100

    def fake_run(app, *, host: str, port: int, log_level: str, access_log: bool) -> None:
        assert app is expected_app
        assert host == "127.0.0.1"
        assert log_level == "info"
        assert access_log is False
        calls.append(port)
        if len(calls) == 1:
            raise OSError(98, "Address already in use")

    monkeypatch.setattr(module, "_resolve_backend_port", fake_resolve_backend_port)
    monkeypatch.setattr(module, "_reserve_port", fake_reserve_port)
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))

    module.main()

    assert calls == [8000, 8100]
    assert module.os.environ["SHAFA_BACKEND_PORT"] == "8100"


def test_main_does_not_retry_when_port_is_explicitly_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_BACKEND_PORT", "8123")
    module = _load_desktop_backend(tmp_path, monkeypatch)
    expected_app = _stub_api_app(monkeypatch)
    error = OSError(98, "Address already in use")
    calls: list[int] = []

    def fake_run(app, *, host: str, port: int, log_level: str, access_log: bool) -> None:
        assert app is expected_app
        calls.append(port)
        raise error

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))

    with pytest.raises(OSError) as exc_info:
        module.main()

    assert exc_info.value is error
    assert calls == [8123]
