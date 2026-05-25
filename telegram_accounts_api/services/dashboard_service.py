from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable, Literal

from telegram_accounts_api.models.account import AccountRead
from telegram_accounts_api.models.dashboard import (
    DashboardSeriesPointRead,
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


@dataclass(frozen=True)
class _HistoryAggregateCacheEntry:
    signature: tuple[int, int] | None
    earliest_entry_date: date | None
    daily_totals: dict[date, dict[str, int]]
    recent_entry_keys: set[tuple[str, str, str]]


class DashboardService:
    def __init__(
        self,
        account_service: AccountService,
        log_store: AccountLogStore,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.account_service = account_service
        self.log_store = log_store
        self.now_provider = now_provider or self._default_now
        self._history_cache: dict[
            tuple[str, str],
            _HistoryAggregateCacheEntry,
        ] = {}

    async def get_summary(
        self,
        *,
        period: DashboardPeriod = "all",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DashboardSummaryRead:
        accounts = await self.account_service.list_accounts()
        current_time = self.now_provider().astimezone()
        local_tz = current_time.tzinfo or UTC
        generated_at = current_time.astimezone(local_tz)
        account_daily_totals: dict[str, dict[date, dict[str, int]]] = {}
        earliest_entry_date: date | None = None

        for account in accounts:
            runtime_entries = self.log_store.list_entries(
                account.id,
                limit=self.log_store.max_entries_per_account,
            )
            account_earliest_date, daily_totals = self._load_account_daily_totals(
                account.id,
                runtime_entries=runtime_entries,
                local_tz=local_tz,
            )
            account_daily_totals[account.id] = daily_totals

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

        return DashboardSummaryRead(
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
        )

    def _load_account_daily_totals(
        self,
        account_id: str,
        *,
        runtime_entries: list[AccountLogEntry],
        local_tz,
    ) -> tuple[date | None, dict[date, dict[str, int]]]:
        history = self._load_cached_history_aggregate(
            account_id,
            local_tz=local_tz,
            runtime_entries=runtime_entries,
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

        return earliest_entry_date, daily_totals

    def _load_cached_history_aggregate(
        self,
        account_id: str,
        *,
        local_tz,
        runtime_entries: list[AccountLogEntry],
    ) -> _HistoryAggregateCacheEntry:
        log_file = self.account_service.account_dir(account_id) / "logs" / "app.log"
        signature = self._get_log_file_signature(log_file)
        cache_key = (account_id, str(local_tz))
        cached = self._history_cache.get(cache_key)
        if cached is not None and cached.signature == signature:
            return cached

        recent_entry_key_limit = max(self.log_store.max_entries_per_account * 2, 200)
        earliest_entry_date, daily_totals, recent_entry_keys = self._scan_log_history(
            log_file,
            local_tz=local_tz,
            recent_entry_key_limit=recent_entry_key_limit,
        )
        cache_entry = _HistoryAggregateCacheEntry(
            signature=signature,
            earliest_entry_date=earliest_entry_date,
            daily_totals=daily_totals,
            recent_entry_keys=recent_entry_keys,
        )
        self._history_cache[cache_key] = cache_entry
        return cache_entry

    def _find_runtime_keys_in_history(
        self,
        account_id: str,
        *,
        runtime_entries: list[AccountLogEntry],
        local_tz,
    ) -> set[tuple[str, str, str]]:
        if not runtime_entries:
            return set()
        history = self._load_cached_history_aggregate(
            account_id,
            local_tz=local_tz,
            runtime_entries=runtime_entries,
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
    ) -> tuple[date | None, dict[date, dict[str, int]], set[tuple[str, str, str]]]:
        if not log_file.exists() or not log_file.is_file():
            return None, {}, set()

        earliest_entry_date: date | None = None
        daily_totals: dict[date, dict[str, int]] = {}
        recent_entry_keys_queue: deque[tuple[str, str, str]] = deque(
            maxlen=max(1, recent_entry_key_limit)
        )

        with log_file.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
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

        return earliest_entry_date, daily_totals, set(recent_entry_keys_queue)

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
