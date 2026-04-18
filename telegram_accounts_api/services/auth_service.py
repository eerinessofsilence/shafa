from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from shafa_control import (
    Account,
    AccountRuntimeService,
    AccountSessionStore,
    ShafaAuthService,
    TelegramAuthService,
    preferred_project_dir,
    project_main_path,
)

from telegram_accounts_api.models.auth import (
    ShafaAuthStatusResponse,
    ShafaStorageStateRequest,
    TelegramAuthStatusResponse,
    TelegramCodeRequest,
    TelegramCredentialsRequest,
    TelegramPasswordRequest,
    TelegramPhoneRequest,
    TelegramSessionCopyRequest,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.account_logging import log
from telegram_accounts_api.utils.exceptions import BadRequestError, TelegramOperationError


def _project_main_path(project_dir: Path) -> Path:
    return project_dir / "main.py"


def _preferred_project_dir(project_dir: Path) -> Path:
    shafa_logic_dir = project_dir / "shafa_logic"
    if shafa_logic_dir.is_dir() and _project_main_path(shafa_logic_dir).is_file():
        return shafa_logic_dir
    return project_dir


def _project_data_dir(project_dir: Path) -> Path:
    preferred = _preferred_project_dir(project_dir)
    if preferred.name == "shafa_logic":
        return preferred.parent / "data"
    return preferred / "data"


class AccountAuthService:
    def __init__(
        self,
        account_service: AccountService,
        store: AccountSessionStore,
        runner=None,
        shafa_login_launcher=None,
    ) -> None:
        self.account_service = account_service
        self.store = store
        self.runner = runner or self._run_account_command
        self.shafa_login_launcher = shafa_login_launcher or self._launch_shafa_login
        self.telegram_auth = TelegramAuthService(store, self.runner)
        self.shafa_auth = ShafaAuthService(store)
        self.runtime = AccountRuntimeService(store)


    async def get_telegram_status(self, account_id: str) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        state = self.telegram_auth.load_auth_state(account)
        current_step = self.telegram_auth.normalize_auth_step(state.get("current_auth_step"))
        has_active_login = current_step in {"WAIT_PHONE", "WAIT_CODE", "WAIT_PASSWORD"}
        connected = self.store.is_valid_telegram_session(account) and not has_active_login
        if connected:
            current_step = "SUCCESS"
        return TelegramAuthStatusResponse(
            account_id=account.id,
            connected=connected,
            has_api_credentials=self._has_telegram_credentials(account),
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
            log(account_id, "WARNING", "Rejected Telegram credentials: invalid API ID.")
            raise BadRequestError("Telegram API ID must be an integer.")
        if not api_hash:
            log(account_id, "WARNING", "Rejected Telegram credentials: API hash missing.")
            raise BadRequestError("Telegram API hash is required.")
        self.store.save_telegram_credentials(account, api_id, api_hash)
        log(account_id, "INFO", "Telegram API credentials saved.")
        return await self.get_telegram_status(account_id)

    async def request_telegram_code(
        self,
        account_id: str,
        payload: TelegramPhoneRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        log(account_id, "INFO", "Starting Telegram login: requesting verification code.")
        try:
            if not self._has_telegram_credentials(account):
                log(account_id, "WARNING", "Telegram code request blocked: credentials are missing.")
                raise BadRequestError(
                    "Telegram API credentials are missing on backend. "
                    "Set SHAFA_TELEGRAM_API_ID and SHAFA_TELEGRAM_API_HASH in .env or environment.",
                )
            reuse_status = self.telegram_auth.reuse_status(account)
            if reuse_status is not None:
                log(account_id, "INFO", "Telegram login already has an active pending step.")
                return await self.get_telegram_status(account_id)
            phone_status = self.telegram_auth.validate_phone(payload.phone)
            if not phone_status.ok:
                log(account_id, "WARNING", f"Rejected Telegram phone number: {phone_status.message}")
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
                log(account_id, "ERROR", f"Telegram verification code request failed: {result.message}")
                raise TelegramOperationError(result.message)
            log(account_id, "INFO", "Telegram verification code requested.")
            return await self.get_telegram_status(account_id)
        except (BadRequestError, TelegramOperationError):
            raise
        except Exception as exc:
            log(account_id, "ERROR", f"Unexpected Telegram code request failure: {exc}")
            raise

    async def submit_telegram_code(
        self,
        account_id: str,
        payload: TelegramCodeRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        log(account_id, "INFO", "Submitting Telegram verification code.")
        try:
            state = self.telegram_auth.load_auth_state(account)
            phone = str(state.get("phone_number") or account.phone_number or "").strip()
            runtime_account = self._with_phone(account, phone)
            result = self.telegram_auth.submit_code(runtime_account, payload.code)
            if not result.ok:
                log(account_id, "ERROR", f"Telegram code submission failed: {result.message}")
                raise TelegramOperationError(result.message)
            log(account_id, "INFO", "Telegram verification code accepted.")
            return await self.get_telegram_status(account_id)
        except TelegramOperationError:
            raise
        except Exception as exc:
            log(account_id, "ERROR", f"Unexpected Telegram code submission failure: {exc}")
            raise

    async def submit_telegram_password(
        self,
        account_id: str,
        payload: TelegramPasswordRequest,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        log(account_id, "INFO", "Submitting Telegram 2FA password.")
        try:
            result = self.telegram_auth.submit_password(account, payload.password)
            if not result.ok:
                log(account_id, "ERROR", f"Telegram password submission failed: {result.message}")
                raise TelegramOperationError(result.message)
            log(account_id, "INFO", "Telegram login completed successfully.")
            return await self.get_telegram_status(account_id)
        except TelegramOperationError:
            raise
        except Exception as exc:
            log(account_id, "ERROR", f"Unexpected Telegram password submission failure: {exc}")
            raise

    async def logout_telegram(self, account_id: str) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        state = self.telegram_auth.load_auth_state(account)
        phone_number = str(state.get("phone_number") or account.phone_number or "").strip()
        self.store.delete_telegram_session(account)
        self.telegram_auth.persist_auth_state(
            self._with_phone(account, phone_number) if phone_number else account,
            phone_number=phone_number,
            verification_code="",
            telegram_password="",
            current_auth_step="INIT",
            session_path=str(self.store.telegram_session_file(account)),
            code_confirmed=False,
            extra={"phone_code_hash": ""},
        )
        status = await self.get_telegram_status(account_id)
        log(account_id, "INFO", "Telegram session removed.")
        return status.model_copy(update={"message": "Telegram session removed."})

    async def copy_telegram_session(
        self,
        account_id: str,
        payload: TelegramSessionCopyRequest,
    ) -> TelegramAuthStatusResponse:
        target = await self._get_account(account_id)
        source_account_id = str(payload.source_account_id or "").strip()
        if not source_account_id:
            raise BadRequestError("Source account ID is required.")
        if source_account_id == account_id:
            raise BadRequestError("Source and target accounts must be different.")
        source = await self._get_account(source_account_id)
        try:
            self.telegram_auth.copy_session(source, target)
        except RuntimeError as exc:
            log(
                account_id,
                "WARNING",
                f"Telegram session copy failed from '{source_account_id}': {exc}",
            )
            raise BadRequestError(str(exc)) from exc

        source_state = self.telegram_auth.load_auth_state(source)
        phone_number = str(
            source_state.get("phone_number")
            or source.phone_number
            or ""
        ).strip()
        self.telegram_auth.persist_auth_state(
            target,
            phone_number=phone_number,
            verification_code="",
            telegram_password="",
            current_auth_step="SUCCESS",
            session_path=str(self.store.telegram_session_file(target)),
            code_confirmed=False,
            extra={"phone_code_hash": ""},
        )
        self.store.write_account_manifest(target)
        log(
            account_id,
            "INFO",
            f"Telegram session copied from account '{source_account_id}'.",
        )
        return (await self.get_telegram_status(account_id)).model_copy(
            update={"message": f"Telegram session copied from account '{source_account_id}'."}
        )

    async def import_telegram_session(
        self,
        account_id: str,
        file: UploadFile,
    ) -> TelegramAuthStatusResponse:
        account = await self._get_account(account_id)
        filename = Path(file.filename or "telegram.session").name or "telegram.session"
        temp_path: Path | None = None
        try:
            suffix = Path(filename).suffix or ".session"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    temp_file.write(chunk)
                temp_path = Path(temp_file.name)

            if temp_path.stat().st_size <= 0:
                log(account_id, "WARNING", "Telegram session import rejected: file is empty.")
                raise BadRequestError("Telegram session file is empty.")

            self.telegram_auth.import_session(account, temp_path)
        except RuntimeError as exc:
            log(
                account_id,
                "WARNING",
                f"Telegram session import failed from '{filename}': {exc}",
            )
            raise BadRequestError(str(exc)) from exc
        finally:
            await file.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        state = self.telegram_auth.load_auth_state(account)
        phone_number = str(state.get("phone_number") or account.phone_number or "").strip()
        self.telegram_auth.persist_auth_state(
            self._with_phone(account, phone_number) if phone_number else account,
            phone_number=phone_number,
            verification_code="",
            telegram_password="",
            current_auth_step="SUCCESS",
            session_path=str(self.store.telegram_session_file(account)),
            code_confirmed=False,
            extra={"phone_code_hash": ""},
        )
        self.store.write_account_manifest(account)
        log(account_id, "INFO", f"Telegram session imported from file '{filename}'.")
        return (await self.get_telegram_status(account_id)).model_copy(
            update={"message": f"Telegram session imported from file '{filename}'."}
        )

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
        log(account_id, "INFO", "Saving Shafa authentication state.")
        try:
            storage_state = self._normalize_storage_state(payload)
            auth_path = self.store.auth_file(account)
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            auth_path.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8")
            if not self.store.is_valid_shafa_session(account):
                auth_path.unlink(missing_ok=True)
                log(account_id, "WARNING", "Rejected Shafa cookies: valid session cookie was not found.")
                raise BadRequestError("Shafa cookies must include a non-empty csrftoken for shafa.ua.")
            self.store.write_account_manifest(account)
            log(account_id, "INFO", "Shafa session saved.")
            return await self.get_shafa_status(account_id)
        except BadRequestError:
            raise
        except Exception as exc:
            log(account_id, "ERROR", f"Unexpected Shafa session save failure: {exc}")
            raise

    async def start_shafa_browser_login(self, account_id: str) -> ShafaAuthStatusResponse:
        account = await self._get_account(account_id)
        log(account_id, "INFO", "Starting Shafa browser login flow.")
        try:
            self.shafa_login_launcher(account, ["main.py", "--login-shafa"])
            status = await self.get_shafa_status(account_id)
            log(account_id, "INFO", "Shafa browser login flow started.")
            return status.model_copy(
                update={
                    "message": "Shafa login flow started. Complete login in the opened browser window.",
                }
            )
        except BadRequestError as exc:
            log(account_id, "ERROR", f"Failed to start Shafa login flow: {exc.message}")
            raise
        except Exception as exc:
            log(account_id, "ERROR", f"Unexpected Shafa login launcher failure: {exc}")
            raise

    async def logout_shafa(self, account_id: str) -> ShafaAuthStatusResponse:
        account = await self._get_account(account_id)
        self.store.delete_shafa_session(account)
        status = await self.get_shafa_status(account_id)
        log(account_id, "INFO", "Shafa session removed.")
        return status.model_copy(update={"message": "Shafa cookies removed."})

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
        project_path = _preferred_project_dir(Path(account.path).expanduser())
        api_id, api_hash = self._resolve_telegram_credentials(account)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["SHAFA_ACCOUNT_STATE_DIR"] = str(state_dir)
        env["SHAFA_STORAGE_STATE_PATH"] = str(self.store.auth_file(account))
        env["SHAFA_DB_PATH"] = str(_project_data_dir(project_path) / "shafa.sqlite3")
        env["SHAFA_TELEGRAM_SESSION_PATH"] = str(self.store.telegram_session_file(account))
        env["SHAFA_TELEGRAM_LOGIN_STATE_PATH"] = str(self.store.telegram_login_state_file(account))
        env["SHAFA_TELEGRAM_CHANNELS_PATH"] = str(self.store.channels_file(account))
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
    def _read_env_file(path: Path) -> dict[str, str]:
        result = {
            "SHAFA_TELEGRAM_API_ID": "",
            "SHAFA_TELEGRAM_API_HASH": "",
        }
        if not path.exists():
            return result
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in result:
                result[key] = value.strip().strip("\"'")
        return result

    def _resolve_telegram_credentials(self, account: Account) -> tuple[str, str]:
        account_credentials = self.store.load_telegram_credentials(account)
        root_credentials = self._read_env_file(Path(__file__).resolve().parents[2] / ".env")
        api_id = (
            account_credentials.get("SHAFA_TELEGRAM_API_ID", "").strip()
            or root_credentials.get("SHAFA_TELEGRAM_API_ID", "").strip()
            or str(os.getenv("SHAFA_TELEGRAM_API_ID", "")).strip()
        )
        api_hash = (
            account_credentials.get("SHAFA_TELEGRAM_API_HASH", "").strip()
            or root_credentials.get("SHAFA_TELEGRAM_API_HASH", "").strip()
            or str(os.getenv("SHAFA_TELEGRAM_API_HASH", "")).strip()
        )
        return api_id, api_hash

    def _has_telegram_credentials(self, account: Account) -> bool:
        api_id, api_hash = self._resolve_telegram_credentials(account)
        return api_id.isdigit() and bool(api_hash)

    def _launch_shafa_login(self, account: Account, args: list[str]) -> None:
        project_path = _preferred_project_dir(Path(account.path).expanduser())
        if not _project_main_path(project_path).is_file():
            raise BadRequestError(f"main.py not found at {project_path}")
    def _run_account_command(self, account: Account, args: list[str]):
        return self.runtime.run_account_command(account, args)

    def _launch_shafa_login(self, account: Account, args: list[str]) -> None:
        project_path = preferred_project_dir(Path(account.path).expanduser())
        if not project_main_path(project_path).is_file():
            raise BadRequestError(f"main.py not found at {project_path}")

        account_dir = self.store.account_dir(account)
        account_dir.mkdir(parents=True, exist_ok=True)
        log_file = account_dir / "shafa_login.log"
        log_file.write_text("", encoding="utf-8")

        try:
            with log_file.open("a", encoding="utf-8") as stream:
                process = subprocess.Popen(
                    [self.runtime.account_python(account), *args],
                    cwd=str(project_path),
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=stream,
                    env=self.runtime.account_env(account),
                    start_new_session=True,
                )
        except OSError as exc:
            raise BadRequestError(f"Failed to start Shafa login flow: {exc}") from exc

        time.sleep(1)
        exit_code = process.poll()
        if exit_code is None:
            return

        log_tail = ""
        try:
            log_lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            if log_lines:
                log_tail = log_lines[-1]
        except OSError:
            log_tail = ""

        detail = f" Shafa login exited immediately with code {exit_code}."
        if log_tail:
            detail += f" {log_tail}"
        raise BadRequestError(f"Failed to start Shafa login flow.{detail}")

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
