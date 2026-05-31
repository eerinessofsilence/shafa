from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable, Literal

from telegram_accounts_api.models.account import AccountRead
from telegram_accounts_api.models.dashboard import (
    DashboardRecentSharedDeactivationRead,
    DashboardSeriesPointRead,
    DashboardSharedDeactivationAccountRead,
    DashboardSharedDeactivationSummaryRead,
    DashboardSummaryRead,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.account_logging import (
    AccountLogEntry,
    AccountLogStore,
    normalize_log_level,
    normalize_log_message,
    normalize_log_timestamp,
)

LOGGER = logging.getLogger(__name__)
_PRODUCT_SUCCESS_PATTERN = re.compile(r"товар создан успешно", re.IGNORECASE)
_RENDERED_LOG_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+\[(?P<level>[^\]]+)\](?:\s+\[(?P<account_name>[^\]]+)\])?\s+(?P<message>.*)$"
)
DashboardPeriod = Literal["all", "week", "month", "quarter", "custom"]
_DASHBOARD_PERIOD_DAYS: dict[DashboardPeriod, int] = {
    "all": 0,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "custom": 0,
}
SHARED_ACCOUNT_TASK_COMPLETED = "completed"
SHARED_ACCOUNT_TASK_FAILED = "failed"
SHARED_ACCOUNT_TASK_PENDING = "pending"
SHARED_ACCOUNT_TASK_RETRY_SCHEDULED = "retry_scheduled"
SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND = "skipped_not_found"
DEFAULT_DASHBOARD_LOG_HISTORY_LINES = 500
MAX_DASHBOARD_LOG_HISTORY_LINES = 50_000


@dataclass(frozen=True)
class _HistoryAggregateCacheEntry:
    signature: tuple[int, int] | None
    earliest_entry_date: date | None
    daily_totals: dict[date, dict[str, int]]
    recent_entry_keys: set[tuple[str, str, str]]
    scanned_lines: int


@dataclass(frozen=True)
class _DashboardSummaryCacheEntry:
    expires_at: float
    summary: DashboardSummaryRead


@dataclass(frozen=True)
class _SharedDeactivationCacheEntry:
    expires_at: float
    signature: tuple[int, int] | None
    summary: DashboardSharedDeactivationSummaryRead


class DashboardService:
    def __init__(
        self,
        account_service: AccountService,
        log_store: AccountLogStore,
        *,
        now_provider: Callable[[], datetime] | None = None,
        history_line_limit: int | None = None,
        summary_cache_ttl_seconds: float | None = None,
        deactivation_cache_ttl_seconds: float | None = None,
    ) -> None:
        self.account_service = account_service
        self.log_store = log_store
        self.now_provider = now_provider or self._default_now
        self.history_line_limit = (
            self._resolve_history_line_limit()
            if history_line_limit is None
            else self._bound_history_line_limit(history_line_limit)
        )
        self.summary_cache_ttl_seconds = (
            self._resolve_summary_cache_ttl_seconds()
            if summary_cache_ttl_seconds is None
            else max(float(summary_cache_ttl_seconds), 0.0)
        )
        self.deactivation_cache_ttl_seconds = (
            self._resolve_deactivation_cache_ttl_seconds()
            if deactivation_cache_ttl_seconds is None
            else max(float(deactivation_cache_ttl_seconds), 0.0)
        )
        self._history_cache: dict[
            tuple[str, str],
            _HistoryAggregateCacheEntry,
        ] = {}
        self._summary_cache: dict[
            tuple[DashboardPeriod, str | None, str | None, int],
            _DashboardSummaryCacheEntry,
        ] = {}
        self._shared_deactivation_cache: dict[
            tuple[str, int],
            _SharedDeactivationCacheEntry,
        ] = {}
        self._dashboard_indexed_paths: set[str] = set()

    async def get_summary(
        self,
        *,
        period: DashboardPeriod = "all",
        date_from: date | None = None,
        date_to: date | None = None,
        history_line_limit: int | None = None,
    ) -> DashboardSummaryRead:
        started_at = time.perf_counter()
        monotonic_started_at = time.monotonic()
        effective_history_line_limit = (
            self.history_line_limit
            if history_line_limit is None
            else self._bound_history_line_limit(history_line_limit)
        )
        cache_key = (
            period,
            date_from.isoformat() if date_from is not None else None,
            date_to.isoformat() if date_to is not None else None,
            effective_history_line_limit,
        )
        cached = self._summary_cache.get(cache_key)
        if (
            cached is not None
            and self.summary_cache_ttl_seconds > 0
            and cached.expires_at > monotonic_started_at
        ):
            LOGGER.info(
                "dashboard summary cache hit period=%s history_line_limit=%s "
                "duration_ms=%s",
                period,
                effective_history_line_limit,
                round((time.perf_counter() - started_at) * 1000),
            )
            return cached.summary

        account_list_started_at = time.perf_counter()
        accounts = await self.account_service.list_accounts()
        account_list_ms = round((time.perf_counter() - account_list_started_at) * 1000)
        current_time = self.now_provider().astimezone()
        local_tz = current_time.tzinfo or UTC
        generated_at = current_time.astimezone(local_tz)
        account_daily_totals: dict[str, dict[date, dict[str, int]]] = {}
        account_names = {account.id: account.name for account in accounts}
        earliest_entry_date: date | None = None
        total_history_lines_scanned = 0
        account_stats_ms = 0

        for account in accounts:
            account_started_at = time.perf_counter()
            runtime_entries = self.log_store.list_entries(
                account.id,
                limit=self.log_store.max_entries_per_account,
            )
            account_earliest_date, daily_totals, scanned_lines = self._load_account_daily_totals(
                account.id,
                runtime_entries=runtime_entries,
                local_tz=local_tz,
                history_line_limit=effective_history_line_limit,
            )
            account_daily_totals[account.id] = daily_totals
            total_history_lines_scanned += scanned_lines
            account_stats_ms += round((time.perf_counter() - account_started_at) * 1000)

            if (
                period == "all"
                and account_earliest_date is not None
                and (
                    earliest_entry_date is None
                    or account_earliest_date < earliest_entry_date
                )
            ):
                earliest_entry_date = account_earliest_date

        range_start, range_end = self._resolve_date_range(
            generated_at=generated_at,
            period=period,
            date_from=date_from,
            date_to=date_to,
            earliest_entry_date=earliest_entry_date,
        )
        series_dates = [
            range_start + timedelta(days=offset)
            for offset in range((range_end - range_start).days + 1)
        ]
        series_totals = {
            point_date: {"items": 0, "errors": 0}
            for point_date in series_dates
        }

        latest_run_account_name: str | None = None
        latest_run_at: datetime | None = None
        top_error_account_name: str | None = None
        top_error_account_errors = 0
        ready_accounts = 0
        attention_accounts = 0

        for account in accounts:
            if self._is_ready_account(account):
                ready_accounts += 1
            if self._needs_attention(account):
                attention_accounts += 1

            parsed_last_run = self._parse_datetime(account.last_run)
            if parsed_last_run is not None and (
                latest_run_at is None or parsed_last_run > latest_run_at
            ):
                latest_run_at = parsed_last_run
                latest_run_account_name = account.name

            if account.errors > top_error_account_errors:
                top_error_account_errors = account.errors
                top_error_account_name = account.name

            for entry_date, totals in account_daily_totals[account.id].items():
                if entry_date not in series_totals:
                    continue
                series_totals[entry_date]["items"] += totals["items"]
                series_totals[entry_date]["errors"] += totals["errors"]

        series = [
            DashboardSeriesPointRead(
                date=point_date,
                items=series_totals[point_date]["items"],
                errors=series_totals[point_date]["errors"],
            )
            for point_date in series_dates
        ]

        shared_summary_started_at = time.perf_counter()
        shared_deactivation_summary = self._load_shared_deactivation_summary(
            account_names=account_names
        )
        shared_stats_ms = round((time.perf_counter() - shared_summary_started_at) * 1000)

        summary = DashboardSummaryRead(
            generated_at=generated_at,
            range_start=range_start,
            range_end=range_end,
            total_accounts=len(accounts),
            active_accounts=sum(1 for account in accounts if account.status == "started"),
            ready_accounts=ready_accounts,
            attention_accounts=attention_accounts,
            item_successes_in_range=sum(point.items for point in series),
            error_events_in_range=sum(point.errors for point in series),
            latest_run_account_name=latest_run_account_name,
            latest_run_at=latest_run_at,
            top_error_account_name=top_error_account_name,
            top_error_account_errors=top_error_account_errors,
            series=series,
            shared_deactivation=shared_deactivation_summary,
        )
        if self.summary_cache_ttl_seconds > 0:
            self._summary_cache[cache_key] = _DashboardSummaryCacheEntry(
                expires_at=monotonic_started_at + self.summary_cache_ttl_seconds,
                summary=summary,
            )
        LOGGER.info(
            "dashboard summary loaded account_count=%s history_line_limit=%s "
            "history_lines_scanned=%s account_list_ms=%s account_stats_ms=%s "
            "shared_stats_ms=%s duration_ms=%s",
            len(accounts),
            effective_history_line_limit,
            total_history_lines_scanned,
            account_list_ms,
            account_stats_ms,
            shared_stats_ms,
            round((time.perf_counter() - started_at) * 1000),
        )
        return summary

    def _load_shared_deactivation_summary(
        self,
        *,
        account_names: dict[str, str],
        recent_limit: int = 20,
    ) -> DashboardSharedDeactivationSummaryRead:
        started_at = time.perf_counter()
        shared_counts_ms = 0
        direct_counts_ms = 0
        recent_rows_ms = 0
        db_path = self.account_service.session_store.shared_telegram_db_file()
        if not db_path.exists():
            return DashboardSharedDeactivationSummaryRead()
        cache_key = (str(db_path), max(int(recent_limit), 1))
        current_signature = self._get_log_file_signature(db_path)
        monotonic_started_at = time.monotonic()
        cached = self._shared_deactivation_cache.get(cache_key)
        if (
            cached is not None
            and self.deactivation_cache_ttl_seconds > 0
            and cached.expires_at > monotonic_started_at
            and cached.signature == current_signature
        ):
            LOGGER.info(
                "dashboard shared deactivation cache hit duration_ms=%s",
                round((time.perf_counter() - started_at) * 1000),
            )
            return cached.summary

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                shared_available = self._shared_deactivation_tables_exist(conn)
                telegram_products_available = self._tables_exist(
                    conn, {"telegram_products"}
                )
                if not shared_available and not telegram_products_available:
                    return DashboardSharedDeactivationSummaryRead()
                indexed_path = str(db_path)
                if indexed_path not in self._dashboard_indexed_paths:
                    self._ensure_dashboard_indexes(
                        conn,
                        shared_available=shared_available,
                        telegram_products_available=telegram_products_available,
                    )
                    self._dashboard_indexed_paths.add(indexed_path)

                account_rows = []
                recent_rows = []
                if shared_available:
                    shared_counts_started_at = time.perf_counter()
                    account_rows = conn.execute(
                        """
                        SELECT
                            account_id,
                            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END)
                                AS deactivated_success_count,
                            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END)
                                AS not_found_treated_as_done_count,
                            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END)
                                AS failed_count,
                            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END)
                                AS pending_count,
                            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END)
                                AS retry_scheduled_count
                        FROM shared_deactivation_task_accounts
                        GROUP BY account_id
                        ORDER BY account_id
                        """,
                        (
                            SHARED_ACCOUNT_TASK_COMPLETED,
                            SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                            SHARED_ACCOUNT_TASK_FAILED,
                            SHARED_ACCOUNT_TASK_PENDING,
                            SHARED_ACCOUNT_TASK_RETRY_SCHEDULED,
                        ),
                    ).fetchall()
                    shared_counts_ms = round(
                        (time.perf_counter() - shared_counts_started_at) * 1000
                    )
                    recent_rows_started_at = time.perf_counter()
                    recent_rows = conn.execute(
                        """
                        SELECT
                            account_task.account_id,
                            account_task.telegram_product_key,
                            product.channel_id,
                            product.message_id,
                            COALESCE(account_product.product_title, product.product_title)
                                AS product_title,
                            account_task.shafa_product_id,
                            account_task.status,
                            account_task.completed_at,
                            parent.reason,
                            account_task.last_error
                        FROM shared_deactivation_task_accounts AS account_task
                        JOIN shared_deactivation_tasks AS parent
                          ON parent.task_id = account_task.task_id
                        LEFT JOIN shared_telegram_products AS product
                          ON product.telegram_product_key = account_task.telegram_product_key
                        LEFT JOIN shared_telegram_product_accounts AS account_product
                          ON account_product.telegram_product_key = account_task.telegram_product_key
                         AND account_product.account_id = account_task.account_id
                        WHERE account_task.status IN (?, ?)
                        ORDER BY datetime(account_task.completed_at) DESC,
                                 account_task.updated_at DESC
                        LIMIT ?
                        """,
                        (
                            SHARED_ACCOUNT_TASK_COMPLETED,
                            SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                            max(int(recent_limit), 1),
                        ),
                    ).fetchall()
                    recent_rows_ms += round(
                        (time.perf_counter() - recent_rows_started_at) * 1000
                    )

                direct_account_rows = []
                direct_recent_rows = []
                if telegram_products_available:
                    direct_counts_started_at = time.perf_counter()
                    shared_dedupe = (
                        """
                        AND NOT EXISTS (
                            SELECT 1
                            FROM shared_deactivation_task_accounts AS account_task
                            WHERE account_task.account_id = telegram_products.account_id
                              AND account_task.telegram_product_key = (
                                    'tg:' || telegram_products.channel_id || ':' || telegram_products.message_id
                              )
                              AND account_task.shafa_product_id = telegram_products.created_product_id
                              AND account_task.status IN (?, ?)
                        )
                        """
                        if shared_available
                        else ""
                    )
                    shared_params = (
                        (
                            SHARED_ACCOUNT_TASK_COMPLETED,
                            SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                        )
                        if shared_available
                        else ()
                    )
                    terminal_products_cte = f"""
                        WITH terminal_products AS (
                            SELECT
                                account_id,
                                channel_id,
                                message_id,
                                parsed_data,
                                created_product_id,
                                deactivation_completed_at,
                                shafa_deactivated_at,
                                shafa_deleted_at,
                                updated_at,
                                deactivation_error,
                                ? AS terminal_status,
                                1 AS success_count,
                                0 AS not_found_count
                            FROM telegram_products
                            WHERE deactivation_status = ?
                              AND shafa_deactivated_at IS NOT NULL
                              {shared_dedupe}
                            UNION ALL
                            SELECT
                                account_id,
                                channel_id,
                                message_id,
                                parsed_data,
                                created_product_id,
                                deactivation_completed_at,
                                shafa_deactivated_at,
                                shafa_deleted_at,
                                updated_at,
                                deactivation_error,
                                ? AS terminal_status,
                                0 AS success_count,
                                1 AS not_found_count
                            FROM telegram_products
                            WHERE deactivation_status = ?
                              {shared_dedupe}
                            UNION ALL
                            SELECT
                                account_id,
                                channel_id,
                                message_id,
                                parsed_data,
                                created_product_id,
                                deactivation_completed_at,
                                shafa_deactivated_at,
                                shafa_deleted_at,
                                updated_at,
                                deactivation_error,
                                ? AS terminal_status,
                                0 AS success_count,
                                1 AS not_found_count
                            FROM telegram_products INDEXED BY idx_telegram_products_deactivation_deleted
                            WHERE shafa_deleted_at IS NOT NULL
                              AND shafa_deactivated_at IS NULL
                              AND (
                                    deactivation_status IS NULL
                                    OR deactivation_status != ?
                                  )
                              {shared_dedupe}
                        )
                    """
                    terminal_params = (
                        SHARED_ACCOUNT_TASK_COMPLETED,
                        SHARED_ACCOUNT_TASK_COMPLETED,
                        *shared_params,
                        SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                        SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                        *shared_params,
                        SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                        SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                        *shared_params,
                    )
                    direct_account_rows = conn.execute(
                        terminal_products_cte
                        + """
                        SELECT
                            account_id,
                            SUM(success_count) AS deactivated_success_count,
                            SUM(not_found_count) AS not_found_treated_as_done_count
                        FROM terminal_products
                        GROUP BY account_id
                        ORDER BY account_id
                        """,
                        terminal_params,
                    ).fetchall()
                    direct_counts_ms = round(
                        (time.perf_counter() - direct_counts_started_at) * 1000
                    )
                    recent_rows_started_at = time.perf_counter()
                    direct_recent_rows = conn.execute(
                        terminal_products_cte
                        + """
                        SELECT
                            account_id,
                            ('tg:' || channel_id || ':' || message_id)
                                AS telegram_product_key,
                            channel_id,
                            message_id,
                            CASE
                                WHEN json_valid(parsed_data)
                                    THEN json_extract(parsed_data, '$.name')
                                ELSE NULL
                            END AS product_title,
                            created_product_id AS shafa_product_id,
                            terminal_status AS status,
                            COALESCE(
                                deactivation_completed_at,
                                shafa_deactivated_at,
                                shafa_deleted_at,
                                updated_at
                            ) AS completed_at,
                            'old_direct' AS reason,
                            deactivation_error AS last_error
                        FROM terminal_products
                        ORDER BY datetime(completed_at) DESC, updated_at DESC
                        LIMIT ?
                        """,
                        (*terminal_params, max(int(recent_limit), 1)),
                    ).fetchall()
                    recent_rows_ms += round(
                        (time.perf_counter() - recent_rows_started_at) * 1000
                    )
        except sqlite3.Error:
            return DashboardSharedDeactivationSummaryRead()

        account_totals: dict[str, dict[str, int]] = {}
        total_success = 0
        total_not_found = 0
        for row in account_rows:
            success_count = int(row["deactivated_success_count"] or 0)
            not_found_count = int(row["not_found_treated_as_done_count"] or 0)
            account_id = str(row["account_id"] or "").strip()
            account_totals[account_id] = {
                "success": success_count,
                "not_found": not_found_count,
                "failed": int(row["failed_count"] or 0),
                "pending": int(row["pending_count"] or 0),
                "retry_scheduled": int(row["retry_scheduled_count"] or 0),
            }
        for row in direct_account_rows:
            account_id = str(row["account_id"] or "").strip()
            totals = account_totals.setdefault(
                account_id,
                {
                    "success": 0,
                    "not_found": 0,
                    "failed": 0,
                    "pending": 0,
                    "retry_scheduled": 0,
                },
            )
            totals["success"] += int(row["deactivated_success_count"] or 0)
            totals["not_found"] += int(row["not_found_treated_as_done_count"] or 0)

        per_account: list[DashboardSharedDeactivationAccountRead] = []
        for account_id, counts in account_totals.items():
            total_success += counts["success"]
            total_not_found += counts["not_found"]
            per_account.append(
                DashboardSharedDeactivationAccountRead(
                    account_id=account_id,
                    account_name=account_names.get(account_id),
                    deactivated_success_count=counts["success"],
                    not_found_treated_as_done_count=counts["not_found"],
                    total_done_count=counts["success"] + counts["not_found"],
                    failed_count=counts["failed"],
                    pending_count=counts["pending"],
                    retry_scheduled_count=counts["retry_scheduled"],
                )
            )

        per_account.sort(
            key=lambda item: (
                -item.total_done_count,
                -item.pending_count,
                item.account_name or item.account_id,
            )
        )
        recent_source_rows = sorted(
            [*recent_rows, *direct_recent_rows],
            key=lambda row: str(row["completed_at"] or ""),
            reverse=True,
        )[: max(int(recent_limit), 1)]
        recent = [
            DashboardRecentSharedDeactivationRead(
                account_id=str(row["account_id"] or ""),
                account_name=account_names.get(str(row["account_id"] or "")),
                telegram_product_key=str(row["telegram_product_key"] or ""),
                channel_id=(
                    int(row["channel_id"]) if row["channel_id"] is not None else None
                ),
                message_id=(
                    int(row["message_id"]) if row["message_id"] is not None else None
                ),
                product_title=str(row["product_title"] or "").strip() or None,
                shafa_product_id=str(row["shafa_product_id"] or ""),
                status=str(row["status"] or ""),
                completed_at=self._parse_datetime(row["completed_at"]),
                reason=str(row["reason"] or "").strip() or None,
                last_error=str(row["last_error"] or "").strip() or None,
            )
            for row in recent_source_rows
        ]

        total_done = total_success + total_not_found
        summary = DashboardSharedDeactivationSummaryRead(
            total_deactivated_products=total_done,
            deactivated_success_count=total_success,
            not_found_treated_as_done_count=total_not_found,
            total_done_count=total_done,
            per_account=per_account,
            recent=recent,
        )
        LOGGER.info(
            "dashboard shared deactivation loaded shared_counts_ms=%s "
            "direct_counts_ms=%s recent_rows_ms=%s duration_ms=%s",
            shared_counts_ms,
            direct_counts_ms,
            recent_rows_ms,
            round((time.perf_counter() - started_at) * 1000),
        )
        if self.deactivation_cache_ttl_seconds > 0:
            self._shared_deactivation_cache[cache_key] = _SharedDeactivationCacheEntry(
                expires_at=monotonic_started_at + self.deactivation_cache_ttl_seconds,
                signature=self._get_log_file_signature(db_path),
                summary=summary,
            )
        return summary

    @staticmethod
    def _shared_deactivation_tables_exist(conn: sqlite3.Connection) -> bool:
        return DashboardService._tables_exist(
            conn,
            {
                "shared_deactivation_task_accounts",
                "shared_deactivation_tasks",
                "shared_telegram_products",
                "shared_telegram_product_accounts",
            },
        )

    @staticmethod
    def _tables_exist(conn: sqlite3.Connection, table_names: set[str]) -> bool:
        if not table_names:
            return True
        placeholders = ",".join(["?"] * len(table_names))
        rows = conn.execute(
            f"""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ({placeholders})
            """,
            tuple(sorted(table_names)),
        ).fetchall()
        return {str(row["name"]) for row in rows} == set(table_names)

    @staticmethod
    def _ensure_dashboard_indexes(
        conn: sqlite3.Connection,
        *,
        shared_available: bool,
        telegram_products_available: bool,
    ) -> None:
        if telegram_products_available:
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_completed
                    ON telegram_products(
                        deactivation_status,
                        shafa_deactivated_at,
                        deactivation_completed_at,
                        updated_at,
                        account_id
                    );
                CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_skipped
                    ON telegram_products(
                        deactivation_status,
                        deactivation_completed_at,
                        updated_at,
                        account_id
                    );
                CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_deleted
                    ON telegram_products(
                        shafa_deleted_at,
                        shafa_deactivated_at,
                        deactivation_completed_at,
                        updated_at,
                        account_id
                    );
                """
            )
        if shared_available:
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_shared_task_accounts_account_status_completed
                    ON shared_deactivation_task_accounts(
                        account_id,
                        status,
                        completed_at,
                        updated_at
                    );
                CREATE INDEX IF NOT EXISTS idx_shared_task_accounts_status_completed
                    ON shared_deactivation_task_accounts(
                        status,
                        completed_at,
                        updated_at
                    );
                """
            )

    def _load_account_daily_totals(
        self,
        account_id: str,
        *,
        runtime_entries: list[AccountLogEntry],
        local_tz,
        history_line_limit: int,
    ) -> tuple[date | None, dict[date, dict[str, int]], int]:
        history = self._load_cached_history_aggregate(
            account_id,
            local_tz=local_tz,
            runtime_entries=runtime_entries,
            history_line_limit=history_line_limit,
        )
        daily_totals = {
            point_date: totals.copy()
            for point_date, totals in history.daily_totals.items()
        }
        earliest_entry_date = history.earliest_entry_date
        runtime_keys_matched_in_history = self._find_runtime_keys_in_history(
            account_id,
            runtime_entries=runtime_entries,
            local_tz=local_tz,
            history_line_limit=history_line_limit,
        )

        for entry in runtime_entries:
            entry_key = self._build_entry_dedupe_key(entry)
            if entry_key in runtime_keys_matched_in_history:
                continue
            entry_date = normalize_log_timestamp(entry.timestamp).astimezone(local_tz).date()
            totals = daily_totals.setdefault(entry_date, {"items": 0, "errors": 0})
            if self._is_product_success(entry.message):
                totals["items"] += 1
            if entry.level.upper() == "ERROR":
                totals["errors"] += 1
            if earliest_entry_date is None or entry_date < earliest_entry_date:
                earliest_entry_date = entry_date

        return earliest_entry_date, daily_totals, history.scanned_lines

    def _load_cached_history_aggregate(
        self,
        account_id: str,
        *,
        local_tz,
        runtime_entries: list[AccountLogEntry],
        history_line_limit: int,
    ) -> _HistoryAggregateCacheEntry:
        log_file = self.account_service.account_dir(account_id) / "logs" / "app.log"
        signature = self._get_log_file_signature(log_file)
        cache_key = (account_id, f"{local_tz}:{history_line_limit}")
        cached = self._history_cache.get(cache_key)
        if cached is not None and cached.signature == signature:
            return cached

        recent_entry_key_limit = max(self.log_store.max_entries_per_account * 2, 200)
        (
            earliest_entry_date,
            daily_totals,
            recent_entry_keys,
            scanned_lines,
        ) = self._scan_log_history(
            log_file,
            local_tz=local_tz,
            recent_entry_key_limit=recent_entry_key_limit,
            history_line_limit=history_line_limit,
        )
        cache_entry = _HistoryAggregateCacheEntry(
            signature=signature,
            earliest_entry_date=earliest_entry_date,
            daily_totals=daily_totals,
            recent_entry_keys=recent_entry_keys,
            scanned_lines=scanned_lines,
        )
        self._history_cache[cache_key] = cache_entry
        return cache_entry

    def _find_runtime_keys_in_history(
        self,
        account_id: str,
        *,
        runtime_entries: list[AccountLogEntry],
        local_tz,
        history_line_limit: int,
    ) -> set[tuple[str, str, str]]:
        if not runtime_entries:
            return set()
        history = self._load_cached_history_aggregate(
            account_id,
            local_tz=local_tz,
            runtime_entries=runtime_entries,
            history_line_limit=history_line_limit,
        )
        matched_keys: set[tuple[str, str, str]] = set()
        for entry in runtime_entries:
            entry_key = self._build_entry_dedupe_key(entry)
            if entry_key in history.recent_entry_keys:
                matched_keys.add(entry_key)
        return matched_keys

    def _scan_log_history(
        self,
        log_file: Path,
        *,
        local_tz,
        recent_entry_key_limit: int,
        history_line_limit: int,
    ) -> tuple[date | None, dict[date, dict[str, int]], set[tuple[str, str, str]], int]:
        if not log_file.exists() or not log_file.is_file():
            return None, {}, set(), 0

        earliest_entry_date: date | None = None
        daily_totals: dict[date, dict[str, int]] = {}
        recent_entry_keys_queue: deque[tuple[str, str, str]] = deque(
            maxlen=max(1, recent_entry_key_limit)
        )
        scanned_lines = 0

        try:
            raw_lines = self._read_log_tail_lines(
                log_file,
                limit=history_line_limit,
            )
        except OSError:
            return None, {}, set(), 0

        for raw_line in raw_lines:
            scanned_lines += 1
            match = _RENDERED_LOG_PATTERN.match(raw_line.strip())
            if not match:
                continue
            try:
                timestamp = normalize_log_timestamp(
                    datetime.strptime(
                        match.group("timestamp"),
                        "%Y-%m-%d %H:%M:%S",
                    )
                )
            except ValueError:
                continue

            level = normalize_log_level(match.group("level"))
            message = normalize_log_message(match.group("message") or "")
            entry_key = (
                timestamp.replace(microsecond=0).isoformat(),
                level,
                message,
            )
            recent_entry_keys_queue.append(entry_key)

            entry_date = timestamp.astimezone(local_tz).date()
            if earliest_entry_date is None or entry_date < earliest_entry_date:
                earliest_entry_date = entry_date
            totals = daily_totals.setdefault(entry_date, {"items": 0, "errors": 0})
            if self._is_product_success(message):
                totals["items"] += 1
            if level == "ERROR":
                totals["errors"] += 1

        return earliest_entry_date, daily_totals, set(recent_entry_keys_queue), scanned_lines

    @staticmethod
    def _read_log_tail_lines(log_file: Path, *, limit: int) -> list[str]:
        bounded_limit = max(1, int(limit))
        chunk_size = 64 * 1024
        buffer = bytearray()
        newline_count = 0

        with log_file.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()

            while position > 0 and newline_count <= bounded_limit:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                chunk = handle.read(read_size)
                buffer[:0] = chunk
                newline_count = buffer.count(b"\n")

        return buffer.decode("utf-8", errors="replace").splitlines()[-bounded_limit:]

    @classmethod
    def _resolve_history_line_limit(cls) -> int:
        raw = os.getenv("SHAFA_DASHBOARD_LOG_HISTORY_LINES", "").strip()
        if not raw:
            return DEFAULT_DASHBOARD_LOG_HISTORY_LINES
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_DASHBOARD_LOG_HISTORY_LINES
        return cls._bound_history_line_limit(value)

    @staticmethod
    def _bound_history_line_limit(value: int) -> int:
        return min(max(int(value), 1), MAX_DASHBOARD_LOG_HISTORY_LINES)

    @staticmethod
    def _resolve_summary_cache_ttl_seconds() -> float:
        raw = os.getenv("SHAFA_DASHBOARD_SUMMARY_CACHE_SECONDS", "").strip()
        if not raw:
            return 5.0
        try:
            value = float(raw)
        except ValueError:
            return 5.0
        return min(max(value, 0.0), 60.0)

    @staticmethod
    def _resolve_deactivation_cache_ttl_seconds() -> float:
        raw = os.getenv("SHAFA_DASHBOARD_DEACTIVATION_CACHE_SECONDS", "").strip()
        if not raw:
            return 15.0
        try:
            value = float(raw)
        except ValueError:
            return 15.0
        return min(max(value, 0.0), 120.0)

    @staticmethod
    def _get_log_file_signature(log_file: Path) -> tuple[int, int] | None:
        if not log_file.exists() or not log_file.is_file():
            return None
        stat = log_file.stat()
        return stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _build_entry_dedupe_key(entry: AccountLogEntry) -> tuple[str, str, str]:
        return (
            normalize_log_timestamp(entry.timestamp).replace(microsecond=0).isoformat(),
            entry.level,
            entry.message,
        )

    @staticmethod
    def _default_now() -> datetime:
        return datetime.now().astimezone()

    @staticmethod
    def _resolve_date_range(
        *,
        generated_at: datetime,
        period: DashboardPeriod,
        date_from: date | None,
        date_to: date | None,
        earliest_entry_date: date | None,
    ) -> tuple[date, date]:
        if period == "custom":
            if date_from is None or date_to is None:
                raise ValueError("Для кастомного диапазона укажи обе даты.")
            if date_from > date_to:
                raise ValueError("Дата начала не может быть позже даты окончания.")
            return date_from, date_to

        if period == "all":
            range_end = generated_at.date()
            if earliest_entry_date is None:
                return range_end, range_end
            return min(earliest_entry_date, range_end), range_end

        range_end = generated_at.date()
        range_days = _DASHBOARD_PERIOD_DAYS[period]
        range_start = range_end - timedelta(days=range_days - 1)
        return range_start, range_end

    @staticmethod
    def _is_product_success(message: str) -> bool:
        return bool(_PRODUCT_SUCCESS_PATTERN.search(str(message)))

    @staticmethod
    def _is_ready_account(account: AccountRead) -> bool:
        return (
            account.shafa_session_exists
            and account.telegram_session_exists
            and account.api_credentials_configured
        )

    @staticmethod
    def _needs_attention(account: AccountRead) -> bool:
        return account.errors > 0 or not DashboardService._is_ready_account(account)

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return normalize_log_timestamp(value)
        text = str(value).strip()
        if not text or text == "—":
            return None
        try:
            return normalize_log_timestamp(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None
