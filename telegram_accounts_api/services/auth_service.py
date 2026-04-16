from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from shafa_control import Account, AccountSessionStore, ShafaAuthService, TelegramAuthService

from telegram_accounts_api.models.auth import (
    ShafaAuthStatusResponse,
    ShafaStorageStateRequest,
    TelegramAuthStatusResponse,
    TelegramCodeRequest,
    TelegramCredentialsRequest,
    TelegramPasswordRequest,
    TelegramPhoneRequest,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.exceptions import BadRequestError, TelegramOperationError


def _project_main_path(project_dir: Path) -> Path:
    return project_dir / "main.py"


def _preferred_project_dir(project_dir: Path) -> Path:
    shafa_logic_dir = project_dir / "shafa_logic"
    if shafa_logic_dir.is_dir() and _project_main_path(shafa_logic_dir).is_file():
        return shafa_logic_dir
    return project_dir


class AccountAuthService:
    def __init__(
        self,
        account_service: AccountService,
        store: AccountSessionStore,
        runner=None,
    ) -> None:
        self.account_service = account_service
        self.store = store
        self.runner = runner or self._run_account_command
        self.telegram_auth = TelegramAuthService(store, self.runner)
        self.shafa_auth = ShafaAuthService(store)

    async def get_telegram_status(self, account_id: str) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        state = self.telegram_auth.load_auth_state(account)
        current_step = self.telegram_auth.normalize_auth_step(state.get("current_auth_step"))
        connected = self.store.is_valid_telegram_session(account)
        if connected:
            current_step = "SUCCESS"
        return TelegramAuthStatusResponse(
            account_id=account.id,
            connected=connected,
            has_api_credentials=self.store.has_telegram_credentials(account),
            current_step=current_step,
            next_step=self._next_telegram_step(current_step, connected),
            phone_number=str(state.get("phone_number") or account.phone_number or "").strip(),
            message=self._telegram_status_message(current_step, connected),
        )

    async def save_telegram_credentials(
        self,
        account_id: str,
        payload: TelegramCredentialsRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        api_id = str(payload.api_id or "").strip()
        api_hash = str(payload.api_hash or "").strip()
        if not api_id.isdigit():
            raise BadRequestError("Telegram API ID must be an integer.")
        if not api_hash:
            raise BadRequestError("Telegram API hash is required.")
        self.store.save_telegram_credentials(account, api_id, api_hash)
        return await self.get_telegram_status(account_id)

    async def request_telegram_code(
        self,
        account_id: str,
        payload: TelegramPhoneRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        phone_status = self.telegram_auth.validate_phone(payload.phone)
        if not phone_status.ok:
            raise BadRequestError(phone_status.message)
        runtime_account = self._with_phone(account, phone_status.message)
        self.telegram_auth.persist_auth_state(
            runtime_account,
            phone_number=phone_status.message,
            verification_code="",
            telegram_password="",
            current_auth_step="WAIT_PHONE",
            session_path=str(self.store.telegram_session_file(runtime_account)),
            code_confirmed=False,
        )
        result = self.telegram_auth.request_code(runtime_account)
        if not result.ok:
            raise TelegramOperationError(result.message)
        return await self.get_telegram_status(account_id)

    async def submit_telegram_code(
        self,
        account_id: str,
        payload: TelegramCodeRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        state = self.telegram_auth.load_auth_state(account)
        phone = str(state.get("phone_number") or account.phone_number or "").strip()
        runtime_account = self._with_phone(account, phone)
        result = self.telegram_auth.submit_code(runtime_account, payload.code)
        if not result.ok:
            raise TelegramOperationError(result.message)
        return await self.get_telegram_status(account_id)

    async def submit_telegram_password(
        self,
        account_id: str,
        payload: TelegramPasswordRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        result = self.telegram_auth.submit_password(account, payload.password)
        if not result.ok:
            raise TelegramOperationError(result.message)
        return await self.get_telegram_status(account_id)

    async def get_shafa_status(self, account_id: str) -> ShafaAuthStatusResponse:
        account = await self._get_account(account_id)
        auth_path = self.store.auth_file(account)
        cookies_count = 0
        if auth_path.exists():
            try:
                payload = json.loads(auth_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            cookies = payload.get("cookies")
            if isinstance(cookies, list):
                cookies_count = len(cookies)
        connected = self.store.is_valid_shafa_session(account)
        return ShafaAuthStatusResponse(
            account_id=account.id,
            connected=connected,
            cookies_count=cookies_count,
            message="Shafa cookies are ready." if connected else "Shafa cookies are missing or invalid.",
        )

    async def save_shafa_storage_state(
        self,
        account_id: str,
        payload: ShafaStorageStateRequest,
    ) -> ShafaAuthStatusResponse:
        account = await self._get_account(account_id)
        storage_state = self._normalize_storage_state(payload)
        auth_path = self.store.auth_file(account)
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")
        if not self.store.is_valid_shafa_session(account):
            auth_path.unlink(missing_ok=True)
            raise BadRequestError("Shafa cookies must include a non-empty csrftoken for shafa.ua.")
        self.store.write_account_manifest(account)
        return await self.get_shafa_status(account_id)

    async def _get_account(self, account_id: str) -> Account:
        account = await self.account_service.get_account(account_id)
        return Account(
            id=account.id,
            name=account.name,
            path=account.path,
            phone_number=account.phone,
            branch=account.branch,
            open_browser=account.open_browser,
            timer_minutes=account.timer_minutes,
            channel_links=account.channel_links,
            status=account.status,
            last_run=account.last_run or "—",
            errors=account.errors,
        )

    @staticmethod
    def _with_phone(account: Account, phone: str) -> Account:
        return Account(
            id=account.id,
            name=account.name,
            path=account.path,
            phone_number=phone,
            telegram_password=account.telegram_password,
            branch=account.branch,
            open_browser=account.open_browser,
            timer_minutes=account.timer_minutes,
            channel_links=list(account.channel_links),
            status=account.status,
            last_run=account.last_run,
            errors=account.errors,
        )

    def _account_env(self, account: Account) -> dict[str, str]:
        env = os.environ.copy()
        state_dir = self.store.account_dir(account)
        telegram_credentials = self.store.load_telegram_credentials(account)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["SHAFA_ACCOUNT_STATE_DIR"] = str(state_dir)
        env["SHAFA_STORAGE_STATE_PATH"] = str(self.store.auth_file(account))
        env["SHAFA_DB_PATH"] = str(self.store.db_file(account))
        env["SHAFA_TELEGRAM_SESSION_PATH"] = str(self.store.telegram_session_file(account))
        env["SHAFA_TELEGRAM_LOGIN_STATE_PATH"] = str(self.store.telegram_login_state_file(account))
        env["SHAFA_TELEGRAM_CHANNELS_PATH"] = str(self.store.channels_file(account))
        api_id = telegram_credentials.get("SHAFA_TELEGRAM_API_ID", "").strip()
        api_hash = telegram_credentials.get("SHAFA_TELEGRAM_API_HASH", "").strip()
        if api_id:
            env["SHAFA_TELEGRAM_API_ID"] = api_id
        else:
            env.pop("SHAFA_TELEGRAM_API_ID", None)
        if api_hash:
            env["SHAFA_TELEGRAM_API_HASH"] = api_hash
        else:
            env.pop("SHAFA_TELEGRAM_API_HASH", None)
        return env

    def _account_python(self, account: Account) -> str:
        project_path = _preferred_project_dir(Path(account.path).expanduser())
        if os.name == "nt":
            candidate = project_path / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = project_path / ".venv" / "bin" / "python"
        return str(candidate if candidate.exists() else Path(sys.executable))

    def _run_account_command(self, account: Account, args: list[str]) -> subprocess.CompletedProcess:
        project_path = _preferred_project_dir(Path(account.path).expanduser())
        if not _project_main_path(project_path).is_file():
            return subprocess.CompletedProcess(
                [self._account_python(account), *args],
                1,
                stdout="",
                stderr=f"main.py not found at {project_path}",
            )
        return subprocess.run(
            [self._account_python(account), *args],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            env=self._account_env(account),
        )

    @staticmethod
    def _normalize_storage_state(payload: ShafaStorageStateRequest) -> dict[str, Any]:
        if payload.storage_state is not None:
            storage_state = dict(payload.storage_state)
            cookies = storage_state.get("cookies")
            if not isinstance(cookies, list):
                raise BadRequestError("storage_state.cookies must be a list.")
            storage_state["cookies"] = [AccountAuthService._normalize_cookie(cookie) for cookie in cookies]
            origins = storage_state.get("origins")
            storage_state["origins"] = origins if isinstance(origins, list) else []
            return storage_state
        return {
            "cookies": [AccountAuthService._normalize_cookie(cookie.model_dump()) for cookie in payload.cookies],
            "origins": list(payload.origins),
        }

    @staticmethod
    def _normalize_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(cookie)
        normalized["name"] = str(normalized.get("name") or "").strip()
        normalized["value"] = str(normalized.get("value") or "")
        domain = str(normalized.get("domain") or "").strip() or ".shafa.ua"
        normalized["domain"] = domain
        normalized["path"] = str(normalized.get("path") or "/").strip() or "/"
        if "httpOnly" in normalized:
            normalized["httpOnly"] = bool(normalized["httpOnly"])
        if "secure" in normalized:
            normalized["secure"] = bool(normalized["secure"])
        if normalized.get("sameSite") is None:
            normalized.pop("sameSite", None)
        return normalized

    @staticmethod
    def _next_telegram_step(current_step: str, connected: bool) -> str | None:
        if connected or current_step == "SUCCESS":
            return None
        if current_step in {"INIT", "WAIT_PHONE"}:
            return "CODE"
        if current_step == "WAIT_CODE":
            return "PASSWORD_OR_FINISH"
        if current_step == "WAIT_PASSWORD":
            return "FINISH"
        return "PHONE"

    @staticmethod
    def _telegram_status_message(current_step: str, connected: bool) -> str:
        if connected:
            return "Telegram session is ready."
        messages = {
            "INIT": "Telegram login has not started.",
            "WAIT_PHONE": "Phone number accepted. Verification code is being requested.",
            "WAIT_CODE": "Enter the Telegram verification code.",
            "WAIT_PASSWORD": "Enter the Telegram 2FA password.",
            "FAILED": "Telegram login failed. Request a new code and try again.",
            "SUCCESS": "Telegram session is ready.",
        }
        return messages.get(current_step, "Telegram login status is unknown.")
