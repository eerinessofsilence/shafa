from __future__ import annotations

import os
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


def get_settings() -> AppSettings:
    base_dir = Path(os.getenv("TELEGRAM_ACCOUNTS_BASE_DIR", Path.cwd())).resolve()
    accounts_file = Path(os.getenv("ACCOUNTS_STATE_FILE", base_dir / "accounts_state.json")).resolve()
    templates_file = Path(os.getenv("MESSAGE_TEMPLATES_FILE", base_dir / "message_templates.json")).resolve()
    channel_templates_file = Path(
        os.getenv("CHANNEL_TEMPLATES_STATE_FILE", base_dir / "telegram_channel_templates.json")
    ).resolve()
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
