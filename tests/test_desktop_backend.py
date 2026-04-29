from __future__ import annotations

import importlib
import sys
import types

import pytest


def _load_desktop_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SHAFA_DESKTOP_DATA_DIR", str(tmp_path / "desktop-data"))
    monkeypatch.setenv("SHAFA_RUNTIME_PROJECT_DIR", "")
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

    port, used_fallback = module._resolve_backend_port(
        "127.0.0.1",
        preferred_port=8123,
    )

    assert used_fallback is False
    assert port == 8123


def test_main_retries_with_free_port_when_default_port_is_busy(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SHAFA_BACKEND_PORT", raising=False)
    module = _load_desktop_backend(tmp_path, monkeypatch)
    expected_app = _stub_api_app(monkeypatch)
    calls: list[int] = []

    def fake_run(app, *, host: str, port: int, log_level: str, access_log: bool) -> None:
        assert app is expected_app
        assert host == "127.0.0.1"
        assert log_level == "info"
        assert access_log is False
        calls.append(port)
        if len(calls) == 1:
            error = OSError(errno := 98, "Address already in use")
            error.winerror = 10048
            raise error

    monkeypatch.setattr(module, "_reserve_port", lambda host, port: 8100)
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))

    module.main()

    assert calls == [8000, 8100]
    assert module.os.environ["SHAFA_BACKEND_PORT"] == "8100"


def test_main_strips_backend_host_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_BACKEND_HOST", "127.0.0.1 ")
    monkeypatch.setenv("SHAFA_BACKEND_PORT", "8123")
    module = _load_desktop_backend(tmp_path, monkeypatch)
    expected_app = _stub_api_app(monkeypatch)
    calls: list[tuple[str, int]] = []

    def fake_run(app, *, host: str, port: int, log_level: str, access_log: bool) -> None:
        assert app is expected_app
        calls.append((host, port))

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))

    module.main()

    assert calls == [("127.0.0.1", 8123)]


def test_main_does_not_retry_when_port_is_explicitly_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_BACKEND_PORT", "8123")
    module = _load_desktop_backend(tmp_path, monkeypatch)
    expected_app = _stub_api_app(monkeypatch)
    error = OSError(98, "Address already in use")
    error.winerror = 10048
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


def test_copy_runtime_project_sets_stable_project_under_data_dir(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_desktop_backend(tmp_path, monkeypatch)
    bundle_dir = tmp_path / "bundle"
    source_dir = bundle_dir / "shafa_logic"
    source_dir.mkdir(parents=True)
    (source_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (source_dir / "__pycache__").mkdir()
    (source_dir / "__pycache__" / "main.pyc").write_bytes(b"cache")

    runtime_root = module._copy_runtime_project(bundle_dir, tmp_path / "data")

    assert runtime_root == tmp_path / "data" / "runtime-project"
    assert (runtime_root / "shafa_logic" / "main.py").is_file()
    assert not (runtime_root / "shafa_logic" / "__pycache__").exists()


def test_copy_runtime_project_reuses_configured_runtime_dir(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_desktop_backend(tmp_path, monkeypatch)
    configured_runtime_dir = tmp_path / "existing-runtime-root"
    monkeypatch.setenv("SHAFA_RUNTIME_PROJECT_DIR", str(configured_runtime_dir))

    runtime_root = module._copy_runtime_project(tmp_path / "bundle", tmp_path / "data")

    assert runtime_root == configured_runtime_dir.resolve()


def test_embedded_shafa_cli_dispatches_main_py_command(tmp_path, monkeypatch) -> None:
    module = _load_desktop_backend(tmp_path, monkeypatch)
    project_dir = tmp_path / "runtime-project" / "shafa_logic"
    project_dir.mkdir(parents=True)
    marker_path = tmp_path / "cli-marker.txt"
    (project_dir / "main.py").write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "def parse_args():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--shafa', action='store_true')\n"
        "    parser.add_argument('--login-shafa', action='store_true')\n"
        "    parser.add_argument('--mode')\n"
        "    parser.add_argument('--telegram-send-code')\n"
        "    parser.add_argument('--telegram-login-phone')\n"
        "    parser.add_argument('--telegram-login-code')\n"
        "    parser.add_argument('--telegram-login-password')\n"
        "    parser.add_argument('--telegram-session-status', action='store_true')\n"
        "    return parser.parse_args()\n"
        "def main(**kwargs):\n"
        f"    Path({str(marker_path)!r}).write_text(\n"
        "        str(kwargs['shafa']),\n"
        "        encoding='utf-8',\n"
        "    )\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)

    exit_code = module._run_embedded_shafa_cli(["main.py", "--shafa"])

    assert exit_code == 0
    assert marker_path.read_text(encoding="utf-8") == "True"
