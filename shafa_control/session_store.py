from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from .models import Account

PENDING_TELEGRAM_AUTH_STEPS = {
    "WAIT_PHONE",
    "WAIT_CODE",
    "WAIT_PASSWORD",
}

TELEGRAM_AUTH_STEP_ALIASES = {
    "": "INIT",
    "IDLE": "INIT",
    "INIT": "INIT",
    "WAIT_PHONE": "WAIT_PHONE",
    "WAIT_PHONE_INPUT": "WAIT_PHONE",
    "PHONE_RECEIVED": "WAIT_PHONE",
    "PHONE_SUBMITTED": "WAIT_PHONE",
    "SENDING_CODE": "WAIT_PHONE",
    "WAIT_CODE": "WAIT_CODE",
    "WAIT_CODE_INPUT": "WAIT_CODE",
    "WAITING_FOR_CODE": "WAIT_CODE",
    "AWAITING_CODE_INPUT": "WAIT_CODE",
    "CODE_RECEIVED": "WAIT_CODE",
    "VERIFYING": "WAIT_CODE",
    "VERIFYING_CODE": "WAIT_CODE",
    "WAIT_PASSWORD": "WAIT_PASSWORD",
    "PASSWORD_REQUIRED": "WAIT_PASSWORD",
    "PASSWORD_REQUESTED": "WAIT_PASSWORD",
    "SUCCESS": "SUCCESS",
    "FAILED": "FAILED",
}


class AccountSessionStore:
    def __init__(
        self,
        base_dir: Path,
        accounts_dir: Path,
        legacy_state_file: Path,
        index_file: Path | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.accounts_dir = accounts_dir
        self.legacy_state_file = legacy_state_file
        self.index_file = index_file or accounts_dir / "index.json"

    def load_accounts(self) -> list[Account]:
        raw_accounts = self._read_payload(self.index_file)
        if raw_accounts is None:
            raw_accounts = self._read_payload(self.legacy_state_file)
        if raw_accounts is None:
            return []

        accounts = [Account.from_json(item) for item in raw_accounts if item.get("path")]
        for account in accounts:
            account.status = "stopped"
            account.process = None
        return accounts

    def save_accounts(self, accounts: Iterable[Account]) -> None:
        payload = [account.to_json() for account in accounts]
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        self.index_file.write_text(rendered, encoding="utf-8")
        self.legacy_state_file.write_text(rendered, encoding="utf-8")
        for account in accounts:
            self.write_account_manifest(account)

    def write_account_manifest(self, account: Account) -> Path:
        account_dir = self.account_dir(account)
        manifest_path = account_dir / "account.json"
        manifest = {
            "id": account.id,
            "name": account.name,
            "phone_number": account.phone_number,
            "project_path": account.path,
            "branch": account.branch,
            "browser_session_path": str(self.auth_file(account)),
            "shafa_session_path": str(self.auth_file(account)),
            "browser_session_valid": self.is_valid_shafa_session(account),
            "telegram_session_path": str(self.telegram_session_file(account)),
            "telegram_session_valid": self.is_valid_telegram_session(account),
            "telegram_login_state_path": str(self.telegram_login_state_file(account)),
            "telegram_login_pending": self.has_pending_telegram_code(account),
            "telegram_channels_path": str(self.channels_file(account)),
            "logs_path": str(self.account_log_file(account)),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def account_dir(self, account: Account) -> Path:
        account_dir = self.accounts_dir / account.id
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir

    def auth_file(self, account: Account) -> Path:
        return self.account_dir(account) / "auth.json"

    def db_file(self, account: Account) -> Path:
        return self.account_dir(account) / "shafa.sqlite3"

    def telegram_session_file(self, account: Account) -> Path:
        return self.account_dir(account) / "telegram.session"

    def telegram_login_state_file(self, account: Account) -> Path:
        return self.account_dir(account) / "telegram_login_state.json"

    def channels_file(self, account: Account) -> Path:
        return self.account_dir(account) / "shafa_telegram_channels.json"

    def logs_dir(self, account: Account) -> Path:
        path = self.account_dir(account) / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def account_log_file(self, account: Account) -> Path:
        return self.logs_dir(account) / "app.log"

    def has_pending_telegram_code(self, account: Account) -> bool:
        path = self.telegram_login_state_file(account)
        if not path.exists():
            return False
        if self.is_valid_telegram_session(account):
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        step = TELEGRAM_AUTH_STEP_ALIASES.get(
            str(payload.get("current_auth_step") or "").strip().upper(),
            "INIT",
        )
        return step in PENDING_TELEGRAM_AUTH_STEPS

    def is_valid_shafa_session(self, account: Account) -> bool:
        path = self.auth_file(account)
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        cookies = payload.get("cookies")
        return isinstance(cookies, list) and bool(cookies)

    def is_valid_telegram_session(self, account: Account) -> bool:
        path = self.telegram_session_file(account)
        return self.is_valid_telegram_session_path(path)

    @staticmethod
    def is_valid_telegram_session_path(path: Path) -> bool:
        if not path.exists() or not path.is_file():
            return False
        try:
            if path.stat().st_size <= 0:
                return False
            header = path.read_bytes()[:16]
        except OSError:
            return False
        return header.startswith(b"SQLite format 3") or path.suffix == ".session"

    def delete_telegram_session(self, account: Account) -> None:
        session_file = self.telegram_session_file(account)
        session_file.unlink(missing_ok=True)
        Path(f"{session_file}-journal").unlink(missing_ok=True)
        self.telegram_login_state_file(account).unlink(missing_ok=True)
        self.write_account_manifest(account)

    def delete_shafa_session(self, account: Account) -> None:
        self.auth_file(account).unlink(missing_ok=True)
        self.write_account_manifest(account)

    def delete_account_data(self, account: Account) -> None:
        account_dir = self.accounts_dir / account.id
        if account_dir.exists():
            for child in sorted(account_dir.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            account_dir.rmdir()

    def copy_telegram_session(self, source: Account, target: Account) -> None:
        source_file = self.telegram_session_file(source)
        if not self.is_valid_telegram_session(source):
            raise RuntimeError("Source Telegram session is invalid.")
        target_file = self.telegram_session_file(target)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        source_journal = Path(f"{source_file}-journal")
        if source_journal.exists():
            shutil.copy2(source_journal, Path(f"{target_file}-journal"))
        self.write_account_manifest(target)

    def copy_shafa_session(self, source: Account, target: Account) -> None:
        if not self.is_valid_shafa_session(source):
            raise RuntimeError("Source Shafa session is invalid.")
        target_file = self.auth_file(target)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.auth_file(source), target_file)
        self.write_account_manifest(target)

    def import_telegram_session(self, account: Account, source_path: Path) -> None:
        if not self.is_valid_telegram_session_path(source_path):
            raise RuntimeError("Imported Telegram session file is invalid.")
        target_file = self.telegram_session_file(account)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_file)
        if not self.is_valid_telegram_session(account):
            target_file.unlink(missing_ok=True)
            raise RuntimeError("Imported Telegram session failed validation.")
        self.write_account_manifest(account)

    def export_telegram_session(self, account: Account, target_path: Path) -> None:
        if not self.is_valid_telegram_session(account):
            raise RuntimeError("Telegram session is missing or invalid.")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.telegram_session_file(account), target_path)

    @staticmethod
    def _read_payload(path: Path) -> list[dict] | None:
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, list):
            return None
        return raw
