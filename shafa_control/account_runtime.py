from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from telegram_channels import export_runtime_config

from .models import Account
from .session_store import AccountSessionStore


def project_main_path(project_dir: Path) -> Path:
    return project_dir / "main.py"


def is_runnable_project_dir(project_dir: Path) -> bool:
    return project_dir.is_dir() and project_main_path(project_dir).is_file()


def preferred_project_dir(project_dir: Path) -> Path:
    shafa_logic_dir = project_dir / "shafa_logic"
    if is_runnable_project_dir(shafa_logic_dir):
        return shafa_logic_dir
    return project_dir


def project_root_dir(project_dir: Path) -> Path:
    preferred = preferred_project_dir(project_dir)
    if preferred.name == "shafa_logic":
        return preferred.parent
    return preferred


def nested_runnable_project_dir(project_dir: Path) -> Path | None:
    if not project_dir.is_dir():
        return None
    candidates = [child for child in project_dir.iterdir() if child.is_dir() and is_runnable_project_dir(child)]
    if len(candidates) == 1:
        return candidates[0]
    return None


def read_env_file(path: Path) -> dict[str, str]:
    credentials = {
        "SHAFA_TELEGRAM_API_ID": "",
        "SHAFA_TELEGRAM_API_HASH": "",
    }
    if not path.exists():
        return credentials
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return credentials
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in credentials:
            credentials[key] = value.strip().strip("\"'")
    return credentials


class AccountRuntimeService:
    def __init__(self, store: AccountSessionStore) -> None:
        self.store = store

    @staticmethod
    def root_env_path() -> Path:
        return Path(__file__).resolve().parents[1] / ".env"

    def state_dir(self, account: Account) -> Path:
        return self.store.account_dir(account)

    def account_env(
        self,
        account: Account,
        *,
        app_mode: str | None = None,
        base_env: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        env = dict(base_env) if base_env is not None else os.environ.copy()
        state_dir = self.state_dir(account)
        project_path = preferred_project_dir(Path(account.path).expanduser())
        telegram_credentials = self.store.load_telegram_credentials(account)
        root_credentials = read_env_file(self.root_env_path())
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["SHAFA_ACCOUNT_STATE_DIR"] = str(state_dir)
        env["SHAFA_STORAGE_STATE_PATH"] = str(self.store.auth_file(account))
        env["SHAFA_DB_PATH"] = str(self.store.db_file(account))
        env["SHAFA_TELEGRAM_SESSION_PATH"] = str(self.store.telegram_session_file(account))
        env["SHAFA_TELEGRAM_LOGIN_STATE_PATH"] = str(self.store.telegram_login_state_file(account))
        env["SHAFA_TELEGRAM_CHANNELS_PATH"] = str(self.store.channels_file(account))
        api_id = (
            telegram_credentials.get("SHAFA_TELEGRAM_API_ID", "").strip()
            or root_credentials.get("SHAFA_TELEGRAM_API_ID", "").strip()
            or str(env.get("SHAFA_TELEGRAM_API_ID", "")).strip()
        )
        api_hash = (
            telegram_credentials.get("SHAFA_TELEGRAM_API_HASH", "").strip()
            or root_credentials.get("SHAFA_TELEGRAM_API_HASH", "").strip()
            or str(env.get("SHAFA_TELEGRAM_API_HASH", "")).strip()
        )
        if api_id:
            env["SHAFA_TELEGRAM_API_ID"] = api_id
        else:
            env.pop("SHAFA_TELEGRAM_API_ID", None)
        if api_hash:
            env["SHAFA_TELEGRAM_API_HASH"] = api_hash
        else:
            env.pop("SHAFA_TELEGRAM_API_HASH", None)
        if app_mode:
            env["SHAFA_APP_MODE"] = str(app_mode).strip()
        return env

    def account_python(self, account: Account) -> str:
        project_path = preferred_project_dir(Path(account.path).expanduser())
        if os.name == "nt":
            candidate = project_path / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = project_path / ".venv" / "bin" / "python"
        return str(candidate if candidate.exists() else Path(sys.executable))

    def run_account_command(
        self,
        account: Account,
        args: list[str],
        *,
        app_mode: str | None = None,
        base_env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        project_path = preferred_project_dir(Path(account.path).expanduser())
        if not project_main_path(project_path).is_file():
            return subprocess.CompletedProcess(
                [self.account_python(account), *args],
                1,
                stdout="",
                stderr=f"main.py not found at {project_path}",
            )
        return subprocess.run(
            [self.account_python(account), *args],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            env=self.account_env(account, app_mode=app_mode, base_env=base_env),
        )

    def export_channel_runtime_config(self, account: Account) -> Path:
        return export_runtime_config(
            account_name=account.name,
            account_path=str(preferred_project_dir(Path(account.path).expanduser())),
            links=account.channel_links,
            output_dir=self.state_dir(account),
        )
