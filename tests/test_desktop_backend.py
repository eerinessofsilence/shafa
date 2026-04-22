from __future__ import annotations

import importlib
import socket
import sys


def _load_desktop_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SHAFA_DESKTOP_DATA_DIR", str(tmp_path / "desktop-data"))
    sys.modules.pop("desktop_backend", None)
    return importlib.import_module("desktop_backend")


def test_resolve_backend_port_uses_configured_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_BACKEND_PORT", "8123")
    module = _load_desktop_backend(tmp_path, monkeypatch)

    port, used_fallback = module._resolve_backend_port("127.0.0.1")

    assert port == 8123
    assert used_fallback is False


def test_resolve_backend_port_falls_back_when_preferred_port_is_busy(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SHAFA_BACKEND_PORT", raising=False)
    module = _load_desktop_backend(tmp_path, monkeypatch)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_socket:
        occupied_socket.bind(("127.0.0.1", 0))
        occupied_socket.listen(1)
        occupied_port = int(occupied_socket.getsockname()[1])

        port, used_fallback = module._resolve_backend_port(
            "127.0.0.1",
            preferred_port=occupied_port,
        )

    assert used_fallback is True
    assert port != occupied_port
    assert port > 0
