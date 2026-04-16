from __future__ import annotations

import logging
import shutil
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from telegram_accounts_api.models.account import AccountCreate, AccountRead, AccountUpdate
from telegram_accounts_api.utils.exceptions import NotFoundError
from telegram_accounts_api.utils.storage import JsonListStorage

LOGGER = logging.getLogger(__name__)

ACCOUNT_KNOWN_FIELDS = {
    "id",
    "name",
    "phone",
    "phone_number",
    "path",
    "branch",
    "open_browser",
    "timer_minutes",
    "channel_links",
    "status",
    "last_run",
    "errors",
    "created_at",
    "updated_at",
}


class AccountService:
    def __init__(self, storage: JsonListStorage, accounts_dir: Path, channel_template_service=None) -> None:
        self.storage = storage
        self.accounts_dir = accounts_dir
        self.channel_template_service = channel_template_service

    async def list_accounts(self) -> list[AccountRead]:
        payload = await self.storage.read()
        return [await self._to_model(item) for item in payload]

    async def get_account(self, account_id: str) -> AccountRead:
        for item in await self.storage.read():
            if str(item.get("id")) == account_id:
                return await self._to_model(item)
        raise NotFoundError(f"Account '{account_id}' not found.")

    async def create_account(self, data: AccountCreate) -> AccountRead:
        payload = await self.storage.read()
        account_id = uuid4().hex
        while any(str(item.get("id")) == account_id for item in payload):
            account_id = uuid4().hex

        timestamp = datetime.now(UTC).isoformat()
        record = {
            "id": account_id,
            "name": data.name,
            "phone_number": data.phone,
            "path": data.path,
            "branch": data.branch,
            "open_browser": data.open_browser,
            "timer_minutes": data.timer_minutes,
            "channel_links": data.channel_links,
            "status": "stopped",
            "last_run": None,
            "errors": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        payload.append(record)
        await self.storage.write(payload)
        self._ensure_account_dir(account_id)
        LOGGER.info("Created account %s", account_id)
        return await self._to_model(record)

    async def update_account(self, account_id: str, data: AccountUpdate) -> AccountRead:
        payload = await self.storage.read()
        updated_record: dict | None = None

        for item in payload:
            if str(item.get("id")) != account_id:
                continue

            if data.name is not None:
                item["name"] = data.name
            if data.path is not None:
                item["path"] = data.path
            if data.open_browser is not None:
                item["open_browser"] = data.open_browser
            if data.timer_minutes is not None:
                item["timer_minutes"] = data.timer_minutes

            item["updated_at"] = datetime.now(UTC).isoformat()
            updated_record = item
            break

        if updated_record is None:
            raise NotFoundError(f"Account '{account_id}' not found.")

        await self.storage.write(payload)
        LOGGER.info("Updated account %s", account_id)
        return await self._to_model(updated_record)

    async def delete_account(self, account_id: str) -> None:
        payload = await self.storage.read()
        filtered = [item for item in payload if str(item.get("id")) != account_id]
        if len(filtered) == len(payload):
            raise NotFoundError(f"Account '{account_id}' not found.")
        await self.storage.write(filtered)
        account_dir = self.accounts_dir / account_id
        if account_dir.exists():
            shutil.rmtree(account_dir)
        LOGGER.info("Deleted account %s", account_id)

    async def set_status(self, account_id: str, status: str) -> AccountRead:
        payload = await self.storage.read()
        updated_record: dict | None = None
        for item in payload:
            if str(item.get("id")) != account_id:
                continue
            item["status"] = status
            item["updated_at"] = datetime.now(UTC).isoformat()
            if status == "started":
                item["last_run"] = datetime.now().isoformat(timespec="seconds")
            updated_record = item
            break
        if updated_record is None:
            raise NotFoundError(f"Account '{account_id}' not found.")
        await self.storage.write(payload)
        LOGGER.info("Set account %s status to %s", account_id, status)
        return await self._to_model(updated_record)

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
        channel_templates = []
        if self.channel_template_service is not None and account_id:
            channel_templates = await self.channel_template_service.list_template_summaries(account_id)
        return AccountRead(
            id=account_id,
            name=str(item.get("name") or "").strip(),
            phone=phone,
            path=str(item.get("path") or "").strip(),
            branch=str(item.get("branch") or "main").strip() or "main",
            open_browser=bool(item.get("open_browser", False)),
            timer_minutes=int(item.get("timer_minutes", 5)),
            channel_links=item.get("channel_links") or [],
            status="started" if str(item.get("status")).strip().lower() in {"started", "running"} else "stopped",
            last_run=item.get("last_run"),
            errors=int(item.get("errors", 0)),
            telegram_session_exists=self.session_file(account_id).exists(),
            api_credentials_configured=self.credentials_file(account_id).exists(),
            created_at=self._parse_datetime(item.get("created_at")),
            updated_at=self._parse_datetime(item.get("updated_at")),
            channel_templates=channel_templates,
            extra=extra,
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
