from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    base_dir: Path
    accounts_file: Path
    templates_file: Path
    channel_templates_file: Path
    accounts_dir: Path
    log_level: str
    app_name: str = "Telegram Accounts API"
    app_version: str = "1.0.0"


def _default_base_dir() -> Path:
    configured = os.getenv("TELEGRAM_ACCOUNTS_BASE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    desktop_data_dir = os.getenv("SHAFA_DESKTOP_DATA_DIR", "").strip()
    if desktop_data_dir:
        return Path(desktop_data_dir).expanduser().resolve()

    return Path(__file__).resolve().parents[2]


def get_settings() -> AppSettings:
    base_dir = _default_base_dir()
    accounts_file = Path(os.getenv("ACCOUNTS_STATE_FILE", base_dir / "accounts_state.json")).resolve()
    templates_file = Path(os.getenv("MESSAGE_TEMPLATES_FILE", base_dir / "message_templates.json")).resolve()
    configured_channel_templates_file = os.getenv("CHANNEL_TEMPLATES_STATE_FILE", "").strip()
    if configured_channel_templates_file:
        channel_templates_file = Path(configured_channel_templates_file).expanduser().resolve()
    else:
        channel_templates_file = (base_dir / "telegram_templates" / "channel_templates.json").resolve()
        legacy_channel_templates_file = (base_dir / "telegram_channel_templates.json").resolve()
        if legacy_channel_templates_file.exists() and not channel_templates_file.exists():
            channel_templates_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_channel_templates_file, channel_templates_file)
    accounts_dir = Path(os.getenv("ACCOUNTS_DIR", base_dir / "accounts")).resolve()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    return AppSettings(
        base_dir=base_dir,
        accounts_file=accounts_file,
        templates_file=templates_file,
        channel_templates_file=channel_templates_file,
        accounts_dir=accounts_dir,
        log_level=log_level,
    )


settings = get_settings()
