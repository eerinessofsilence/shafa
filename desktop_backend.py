from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import uvicorn

SEED_FILES = ("accounts_state.json", "telegram_channel_templates.json")


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

    os.environ.setdefault("TELEGRAM_ACCOUNTS_BASE_DIR", str(data_dir))
    os.environ.setdefault("ACCOUNTS_STATE_FILE", str(data_dir / "accounts_state.json"))
    os.environ.setdefault("MESSAGE_TEMPLATES_FILE", str(data_dir / "message_templates.json"))
    os.environ.setdefault("CHANNEL_TEMPLATES_STATE_FILE", str(data_dir / "telegram_channel_templates.json"))
    os.environ.setdefault("ACCOUNTS_DIR", str(data_dir / "accounts"))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return data_dir


DATA_DIR = _bootstrap_environment()

from telegram_accounts_api.main import app


def main() -> None:
    host = os.getenv("SHAFA_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("SHAFA_BACKEND_PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    print(f"Starting desktop backend on {host}:{port} with data dir {DATA_DIR}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=False)


if __name__ == "__main__":
    main()
