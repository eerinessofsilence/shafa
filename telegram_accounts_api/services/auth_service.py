from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib import error, request

from fastapi import UploadFile

from shafa_control import (
    Account,
    AccountRuntimeService,
    AccountSessionStore,
    ShafaAuthService,
    TelegramAuthService,
    python_candidates,
    project_main_path,
    resolve_project_dir,
)
from shafa_logic.data.const import API_BATCH_URL, APP_PLATFORM, APP_VERSION, ORIGIN_URL

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


def _windows_gui_python(python_command: str) -> str:
    candidate = Path(python_command)
    if candidate.name.lower() == "python.exe":
        pythonw_candidate = candidate.with_name("pythonw.exe")
        if pythonw_candidate.exists():
            return str(pythonw_candidate)

    resolved = shutil.which(python_command)
    if resolved:
        resolved_path = Path(resolved)
        if resolved_path.name.lower() == "python.exe":
            pythonw_candidate = resolved_path.with_name("pythonw.exe")
            if pythonw_candidate.exists():
                return str(pythonw_candidate)

    return python_command


SHAFA_SETTINGS_REFERER_URL = "https://shafa.ua/uk/my/settings"
SHAFA_PROFILE_OPERATION_NAME = "WEB_MainInfoSettingsFormData"
SHAFA_PROFILE_QUERY = """query WEB_MainInfoSettingsFormData {
  viewer {
    id
    thumbnail
    firstName
    lastName
    patronymic
    email
    phone
    showRealName
    showSocialWebSite
    city {
      id
      name
      __typename
    }
    gender
    about
    __typename
  }
}"""


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
        phone_number = str(state.get("phone_number") or account.phone_number or "").strip()
        if connected and not phone_number:
            phone_number = await self._backfill_phone_from_session(account)
        return TelegramAuthStatusResponse(
            account_id=account.id,
            connected=connected,
            has_api_credentials=self._has_telegram_credentials(account),
            current_step=current_step,
            next_step=self._next_telegram_step(current_step, connected),
            phone_number=phone_number,
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
            raise BadRequestError("Telegram API ID должен быть числом.")
        if not api_hash:
            log(account_id, "WARNING", "Rejected Telegram credentials: API hash missing.")
            raise BadRequestError("Нужен Telegram API hash.")
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
                    "На backend не настроены Telegram API-данные. "
                    "Укажи SHAFA_TELEGRAM_API_ID и SHAFA_TELEGRAM_API_HASH в .env или переменных окружения.",
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
        return status.model_copy(update={"message": "Сессия Telegram удалена."})

    async def copy_telegram_session(
        self,
        account_id: str,
        payload: TelegramSessionCopyRequest,
    ) -> TelegramAuthStatusResponse:
        target = await self._get_account(account_id)
        source_account_id = str(payload.source_account_id or "").strip()
        if not source_account_id:
            raise BadRequestError("Нужен ID исходного аккаунта.")
        if source_account_id == account_id:
            raise BadRequestError("Исходный и целевой аккаунты должны отличаться.")
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
            update={"message": f"Сессия Telegram скопирована из аккаунта '{source_account_id}'."}
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
                raise BadRequestError("Файл сессии Telegram пустой.")

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
            update={"message": f"Сессия Telegram импортирована из файла '{filename}'."}
        )

    async def get_shafa_status(self, account_id: str) -> ShafaAuthStatusResponse:
        account = await self._get_account(account_id)
        auth_path = self.store.auth_file(account)
        cookies_count = 0
        cookies: list[dict[str, Any]] = []
        if auth_path.exists():
            try:
                payload = json.loads(auth_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            raw_cookies = payload.get("cookies")
            if isinstance(raw_cookies, list):
                cookies = [
                    cookie
                    for cookie in raw_cookies
                    if isinstance(cookie, dict)
                ]
                cookies_count = len(cookies)
        connected = self.store.is_valid_shafa_session(account)
        email = ""
        phone = ""

        if connected and cookies:
            try:
                profile = self._fetch_shafa_profile(cookies)
            except Exception as exc:
                log(account_id, "WARNING", f"Failed to fetch Shafa profile data: {exc}")
            else:
                email = str(profile.get("email") or "").strip()
                phone = str(profile.get("phone") or "").strip()

        return ShafaAuthStatusResponse(
            account_id=account.id,
            connected=connected,
            cookies_count=cookies_count,
            email=email,
            phone=phone,
            message="Cookies Shafa готовы." if connected else "Cookies Shafa отсутствуют или недействительны.",
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
                raise BadRequestError("Cookies Shafa должны содержать непустой csrftoken для shafa.ua.")
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
                    "message": "Вход в Shafa запущен. Заверши вход в открытом окне браузера.",
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
        return status.model_copy(update={"message": "Cookies Shafa удалены."})

    async def _get_account(self, account_id: str) -> Account:
        account = await self.account_service.get_account(account_id)
        return Account(
            id=account.id,
            name=account.name,
            path=account.path,
            phone_number=account.phone,
            branch=account.branch,
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
        env["SHAFA_DB_PATH"] = str(self.store.db_file(account))
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
        for candidate in python_candidates(project_path):
            if candidate.exists():
                return str(candidate)
        return str(Path(sys.executable))

    def _run_account_command(self, account: Account, args: list[str]) -> subprocess.CompletedProcess:
        project_path = _preferred_project_dir(Path(account.path).expanduser())
        if not _project_main_path(project_path).is_file():
            return subprocess.CompletedProcess(
                [self._account_python(account), *args],
                1,
                stdout="",
                stderr=f"main.py не найден по пути {project_path}",
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

    async def _backfill_phone_from_session(self, account: Account) -> str:
        phone_number = await self._resolve_phone_from_session(account)

        if not phone_number:
            return ""

        account_with_phone = self._with_phone(account, phone_number)
        await self.account_service.set_account_phone(account.id, phone_number)
        self.telegram_auth.persist_auth_state(
            account_with_phone,
            phone_number=phone_number,
            verification_code="",
            telegram_password="",
            current_auth_step="SUCCESS",
            session_path=str(self.store.telegram_session_file(account)),
            code_confirmed=False,
            extra={"phone_code_hash": ""},
        )
        self.store.write_account_manifest(account_with_phone)
        log(account.id, "INFO", "Telegram phone number resolved from authorized session.")
        return phone_number

    async def _resolve_phone_from_session(self, account: Account) -> str:
        if not self.store.is_valid_telegram_session(account):
            return ""

        api_id, api_hash = self._resolve_telegram_credentials(account)
        if not api_id.isdigit() or not api_hash:
            return ""

        try:
            from telethon import TelegramClient
        except ImportError:
            return ""

        try:
            client = TelegramClient(
                str(self.store.telegram_session_file(account)),
                int(api_id),
                api_hash,
            )
            await client.connect()

            if not await client.is_user_authorized():
                return ""

            me = await client.get_me()
            return self._normalize_resolved_telegram_phone(
                getattr(me, "phone", None),
            )
        except Exception:
            return ""
        finally:
            if "client" in locals():
                await client.disconnect()

    @staticmethod
    def _normalize_resolved_telegram_phone(phone: str | None) -> str:
        normalized_phone = TelegramAuthService.normalize_phone(str(phone or ""))

        if not normalized_phone:
            return ""

        return (
            normalized_phone
            if normalized_phone.startswith("+")
            else f"+{normalized_phone}"
        )

    def _fetch_shafa_profile(self, cookies: list[dict[str, Any]]) -> dict[str, Any]:
        csrftoken = self._get_csrftoken_from_cookies(cookies)
        if not csrftoken:
            raise BadRequestError("Cookies Shafa должны содержать csrftoken.")

        payload = json.dumps(
            [
                {
                    "operationName": SHAFA_PROFILE_OPERATION_NAME,
                    "variables": {},
                    "query": SHAFA_PROFILE_QUERY,
                }
            ]
        ).encode("utf-8")
        request_headers = {
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
            "Cookie": self._build_cookie_header(cookies),
            "Origin": ORIGIN_URL,
            "Referer": SHAFA_SETTINGS_REFERER_URL,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) "
                "Gecko/20100101 Firefox/149.0"
            ),
            "batch": "true",
            "x-app-platform": APP_PLATFORM,
            "x-app-version": APP_VERSION,
            "x-csrftoken": csrftoken,
        }
        http_request = request.Request(
            API_BATCH_URL,
            data=payload,
            headers=request_headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=20) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Запрос профиля Shafa завершился HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Не удалось запросить профиль Shafa: {exc.reason}") from exc

        try:
            parsed_response = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ответ профиля Shafa не является корректным JSON.") from exc

        if isinstance(parsed_response, list):
            for item in parsed_response:
                if not isinstance(item, dict):
                    continue
                viewer = item.get("data", {}).get("viewer")
                if isinstance(viewer, dict):
                    return viewer
        elif isinstance(parsed_response, dict):
            viewer = parsed_response.get("data", {}).get("viewer")
            if isinstance(viewer, dict):
                return viewer

        raise RuntimeError("Ответ профиля Shafa не содержит данные viewer.")

    @staticmethod
    def _get_csrftoken_from_cookies(cookies: list[dict[str, Any]]) -> str:
        for cookie in cookies:
            name = str(cookie.get("name") or "").strip()
            if name == "csrftoken":
                return str(cookie.get("value") or "").strip()
        return ""

    @staticmethod
    def _build_cookie_header(cookies: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for cookie in cookies:
            name = str(cookie.get("name") or "").strip()
            value = cookie.get("value")
            if not name or value in (None, ""):
                continue
            parts.append(f"{name}={value}")
        return "; ".join(parts)

    def _run_account_command(self, account: Account, args: list[str]):
        project_path = resolve_project_dir(Path(account.path).expanduser())
        if not project_main_path(project_path).is_file():
            telegram_result = self._run_packaged_telegram_command(account, args)
            if telegram_result is not None:
                return telegram_result
        return self.runtime.run_account_command(account, args)

    def _run_packaged_telegram_command(
        self,
        account: Account,
        args: list[str],
    ) -> subprocess.CompletedProcess | None:
        if len(args) >= 3 and args[:2] == ["main.py", "--telegram-send-code"]:
            return self._run_packaged_telegram_step(
                args,
                lambda: self._direct_request_telegram_code(account, args[2]),
                "Код Telegram запрошен.",
            )

        if (
            len(args) >= 5
            and args[0] == "main.py"
            and args[1] == "--telegram-login-phone"
            and args[3] == "--telegram-login-code"
        ):
            return self._run_packaged_telegram_step(
                args,
                lambda: self._direct_submit_telegram_code(account, args[2], args[4]),
                "Код Telegram отправлен.",
            )

        if len(args) >= 3 and args[:2] == ["main.py", "--telegram-login-password"]:
            return self._run_packaged_telegram_step(
                args,
                lambda: self._direct_submit_telegram_password(account, args[2]),
                "Пароль Telegram отправлен.",
            )

        if args == ["main.py", "--telegram-session-status"]:
            try:
                authorized = self._run_async_blocking(
                    lambda: self._direct_telegram_session_status(account),
                )
            except Exception:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(
                args,
                0 if authorized else 1,
                stdout="Сессия Telegram авторизована." if authorized else "",
                stderr="",
            )

        return None

    def _run_packaged_telegram_step(
        self,
        args: list[str],
        action,
        success_message: str,
    ) -> subprocess.CompletedProcess:
        try:
            self._run_async_blocking(action)
        except Exception as exc:
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="",
                stderr=str(exc) or exc.__class__.__name__,
            )
        return subprocess.CompletedProcess(args, 0, stdout=success_message, stderr="")

    @staticmethod
    def _run_async_blocking(action):
        result: dict[str, Any] = {}

        def target() -> None:
            try:
                result["value"] = asyncio.run(action())
            except BaseException as exc:
                result["error"] = exc

        thread = threading.Thread(target=target)
        thread.start()
        thread.join()

        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _telegram_client_config(self, account: Account) -> tuple[Any, int, str, Path]:
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise RuntimeError("Telethon не установлен.") from exc

        api_id, api_hash = self._resolve_telegram_credentials(account)
        if not api_id.isdigit() or not api_hash:
            raise RuntimeError("На backend не настроены Telegram API-данные.")
        return TelegramClient, int(api_id), api_hash, self.store.telegram_session_file(account)

    async def _connect_direct_telegram_client(self, account: Account):
        telegram_client_cls, api_id, api_hash, session_file = self._telegram_client_config(account)
        client = telegram_client_cls(str(session_file), api_id, api_hash)
        await client.connect()
        return client

    async def _direct_request_telegram_code(self, account: Account, phone: str) -> None:
        phone = TelegramAuthService.normalize_phone(phone)
        session_file = self.store.telegram_session_file(account)
        self.telegram_auth.persist_auth_state(
            account,
            phone_number=phone,
            verification_code="",
            telegram_password="",
            current_auth_step="WAIT_PHONE",
            session_path=str(session_file),
            code_confirmed=False,
            extra={"phone_code_hash": ""},
        )

        client = await self._connect_direct_telegram_client(account)
        try:
            sent = await client.send_code_request(phone)
        except Exception:
            self.telegram_auth.persist_auth_state(
                account,
                phone_number=phone,
                verification_code="",
                telegram_password="",
                current_auth_step="FAILED",
                session_path=str(session_file),
                code_confirmed=False,
                extra={"phone_code_hash": ""},
            )
            raise
        finally:
            await client.disconnect()

        self.telegram_auth.persist_auth_state(
            account,
            phone_number=phone,
            verification_code="",
            telegram_password="",
            current_auth_step="WAIT_CODE",
            session_path=str(session_file),
            code_confirmed=False,
            extra={"phone_code_hash": str(sent.phone_code_hash).strip()},
        )

    async def _direct_submit_telegram_code(
        self,
        account: Account,
        phone: str,
        code: str,
    ) -> None:
        state = self.telegram_auth.load_auth_state(account)
        session_file = self.store.telegram_session_file(account)
        phone_code_hash = str(state.get("phone_code_hash") or "").strip()
        if not phone_code_hash:
            raise RuntimeError("Вход в Telegram не был начат для этого аккаунта.")

        client = await self._connect_direct_telegram_client(account)
        try:
            await client.sign_in(
                phone=TelegramAuthService.normalize_phone(phone),
                code=str(code).strip(),
                phone_code_hash=phone_code_hash,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "SessionPasswordNeededError":
                self.telegram_auth.persist_auth_state(
                    account,
                    phone_number=TelegramAuthService.normalize_phone(phone),
                    verification_code=str(code).strip(),
                    telegram_password=str(state.get("telegram_password") or ""),
                    current_auth_step="WAIT_PASSWORD",
                    session_path=str(session_file),
                    code_confirmed=True,
                    extra={"phone_code_hash": phone_code_hash},
                )
                return
            self.telegram_auth.persist_auth_state(
                account,
                phone_number=TelegramAuthService.normalize_phone(phone),
                verification_code="",
                telegram_password=str(state.get("telegram_password") or ""),
                current_auth_step="WAIT_CODE",
                session_path=str(session_file),
                code_confirmed=False,
                extra={"phone_code_hash": phone_code_hash},
            )
            raise
        finally:
            await client.disconnect()

        self.telegram_auth.persist_auth_state(
            account,
            phone_number=TelegramAuthService.normalize_phone(phone),
            verification_code=str(code).strip(),
            telegram_password=str(state.get("telegram_password") or ""),
            current_auth_step="SUCCESS",
            session_path=str(session_file),
            code_confirmed=True,
            extra={"phone_code_hash": ""},
        )
        self.store.write_account_manifest(account)

    async def _direct_submit_telegram_password(
        self,
        account: Account,
        password: str,
    ) -> None:
        state = self.telegram_auth.load_auth_state(account)
        session_file = self.store.telegram_session_file(account)
        client = await self._connect_direct_telegram_client(account)
        try:
            await client.sign_in(password=password)
        finally:
            await client.disconnect()

        self.telegram_auth.persist_auth_state(
            account,
            phone_number=str(state.get("phone_number") or account.phone_number or "").strip(),
            verification_code=str(state.get("verification_code") or ""),
            telegram_password=password,
            current_auth_step="SUCCESS",
            session_path=str(session_file),
            code_confirmed=True,
            extra={"phone_code_hash": ""},
        )
        self.store.write_account_manifest(account)

    async def _direct_telegram_session_status(self, account: Account) -> bool:
        if not self.store.is_valid_telegram_session(account):
            return False

        client = await self._connect_direct_telegram_client(account)
        try:
            authorized = bool(await client.is_user_authorized())
        finally:
            await client.disconnect()

        if authorized:
            self.telegram_auth.persist_auth_state(
                account,
                current_auth_step="SUCCESS",
                session_path=str(self.store.telegram_session_file(account)),
                code_confirmed=False,
                extra={"phone_code_hash": ""},
            )
            self.store.write_account_manifest(account)
        return authorized

    def _launch_shafa_login(self, account: Account, args: list[str]) -> None:
        project_path = resolve_project_dir(Path(account.path).expanduser())
        if not project_main_path(project_path).is_file():
            raise BadRequestError(f"main.py не найден по пути {project_path}")

        account_dir = self.store.account_dir(account)
        account_dir.mkdir(parents=True, exist_ok=True)
        log_file = account_dir / "shafa_login.log"
        log_file.write_text("", encoding="utf-8")

        python_command = self.runtime.account_python(account)
        if os.name == "nt":
            python_command = _windows_gui_python(python_command)

        try:
            with log_file.open("a", encoding="utf-8") as stream:
                process = subprocess.Popen(
                    [python_command, *args],
                    cwd=str(project_path),
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=stream,
                    env=self.runtime.account_env(account),
                    start_new_session=True,
                )
        except OSError as exc:
            raise BadRequestError(f"Не удалось запустить вход в Shafa: {exc}") from exc

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

        detail = f" Вход в Shafa сразу завершился с кодом {exit_code}."
        if log_tail:
            detail += f" {log_tail}"
        raise BadRequestError(f"Не удалось запустить вход в Shafa.{detail}")

    @staticmethod
    def _normalize_storage_state(payload: ShafaStorageStateRequest) -> dict[str, Any]:
        if payload.storage_state is not None:
            storage_state = dict(payload.storage_state)
            cookies = storage_state.get("cookies")
            if not isinstance(cookies, list):
                raise BadRequestError("storage_state.cookies должен быть списком.")
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
            return "Сессия Telegram готова."
        messages = {
            "INIT": "Вход в Telegram не начат.",
            "WAIT_PHONE": "Номер телефона принят. Запрашиваю код подтверждения.",
            "WAIT_CODE": "Введи код подтверждения Telegram.",
            "WAIT_PASSWORD": "Введи пароль двухфакторной защиты Telegram.",
            "FAILED": "Вход в Telegram не удался. Запроси новый код и попробуй снова.",
            "SUCCESS": "Сессия Telegram готова.",
        }
        return messages.get(current_step, "Статус входа в Telegram неизвестен.")
