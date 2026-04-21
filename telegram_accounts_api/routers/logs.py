from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from telegram_accounts_api.dependencies import get_account_log_store, get_account_service
from telegram_accounts_api.models.common import ActionResponse
from telegram_accounts_api.models.logs import AccountLogEntryRead
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.account_logging import (
    AccountLogStore,
    filter_account_log_entries,
    load_account_log_file_entries,
    merge_account_log_entries,
)
from telegram_accounts_api.utils.exceptions import BadRequestError

router = APIRouter(tags=["logs"])


@router.get("/accounts/{account_id}/logs", response_model=list[AccountLogEntryRead])
async def get_account_logs(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    level: str | None = Query(default=None),
    since: str | None = Query(default=None),
    service: AccountService = Depends(get_account_service),
    store: AccountLogStore = Depends(get_account_log_store),
) -> list[AccountLogEntryRead]:
    await service.get_account(account_id)
    since_index, since_timestamp = _parse_since(since)
    history_entries = load_account_log_file_entries(
        account_id,
        service.account_dir(account_id) / "logs" / "app.log",
    )
    runtime_entries = store.list_entries(
        account_id,
        limit=store.max_entries_per_account,
    )
    entries = filter_account_log_entries(
        merge_account_log_entries(history_entries, runtime_entries),
        limit=limit,
        level=level,
        since_index=since_index,
        since_timestamp=since_timestamp,
        max_entries=store.max_entries_per_account,
    )
    return [
        AccountLogEntryRead(
            index=entry.index,
            account_id=entry.account_id,
            timestamp=entry.timestamp,
            level=entry.level,
            message=entry.message,
        )
        for entry in entries
    ]


@router.post("/logs/clear", response_model=ActionResponse)
async def clear_logs(
    service: AccountService = Depends(get_account_service),
    store: AccountLogStore = Depends(get_account_log_store),
) -> ActionResponse:
    removed_files = 0
    removed_files += _clear_log_directory(service.log_store.root_dir)

    accounts = await service.list_accounts()
    for account in accounts:
        removed_files += _clear_log_directory(service.account_dir(account.id) / "logs")

    service.log_store.replace([])
    store.clear_entries()

    if removed_files == 0:
        return ActionResponse(detail="Логи уже пусты.")

    return ActionResponse(detail=f"Логи очищены. Удалено файлов: {removed_files}.")


@router.websocket("/ws/logs/{account_id}")
async def stream_account_logs(
    websocket: WebSocket,
    account_id: str,
    service: AccountService = Depends(get_account_service),
    store: AccountLogStore = Depends(get_account_log_store),
) -> None:
    try:
        await service.get_account(account_id)
    except Exception:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    subscription_id, queue = store.subscribe(account_id)
    try:
        while True:
            entry = await queue.get()
            await websocket.send_json(
                {
                    "index": entry.index,
                    "account_id": entry.account_id,
                    "timestamp": entry.timestamp.isoformat(),
                    "level": entry.level,
                    "message": entry.message,
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(account_id, subscription_id)


def _parse_since(value: str | None) -> tuple[int | None, datetime | None]:
    if value is None or not value.strip():
        return None, None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped), None
    normalized = stripped.replace("Z", "+00:00")
    try:
        return None, datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BadRequestError("Query param 'since' must be a log index or ISO-8601 timestamp.") from exc


def _clear_log_directory(log_dir: Path) -> int:
    if not log_dir.exists() or not log_dir.is_dir():
        return 0

    removed_files = 0

    for path in sorted(log_dir.rglob("*"), reverse=True):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed_files += 1
            elif path.is_dir():
                path.rmdir()
        except OSError:
            continue

    return removed_files
