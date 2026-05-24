from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from shafa_logic.utils.proxy import (
    DEFAULT_PROXY_MAX_ACCOUNTS,
    PROXY_STATUS_UNKNOWN,
    RuntimeProxyConfig,
    compute_proxy_status,
    delete_runtime_proxy_config,
    ensure_proxy_database_schema,
    write_runtime_proxy_config,
)
from telegram_accounts_api.models.proxy import ProxyCreate, ProxyRead, ProxySummary, ProxyUpdate
from telegram_accounts_api.utils.exceptions import BadRequestError, ConflictError, NotFoundError
from telegram_accounts_api.utils.storage import read_json_list_file


class ProxyService:
    def __init__(self, db_path: Path, accounts_file: Path, accounts_dir: Path) -> None:
        self.db_path = db_path
        self.accounts_file = accounts_file
        self.accounts_dir = accounts_dir
        ensure_proxy_database_schema(self.db_path)

    def list_proxies(self) -> list[ProxyRead]:
        assigned_counts = self._assigned_counts()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    name,
                    scheme,
                    host,
                    port,
                    username,
                    password,
                    max_accounts,
                    enabled,
                    notes,
                    status,
                    total_requests,
                    total_failures,
                    consecutive_failures,
                    last_used_at,
                    last_success_at,
                    last_failure_at,
                    created_at,
                    updated_at
                FROM proxies
                ORDER BY LOWER(name) ASC, created_at ASC
                """
            ).fetchall()
        return [self._row_to_model(row, assigned_counts) for row in rows]

    def get_proxy(self, proxy_id: str) -> ProxyRead:
        return self._row_to_model(
            self._get_row(proxy_id),
            self._assigned_counts(),
        )

    def get_proxy_summary(self, proxy_id: str | None) -> ProxySummary | None:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        if normalized_proxy_id is None:
            return None
        row = self._get_row(normalized_proxy_id)
        assigned_counts = self._assigned_counts()
        return ProxySummary(
            id=str(row["id"]),
            name=str(row["name"]),
            scheme=str(row["scheme"]),
            status=str(row["status"] or PROXY_STATUS_UNKNOWN),
            assigned_accounts_count=assigned_counts.get(normalized_proxy_id, 0),
            max_accounts=int(row["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS),
            enabled=bool(row["enabled"]),
        )

    def create_proxy(self, data: ProxyCreate) -> ProxyRead:
        proxy_id = uuid4().hex
        timestamp = self._now_iso()
        status = compute_proxy_status(
            enabled=data.enabled,
            consecutive_failures=0,
            total_requests=0,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO proxies (
                    id,
                    name,
                    scheme,
                    host,
                    port,
                    username,
                    password,
                    max_accounts,
                    enabled,
                    notes,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proxy_id,
                    data.name,
                    data.scheme,
                    data.host,
                    data.port,
                    data.username,
                    data.password,
                    data.max_accounts,
                    1 if data.enabled else 0,
                    data.notes,
                    status,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_proxy(proxy_id)

    def update_proxy(self, proxy_id: str, data: ProxyUpdate) -> ProxyRead:
        row = self._get_row(proxy_id)
        payload = dict(row)
        for field_name in (
            "name",
            "scheme",
            "host",
            "port",
            "username",
            "password",
            "max_accounts",
            "enabled",
            "notes",
        ):
            if field_name in data.model_fields_set:
                payload[field_name] = getattr(data, field_name)
        self._validate_existing_assignments(
            self._normalize_proxy_id(proxy_id),
            max_accounts=int(payload["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS),
            scheme=str(payload["scheme"]),
        )
        payload["status"] = compute_proxy_status(
            enabled=bool(payload["enabled"]),
            consecutive_failures=int(payload.get("consecutive_failures") or 0),
            total_requests=int(payload.get("total_requests") or 0),
        )
        payload["updated_at"] = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE proxies
                SET name = ?,
                    scheme = ?,
                    host = ?,
                    port = ?,
                    username = ?,
                    password = ?,
                    max_accounts = ?,
                    enabled = ?,
                    notes = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["name"],
                    payload["scheme"],
                    payload["host"],
                    payload["port"],
                    payload["username"] or "",
                    payload["password"] or "",
                    int(payload["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS),
                    1 if payload["enabled"] else 0,
                    payload["notes"] or "",
                    payload["status"],
                    payload["updated_at"],
                    self._normalize_proxy_id(proxy_id),
                ),
            )
        self.sync_proxy_snapshots(self._normalize_proxy_id(proxy_id))
        return self.get_proxy(proxy_id)

    def delete_proxy(self, proxy_id: str) -> None:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        assigned_count = self._assigned_counts().get(normalized_proxy_id or "", 0)
        if assigned_count > 0:
            raise ConflictError(
                "Proxy is assigned to one or more accounts. Unassign it before deletion.",
            )
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM proxies WHERE id = ?", (normalized_proxy_id,))
        if cursor.rowcount == 0:
            raise NotFoundError(f"Proxy '{proxy_id}' not found.")

    def ensure_account_proxy_assignment(
        self,
        proxy_id: str | None,
        *,
        account_id: str | None = None,
        requires_telegram: bool = False,
    ) -> None:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        if normalized_proxy_id is None:
            return
        row = self._get_row(normalized_proxy_id)
        if not bool(row["enabled"]):
            raise BadRequestError("Assigned proxy is disabled.")
        assigned_count = self._assigned_counts(excluding_account_id=account_id).get(
            normalized_proxy_id,
            0,
        )
        if assigned_count >= int(row["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS):
            raise ConflictError(
                "Assigned proxy has reached the maximum number of linked accounts.",
            )
        if requires_telegram and str(row["scheme"]) == "https":
            raise BadRequestError(
                "HTTPS proxies are not supported for Telegram connections. "
                "Use an HTTP or SOCKS5 proxy for accounts with Telegram traffic.",
            )

    def sync_account_proxy_snapshot(self, account_payload: dict[str, Any]) -> None:
        account_id = str(account_payload.get("id") or "").strip()
        if not account_id:
            return
        snapshot_path = self.proxy_config_path(account_id)
        normalized_proxy_id = self._normalize_proxy_id(account_payload.get("proxy_id"))
        if normalized_proxy_id is None:
            delete_runtime_proxy_config(snapshot_path)
            return
        row = self._get_row(normalized_proxy_id)
        config = RuntimeProxyConfig.from_payload(
            {
                "id": row["id"],
                "name": row["name"],
                "scheme": row["scheme"],
                "host": row["host"],
                "port": row["port"],
                "username": row["username"] or "",
                "password": row["password"] or "",
                "enabled": bool(row["enabled"]),
                "max_accounts": int(row["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS),
            }
        )
        write_runtime_proxy_config(snapshot_path, config.to_payload())

    def sync_proxy_snapshots(self, proxy_id: str | None) -> None:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        if normalized_proxy_id is None:
            return
        for item in read_json_list_file(self.accounts_file):
            if self._normalize_proxy_id(item.get("proxy_id")) != normalized_proxy_id:
                continue
            self.sync_account_proxy_snapshot(item)

    def proxy_config_path(self, account_id: str) -> Path:
        return self.accounts_dir / account_id / "proxy.json"

    def _validate_existing_assignments(
        self,
        proxy_id: str | None,
        *,
        max_accounts: int,
        scheme: str,
    ) -> None:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        if normalized_proxy_id is None:
            return
        assigned_accounts = self._assigned_account_payloads(normalized_proxy_id)
        if len(assigned_accounts) > max_accounts:
            raise ConflictError(
                "Proxy max_accounts cannot be lower than the current number of assigned accounts.",
            )
        if scheme == "https":
            for item in assigned_accounts:
                if item.get("channel_links"):
                    raise BadRequestError(
                        "HTTPS proxies are not supported for Telegram-linked accounts. "
                        "Reassign those accounts or switch the proxy to HTTP/SOCKS5.",
                    )

    def _assigned_counts(
        self,
        *,
        excluding_account_id: str | None = None,
    ) -> dict[str, int]:
        normalized_excluding_account_id = str(excluding_account_id or "").strip()
        counts: dict[str, int] = {}
        for item in read_json_list_file(self.accounts_file):
            if normalized_excluding_account_id and str(item.get("id") or "") == normalized_excluding_account_id:
                continue
            proxy_id = self._normalize_proxy_id(item.get("proxy_id"))
            if proxy_id is None:
                continue
            counts[proxy_id] = counts.get(proxy_id, 0) + 1
        return counts

    def _assigned_account_payloads(self, proxy_id: str) -> list[dict[str, Any]]:
        return [
            item
            for item in read_json_list_file(self.accounts_file)
            if self._normalize_proxy_id(item.get("proxy_id")) == proxy_id
        ]

    def _get_row(self, proxy_id: str | None) -> sqlite3.Row:
        normalized_proxy_id = self._normalize_proxy_id(proxy_id)
        if normalized_proxy_id is None:
            raise NotFoundError("Proxy ID is required.")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    name,
                    scheme,
                    host,
                    port,
                    username,
                    password,
                    max_accounts,
                    enabled,
                    notes,
                    status,
                    total_requests,
                    total_failures,
                    consecutive_failures,
                    last_used_at,
                    last_success_at,
                    last_failure_at,
                    created_at,
                    updated_at
                FROM proxies
                WHERE id = ?
                """,
                (normalized_proxy_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Proxy '{proxy_id}' not found.")
        return row

    def _row_to_model(
        self,
        row: sqlite3.Row,
        assigned_counts: dict[str, int],
    ) -> ProxyRead:
        return ProxyRead(
            id=str(row["id"]),
            name=str(row["name"]),
            scheme=str(row["scheme"]),
            host=str(row["host"]),
            port=int(row["port"]),
            username=str(row["username"] or ""),
            password=str(row["password"] or ""),
            max_accounts=int(row["max_accounts"] or DEFAULT_PROXY_MAX_ACCOUNTS),
            enabled=bool(row["enabled"]),
            notes=str(row["notes"] or ""),
            status=str(row["status"] or PROXY_STATUS_UNKNOWN),
            assigned_accounts_count=assigned_counts.get(str(row["id"]), 0),
            total_requests=int(row["total_requests"] or 0),
            total_failures=int(row["total_failures"] or 0),
            consecutive_failures=int(row["consecutive_failures"] or 0),
            last_used_at=self._parse_datetime(row["last_used_at"]),
            last_success_at=self._parse_datetime(row["last_success_at"]),
            last_failure_at=self._parse_datetime(row["last_failure_at"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _normalize_proxy_id(proxy_id: object) -> str | None:
        normalized = str(proxy_id or "").strip()
        return normalized or None

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().replace(tzinfo=None).isoformat()
