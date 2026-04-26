from __future__ import annotations

import errno
import os
import shutil
import socket
import sys
from pathlib import Path

SEED_FILES = ("accounts_state.json", "telegram_channel_templates.json")
SEED_JSON_PAYLOAD = "[]\n"
DEFAULT_BACKEND_PORT = 8000
ADDRESS_IN_USE_WINERROR = 10048


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    configured = os.getenv("SHAFA_DESKTOP_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _bundle_dir()


def _bootstrap_environment() -> Path:
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "accounts").mkdir(parents=True, exist_ok=True)

    bundle_dir = _bundle_dir()
    for filename in SEED_FILES:
        source = bundle_dir / filename
        target = data_dir / filename
        if source.exists() and not target.exists():
            shutil.copyfile(source, target)
        if not target.exists():
            target.write_text(SEED_JSON_PAYLOAD, encoding="utf-8")

    os.environ.setdefault("TELEGRAM_ACCOUNTS_BASE_DIR", str(data_dir))
    os.environ.setdefault("ACCOUNTS_STATE_FILE", str(data_dir / "accounts_state.json"))
    os.environ.setdefault("MESSAGE_TEMPLATES_FILE", str(data_dir / "message_templates.json"))
    os.environ.setdefault("CHANNEL_TEMPLATES_STATE_FILE", str(data_dir / "telegram_channel_templates.json"))
    os.environ.setdefault("ACCOUNTS_DIR", str(data_dir / "accounts"))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return data_dir


def _reserve_port(host: str, port: int) -> int:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.bind((host, port))
        probe.listen(1)
        return int(probe.getsockname()[1])


def _resolve_backend_port(host: str, preferred_port: int = DEFAULT_BACKEND_PORT) -> tuple[int, bool]:
    configured_port = os.getenv("SHAFA_BACKEND_PORT", "").strip()
    if configured_port:
        return int(configured_port), False

    try:
        return _reserve_port(host, preferred_port), False
    except OSError:
        return _reserve_port(host, 0), True

DATA_DIR = _bootstrap_environment()


def _is_address_in_use_error(error: OSError) -> bool:
    if error.errno == errno.EADDRINUSE:
        return True
    if getattr(error, "winerror", None) == ADDRESS_IN_USE_WINERROR:
        return True
    return False


def main() -> None:
    import uvicorn
    from telegram_accounts_api.main import app

    host = os.getenv("SHAFA_BACKEND_HOST", "127.0.0.1")
    configured_port = os.getenv("SHAFA_BACKEND_PORT", "").strip()
    port, used_fallback_port = _resolve_backend_port(host)
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    while True:
        os.environ["SHAFA_BACKEND_PORT"] = str(port)
        if used_fallback_port:
            print(
                f"Port {DEFAULT_BACKEND_PORT} is busy on {host}; using available port {port}. "
                "Set SHAFA_BACKEND_PORT to override.",
                flush=True,
            )
        print(f"Starting desktop backend on {host}:{port} with data dir {DATA_DIR}", flush=True)

        try:
            uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=False)
            return
        except OSError as error:
            if configured_port or not _is_address_in_use_error(error):
                raise

            next_port = _reserve_port(host, 0)
            print(
                f"Port {port} became busy before startup completed; retrying on {host}:{next_port}.",
                flush=True,
            )
            port = next_port
            used_fallback_port = False


if __name__ == "__main__":
    main()
