from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from shafa_control import (
    Account,
    AccountRuntimeService,
    AccountSessionStore,
    LogRecord,
    LogStore,
    preferred_project_dir,
    project_main_path,
)
from telegram_accounts_api.models.account import AccountCreate, AccountRead, AccountUpdate
from telegram_accounts_api.utils.account_logging import (
    get_account_log_store,
    is_ignorable_log_message,
    normalize_log_message,
    log,
)
from telegram_accounts_api.utils.exceptions import BadRequestError, NotFoundError, StorageError
from telegram_accounts_api.utils.storage import JsonListStorage, read_json_list_file

LOGGER = logging.getLogger(__name__)
LEGACY_DEFAULT_PROJECT_PATH = "/Users/eeri/coding/python/projects/scripts/shafa"

ACCOUNT_KNOWN_FIELDS = {
    "id",
    "name",
    "phone",
    "phone_number",
    "path",
    "branch",
    "timer_minutes",
    "channel_links",
    "status",
    "last_run",
    "errors",
    "created_at",
    "updated_at",
}


@dataclass
class ManagedAccountProcess:
    account_id: str
    process: subprocess.Popen[str]
    watcher: threading.Thread


class AccountService:
    def __init__(
        self,
        storage: JsonListStorage,
        accounts_dir: Path,
        channel_template_service=None,
        session_store: AccountSessionStore | None = None,
    ) -> None:
        self.storage = storage
        self.accounts_dir = accounts_dir
        self.channel_template_service = channel_template_service
        self.session_store = session_store or AccountSessionStore(
            base_dir=accounts_dir.parent,
            accounts_dir=accounts_dir,
            legacy_state_file=storage.path,
        )
        self.runtime = AccountRuntimeService(self.session_store)
        self.log_store = LogStore(self.session_store.base_dir / "runtime" / "logs")
        self._records_lock = threading.RLock()
        self._process_lock = threading.RLock()
        self._processes: dict[str, ManagedAccountProcess] = {}
        self._expected_stops: set[str] = set()

    async def list_accounts(self) -> list[AccountRead]:
        payload = await self._read_payload()
        return [await self._to_model(item) for item in payload]

    async def get_account(self, account_id: str) -> AccountRead:
        item = await self._get_record(account_id)
        return await self._to_model(item)

    async def create_account(self, data: AccountCreate) -> AccountRead:
        payload = await self._read_payload()
        account_id = uuid4().hex
        while any(str(item.get("id")) == account_id for item in payload):
            account_id = uuid4().hex

        timestamp = datetime.now(UTC).isoformat()
        default_project_path = str(self.session_store.base_dir)
        record = {
            "id": account_id,
            "name": data.name,
            "phone_number": data.phone,
            "path": data.path or default_project_path,
            "branch": data.branch,
            "timer_minutes": data.timer_minutes,
            "channel_links": data.channel_links,
            "status": "stopped",
            "last_run": None,
            "errors": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        payload.append(record)
        await self._write_payload(payload)
        self._ensure_account_dir(account_id)
        log(account_id, "INFO", "Account created.")
        return await self._to_model(record)

    async def update_account(self, account_id: str, data: AccountUpdate) -> AccountRead:
        payload = await self._read_payload()
        updated_record: dict | None = None

        for item in payload:
            if str(item.get("id")) != account_id:
                continue

            if data.name is not None:
                item["name"] = data.name
            if data.path is not None:
                item["path"] = data.path
            if data.timer_minutes is not None:
                item["timer_minutes"] = data.timer_minutes
            if data.channel_links is not None:
                item["channel_links"] = data.channel_links

            item["updated_at"] = datetime.now(UTC).isoformat()
            updated_record = item
            break

        if updated_record is None:
            raise NotFoundError(f"Account '{account_id}' not found.")

        await self._write_payload(payload)
        LOGGER.info("Updated account %s", account_id)
        log(account_id, "INFO", "Account settings updated.")
        return await self._to_model(updated_record)

    async def delete_account(self, account_id: str) -> None:
        await self.stop_account(account_id)
        payload = await self._read_payload()
        filtered = [item for item in payload if str(item.get("id")) != account_id]
        if len(filtered) == len(payload):
            raise NotFoundError(f"Account '{account_id}' not found.")
        await self._write_payload(filtered)
        account_dir = self.accounts_dir / account_id
        if account_dir.exists():
            shutil.rmtree(account_dir)
        log(account_id, "INFO", "Account deleted.")

    async def start_account(self, account_id: str) -> AccountRead:
        record = await self._get_record(account_id)
        account = self._record_to_account(record)
        running_process = self._active_process(account_id)
        if running_process is not None:
            return await self._to_model(record)

        try:
            launch_context = self._build_launch_context(account)
            process = self._spawn_process(account, launch_context)
        except BadRequestError as exc:
            self._append_log(account, f"[ERROR] {exc.message}")
            self._update_record_sync(account_id, self._mark_process_failed)
            raise
        await asyncio.sleep(0.2)

        exit_code = process.poll()
        if exit_code is not None:
            output = self._consume_process_output(process).strip()
            message = self._format_start_failure(account, exit_code, output)
            self._append_log(account, message)
            self._update_record_sync(account_id, self._mark_process_failed)
            raise BadRequestError(message)

        watcher = threading.Thread(
            target=self._watch_process,
            args=(account, process),
            daemon=True,
            name=f"account-process-{account.id}",
        )
        with self._process_lock:
            self._processes[account.id] = ManagedAccountProcess(
                account_id=account.id,
                process=process,
                watcher=watcher,
            )
            self._expected_stops.discard(account.id)

        watcher.start()
        updated_record = await self._update_record(
            account_id,
            lambda item: self._mark_process_started(item),
        )
        self._append_log(account, f"[RUN] started pid={process.pid}")
        if account.channel_links:
            self._append_log(
                account,
                f"[CHANNELS] exported {len(account.channel_links)} link(s)",
            )
        LOGGER.info("Started account %s with pid %s", account_id, process.pid)
        log(account_id, "INFO", f"Account status changed to started (pid={process.pid}).")
        return await self._to_model(updated_record)

    async def stop_account(self, account_id: str) -> AccountRead:
        record = await self._get_record(account_id)
        account = self._record_to_account(record)
        managed = self._active_process(account_id)
        if managed is None:
            updated_record = await self._update_record(
                account_id,
                lambda item: self._mark_process_stopped(item),
            )
            return await self._to_model(updated_record)

        with self._process_lock:
            self._expected_stops.add(account_id)

        await asyncio.to_thread(self._terminate_process, managed.process)
        updated_record = await self._update_record(
            account_id,
            lambda item: self._mark_process_stopped(item),
        )
        self._append_log(account, "[STOP] stop requested from API")
        LOGGER.info("Stopped account %s", account_id)
        log(account_id, "INFO", "Account status changed to stopped.")
        return await self._to_model(updated_record)

    async def set_account_phone(self, account_id: str, phone: str) -> AccountRead:
        normalized_phone = str(phone or "").strip()
        updated_record = await self._update_record(
            account_id,
            lambda item: self._set_phone_number(item, normalized_phone),
        )
        return await self._to_model(updated_record)

    async def set_status(self, account_id: str, status: str) -> AccountRead:
        if status == "started":
            return await self.start_account(account_id)
        if status == "stopped":
            return await self.stop_account(account_id)
        raise BadRequestError(f"Unsupported account status '{status}'.")

    def account_dir(self, account_id: str) -> Path:
        return self.accounts_dir / account_id

    def session_file(self, account_id: str) -> Path:
        return self.account_dir(account_id) / "telegram.session"

    def credentials_file(self, account_id: str) -> Path:
        return self.account_dir(account_id) / ".env"

    def _ensure_account_dir(self, account_id: str) -> None:
        self.account_dir(account_id).mkdir(parents=True, exist_ok=True)

    async def _to_model(self, item: dict) -> AccountRead:
        phone = str(item.get("phone") or item.get("phone_number") or "").strip()
        extra = {key: value for key, value in item.items() if key not in ACCOUNT_KNOWN_FIELDS}
        account_id = str(item.get("id") or "")
        runtime_account = self._record_to_account(item)
        if self._active_process(account_id) is not None:
            status = "started"
        else:
            status = "stopped"
        channel_templates = []
        if self.channel_template_service is not None and account_id:
            channel_templates = await self.channel_template_service.list_template_summaries(account_id)
        return AccountRead(
            id=account_id,
            name=runtime_account.name,
            phone=phone,
            path=runtime_account.path,
            branch=runtime_account.branch,
            timer_minutes=runtime_account.timer_minutes,
            channel_links=runtime_account.channel_links,
            status=status,
            last_run=item.get("last_run"),
            errors=int(item.get("errors", 0)),
            shafa_session_exists=self.session_store.is_valid_shafa_session(runtime_account),
            telegram_session_exists=self.session_store.is_valid_telegram_session(runtime_account),
            api_credentials_configured=self.credentials_file(account_id).exists(),
            created_at=self._parse_datetime(item.get("created_at")),
            updated_at=self._parse_datetime(item.get("updated_at")),
            channel_templates=channel_templates,
            extra=extra,
        )

    async def _read_payload(self) -> list[dict]:
        return await asyncio.to_thread(self._read_payload_sync)

    async def _write_payload(self, payload: list[dict]) -> None:
        await asyncio.to_thread(self._write_payload_sync, payload)

    def _read_payload_sync(self) -> list[dict]:
        with self._records_lock:
            return [self._normalize_record(item) for item in read_json_list_file(self.storage.path)]

    def _write_payload_sync(self, payload: list[dict]) -> None:
        with self._records_lock:
            try:
                self.storage.path.parent.mkdir(parents=True, exist_ok=True)
                normalized_payload = [self._normalize_record(item) for item in payload]
                self.storage.path.write_text(
                    json.dumps(normalized_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                raise StorageError(f"Failed to write JSON file: {self.storage.path}") from exc

    async def _get_record(self, account_id: str) -> dict:
        payload = await self._read_payload()
        for item in payload:
            if str(item.get("id")) == account_id:
                return item
        raise NotFoundError(f"Account '{account_id}' not found.")

    async def _update_record(self, account_id: str, update_fn: Callable[[dict], None]) -> dict:
        return await asyncio.to_thread(self._update_record_sync, account_id, update_fn)

    def _update_record_sync(self, account_id: str, update_fn: Callable[[dict], None]) -> dict:
        with self._records_lock:
            payload = self._read_payload_sync()
            for item in payload:
                if str(item.get("id")) != account_id:
                    continue
                update_fn(item)
                self._write_payload_sync(payload)
                return dict(item)
        raise NotFoundError(f"Account '{account_id}' not found.")

    @staticmethod
    def _set_phone_number(item: dict, phone: str) -> None:
        item["phone_number"] = phone
        item["updated_at"] = datetime.now(UTC).isoformat()

    def _normalize_record(self, item: dict) -> dict:
        normalized = dict(item)
        normalized.pop("open_browser", None)
        path = str(normalized.get("path") or "").strip()
        default_project_path = str(self.session_store.base_dir).strip()
        if path == LEGACY_DEFAULT_PROJECT_PATH and default_project_path and default_project_path != path:
            normalized["path"] = default_project_path
        return normalized

    def _record_to_account(self, item: dict) -> Account:
        phone = str(item.get("phone") or item.get("phone_number") or "").strip()
        return Account(
            id=str(item.get("id") or ""),
            name=str(item.get("name") or "").strip(),
            path=str(item.get("path") or "").strip(),
            phone_number=phone,
            branch=str(item.get("branch") or "main").strip() or "main",
            timer_minutes=int(item.get("timer_minutes", 5)),
            channel_links=item.get("channel_links") or [],
            status="started" if str(item.get("status")).strip().lower() in {"started", "running"} else "stopped",
            last_run=item.get("last_run") or "—",
            errors=int(item.get("errors", 0)),
        )

    def _build_launch_context(self, account: Account) -> dict[str, str]:
        if not account.path.strip():
            raise BadRequestError("Перед запуском нужно указать путь проекта аккаунта.")
        normalized_path = preferred_project_dir(Path(account.path).expanduser())
        if not project_main_path(normalized_path).is_file():
            raise BadRequestError(f"main.py не найден по пути {normalized_path}")
        if not self.session_store.is_valid_shafa_session(account):
            raise BadRequestError(
                "Сессия Shafa отсутствует или недействительна. Перед запуском аккаунта выполни вход в Shafa.",
            )
        if account.channel_links and not self.session_store.is_valid_telegram_session(account):
            raise BadRequestError(
                "Сессия Telegram отсутствует или недействительна. Перед синхронизацией каналов выполни вход в Telegram.",
            )

        env = self.runtime.account_env(account)
        if account.channel_links:
            channels_file = self.runtime.export_channel_runtime_config(account)
            env["SHAFA_TELEGRAM_CHANNEL_LINKS_FILE"] = str(channels_file)
        return {
            "cwd": str(normalized_path),
            **env,
        }

    def _spawn_process(self, account: Account, launch_context: dict[str, str]) -> subprocess.Popen[str]:
        cwd = launch_context.pop("cwd")
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            return subprocess.Popen(
                [self.runtime.account_python(account), "main.py", "--shafa"],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=launch_context,
                **popen_kwargs,
            )
        except OSError as exc:
            raise BadRequestError(f"Не удалось запустить процесс аккаунта: {exc}") from exc

    def _watch_process(self, account: Account, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout is not None:
                for raw_line in process.stdout:
                    line = raw_line.rstrip()
                    if not line:
                        continue
                    self._append_log(account, line)
        except Exception:
            LOGGER.exception("Failed to stream logs for account %s", account.id)
        finally:
            exit_code = process.wait()
            expected_stop = self._cleanup_process(account.id, process)
            self._handle_process_exit_sync(account, exit_code, expected_stop)

    def _cleanup_process(self, account_id: str, process: subprocess.Popen[str]) -> bool:
        with self._process_lock:
            managed = self._processes.get(account_id)
            if managed is not None and managed.process is process:
                self._processes.pop(account_id, None)
            expected_stop = account_id in self._expected_stops
            self._expected_stops.discard(account_id)
            return expected_stop

    def _handle_process_exit_sync(self, account: Account, exit_code: int, expected_stop: bool) -> None:
        if expected_stop or exit_code == 0:
            self._append_log(account, f"[STOP] process exited with code {exit_code}")
            try:
                self._update_record_sync(account.id, self._mark_process_stopped)
            except NotFoundError:
                return
            return
        self._append_log(account, f"[ERROR] process exited with code {exit_code}")
        try:
            self._update_record_sync(account.id, self._mark_process_failed)
        except NotFoundError:
            return

    def _active_process(self, account_id: str) -> ManagedAccountProcess | None:
        with self._process_lock:
            managed = self._processes.get(account_id)
            if managed is None:
                return None
            if managed.process.poll() is None:
                return managed
            self._processes.pop(account_id, None)
            self._expected_stops.discard(account_id)
            return None

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
            return
        except Exception:
            LOGGER.warning("Graceful stop failed for pid %s, forcing kill", process.pid)
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except Exception:
            LOGGER.exception("Failed to kill pid %s", process.pid)

    def _append_log(self, account: Account, message: str) -> None:
        normalized_message = normalize_log_message(message)
        if is_ignorable_log_message(normalized_message):
            return

        record = LogRecord(
            timestamp=datetime.now(),
            message=normalized_message,
            level=self.log_store.detect_level(normalized_message),
            account_id=account.id,
            account_name=account.name,
        )
        self.log_store.append(
            record,
            account_log_file=self.session_store.account_log_file(account),
        )
        get_account_log_store().append(
            account_id=account.id,
            level=record.level,
            message=normalized_message,
            timestamp=record.timestamp,
        )

    def _consume_process_output(self, process: subprocess.Popen[str]) -> str:
        if process.stdout is None:
            return ""
        try:
            return process.stdout.read()
        except OSError:
            return ""

    @staticmethod
    def _mark_process_started(item: dict) -> None:
        item["status"] = "started"
        item["last_run"] = datetime.now().isoformat(timespec="seconds")
        item["updated_at"] = datetime.now(UTC).isoformat()

    @staticmethod
    def _mark_process_stopped(item: dict) -> None:
        item["status"] = "stopped"
        item["updated_at"] = datetime.now(UTC).isoformat()

    @staticmethod
    def _mark_process_failed(item: dict) -> None:
        item["status"] = "stopped"
        item["errors"] = int(item.get("errors", 0)) + 1
        item["updated_at"] = datetime.now(UTC).isoformat()

    def _format_start_failure(self, account: Account, exit_code: int, output: str) -> str:
        tail = output.splitlines()[-1].strip() if output else ""
        detail = f"Аккаунт '{account.name}' сразу завершился с кодом {exit_code}."
        if tail:
            detail = f"{detail} {tail}"
        return detail

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
