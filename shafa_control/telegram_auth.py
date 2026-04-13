from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
import json
import re

from .models import Account
from .session_store import AccountSessionStore

CommandRunner = Callable[[Account, list[str]], subprocess.CompletedProcess]

PHONE_PATTERN = re.compile(r"^\+?\d{8,15}$")
CODE_PATTERN = re.compile(r"^\d{5,6}$")
AUTH_STEP_ALIASES = {
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
    "SUCCESS": "SUCCESS",
    "FAILED": "FAILED",
}
PENDING_AUTH_STEPS = {
    "WAIT_PHONE",
    "WAIT_CODE",
}


@dataclass
class TelegramAuthStatus:
    ok: bool
    message: str
    pending_code: bool = False


@dataclass
class TelegramAuthRuntime:
    account_id: str
    state: str = "WAIT_PHONE"
    attempt: int = 1
    max_attempts: int = 2
    deadline: datetime | None = None
    history: list[str] = field(default_factory=list)

    def start_step(self, state: str, timeout_seconds: int = 10) -> None:
        self.state = state
        self.deadline = datetime.now() + timedelta(seconds=timeout_seconds)
        self.history.append(state)

    def transition(self, event: str) -> TelegramAuthStatus | None:
        if event == "PHONE_PROMPT":
            if self.state != "WAIT_PHONE":
                return TelegramAuthStatus(False, "Phone prompt repeated unexpectedly.")
            self.start_step("WAIT_CODE")
            return TelegramAuthStatus(True, "Phone prompt detected.", pending_code=False)
        if event == "CODE_PROMPT":
            if self.state != "WAIT_CODE":
                return TelegramAuthStatus(False, "Code prompt arrived out of sequence.")
            self.state = "AWAITING_CODE_INPUT"
            self.deadline = None
            self.history.append("AWAITING_CODE_INPUT")
            return TelegramAuthStatus(True, "Code prompt detected.", pending_code=True)
        if event == "CODE_SENT":
            if self.state != "AWAITING_CODE_INPUT":
                return TelegramAuthStatus(False, "Verification code was sent before code prompt.")
            self.start_step("VERIFYING")
            return TelegramAuthStatus(True, "Verification code sent.", pending_code=False)
        if event == "SUCCESS":
            if self.state != "VERIFYING":
                return TelegramAuthStatus(False, "Authentication completed out of sequence.")
            self.state = "SUCCESS"
            self.deadline = None
            self.history.append("SUCCESS")
            return TelegramAuthStatus(True, "Telegram authentication completed.", pending_code=False)
        if event == "ERROR":
            self.state = "FAILED"
            self.deadline = None
            self.history.append("FAILED")
            return TelegramAuthStatus(False, "Telegram authentication failed.")
        return None

    def timeout_status(self) -> TelegramAuthStatus | None:
        if self.deadline is None or datetime.now() <= self.deadline:
            return None
        current_state = self.state
        mapping = {
            "WAIT_PHONE": "Timed out waiting for phone prompt.",
            "WAIT_CODE": "Timed out waiting for code prompt.",
            "VERIFYING": "Timed out waiting for authentication success.",
        }
        self.state = "FAILED"
        self.history.append("FAILED")
        self.deadline = None
        return TelegramAuthStatus(False, mapping.get(current_state, "Timed out during Telegram authentication."))

    def can_retry(self) -> bool:
        return self.attempt < self.max_attempts

    def next_attempt(self) -> None:
        self.attempt += 1
        self.state = "WAIT_PHONE"
        self.deadline = datetime.now() + timedelta(seconds=10)
        self.history.append(f"RETRY_{self.attempt}")


class TelegramAuthService:
    def __init__(
        self,
        store: AccountSessionStore,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.runner = runner

    def request_code(self, account: Account) -> TelegramAuthStatus:
        phone_status = self.validate_phone(account.phone_number)
        if not phone_status.ok:
            return phone_status

        result = self.runner(account, ["main.py", "--telegram-send-code", phone_status.message])
        if result.returncode != 0:
            return TelegramAuthStatus(False, self._command_error(result))
        return TelegramAuthStatus(True, "Telegram code requested.", pending_code=True)

    def submit_code(self, account: Account, code: str) -> TelegramAuthStatus:
        phone_status = self.validate_phone(account.phone_number)
        code_status = self.validate_code(code)
        if not phone_status.ok:
            return phone_status
        if not code_status.ok:
            return code_status

        result = self.runner(
            account,
            [
                "main.py",
                "--telegram-login-phone",
                phone_status.message,
                "--telegram-login-code",
                code_status.message,
            ],
        )
        if result.returncode != 0:
            return TelegramAuthStatus(False, self._command_error(result))
        return TelegramAuthStatus(True, "Telegram session saved.", pending_code=False)

    def has_pending_code(self, account: Account) -> bool:
        return self.store.has_pending_telegram_code(account)

    def interactive_command(self) -> list[str]:
        return ["main.py", "--telegram-auth-interactive"]

    def reuse_status(self, account: Account) -> TelegramAuthStatus | None:
        if self.store.is_valid_telegram_session(account):
            return TelegramAuthStatus(True, "Reusing existing Telegram session.", pending_code=False)
        return None

    def create_runtime(self, account: Account, attempt: int = 1) -> TelegramAuthRuntime:
        runtime = TelegramAuthRuntime(account_id=account.id, attempt=attempt)
        runtime.start_step("WAIT_PHONE")
        return runtime

    def auth_state_path(self, account: Account) -> Path:
        return self.store.telegram_login_state_file(account)

    def load_auth_state(self, account: Account) -> dict:
        path = self.auth_state_path(account)
        if not path.exists():
            return self._default_auth_state(account)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default_auth_state(account)
        return {
            "phone_number": str(payload.get("phone_number") or payload.get("phone") or account.phone_number or "").strip(),
            "verification_code": str(payload.get("verification_code") or "").strip(),
            "telegram_password": str(payload.get("telegram_password") or account.telegram_password or "").strip(),
            "current_auth_step": self.normalize_auth_step(payload.get("current_auth_step")),
            "phone_code_hash": str(payload.get("phone_code_hash") or "").strip(),
            "code_confirmed": bool(payload.get("code_confirmed", False)),
        }

    def persist_auth_state(
        self,
        account: Account,
        *,
        phone_number: str | None = None,
        verification_code: str | None = None,
        telegram_password: str | None = None,
        current_auth_step: str | None = None,
        code_confirmed: bool | None = None,
        extra: dict | None = None,
    ) -> dict:
        state = self.load_auth_state(account)
        if phone_number is not None:
            state["phone_number"] = str(phone_number).strip()
        if verification_code is not None:
            state["verification_code"] = str(verification_code).strip()
        if telegram_password is not None:
            state["telegram_password"] = str(telegram_password).strip()
        if current_auth_step is not None:
            state["current_auth_step"] = self.normalize_auth_step(current_auth_step)
        if code_confirmed is not None:
            state["code_confirmed"] = bool(code_confirmed)
        if extra:
            for key, value in extra.items():
                state[key] = value
        path = self.auth_state_path(account)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    def clear_auth_state(self, account: Account) -> None:
        self.auth_state_path(account).unlink(missing_ok=True)

    @staticmethod
    def validate_phone(phone: str) -> TelegramAuthStatus:
        clean_phone = TelegramAuthService.normalize_phone(phone)
        if not clean_phone:
            return TelegramAuthStatus(False, "Phone number is required for Telegram login")
        if not PHONE_PATTERN.fullmatch(clean_phone):
            return TelegramAuthStatus(False, "Phone number is required for Telegram login")
        return TelegramAuthStatus(True, clean_phone)

    @staticmethod
    def validate_code(code: str) -> TelegramAuthStatus:
        clean_code = str(code or "").strip()
        if not clean_code:
            return TelegramAuthStatus(False, "Verification code must be 5 or 6 digits.")
        if not CODE_PATTERN.fullmatch(clean_code):
            return TelegramAuthStatus(False, "Verification code must be 5 or 6 digits.")
        return TelegramAuthStatus(True, clean_code)

    @staticmethod
    def validate_password(password: str) -> TelegramAuthStatus:
        clean_password = str(password or "").strip()
        if not clean_password:
            return TelegramAuthStatus(False, "Telegram password is required.")
        return TelegramAuthStatus(True, clean_password)

    @staticmethod
    def normalize_phone(phone: str) -> str:
        raw_phone = str(phone or "").strip()
        if not raw_phone or raw_phone.casefold() in {"+380...", "phone", "none", "null"}:
            return ""
        normalized = re.sub(r"[\s()-]+", "", raw_phone)
        if normalized.count("+") > 1 or ("+" in normalized and not normalized.startswith("+")):
            return ""
        return normalized

    @classmethod
    def is_pending_auth_step(cls, step: str) -> bool:
        clean_step = cls.normalize_auth_step(step)
        return clean_step in PENDING_AUTH_STEPS

    @staticmethod
    def normalize_auth_step(step: str | None) -> str:
        clean_step = str(step or "").strip().upper()
        return AUTH_STEP_ALIASES.get(clean_step, "INIT")

    @staticmethod
    def _default_auth_state(account: Account) -> dict:
        return {
            "phone_number": str(account.phone_number or "").strip(),
            "verification_code": "",
            "telegram_password": str(account.telegram_password or "").strip(),
            "current_auth_step": "INIT",
            "phone_code_hash": "",
            "code_confirmed": False,
        }

    def import_session(self, account: Account, source_path: Path) -> None:
        self.store.import_telegram_session(account, source_path)

    def export_session(self, account: Account, target_path: Path) -> None:
        self.store.export_telegram_session(account, target_path)

    def copy_session(self, source: Account, target: Account) -> None:
        self.store.copy_telegram_session(source, target)

    @staticmethod
    def _command_error(result: subprocess.CompletedProcess) -> str:
        return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
