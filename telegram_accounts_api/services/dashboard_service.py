from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Callable, Literal

from telegram_accounts_api.models.account import AccountRead
from telegram_accounts_api.models.dashboard import (
    DashboardSeriesPointRead,
    DashboardSummaryRead,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.account_logging import (
    AccountLogStore,
    merge_account_log_entries,
    normalize_log_timestamp,
    load_account_log_file_entries,
)

_PRODUCT_SUCCESS_PATTERN = re.compile(r"товар создан успешно", re.IGNORECASE)
DashboardPeriod = Literal["all", "week", "month", "quarter", "custom"]
_DASHBOARD_PERIOD_DAYS: dict[DashboardPeriod, int] = {
    "all": 0,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "custom": 0,
}


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
        account_entries: dict[str, list] = {}
        earliest_entry_date: date | None = None

        for account in accounts:
            entries = list(self._load_account_entries(account.id))
            account_entries[account.id] = entries

            if period != "all":
                continue

            for entry in entries:
                entry_time = normalize_log_timestamp(entry.timestamp).astimezone(local_tz)
                entry_date = entry_time.date()
                if earliest_entry_date is None or entry_date < earliest_entry_date:
                    earliest_entry_date = entry_date

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

            for entry in account_entries[account.id]:
                entry_time = normalize_log_timestamp(entry.timestamp).astimezone(local_tz)
                entry_date = entry_time.date()

                if entry_date not in series_totals:
                    continue

                if self._is_product_success(entry.message):
                    series_totals[entry_date]["items"] += 1
                if entry.level.upper() == "ERROR":
                    series_totals[entry_date]["errors"] += 1

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

    def _load_account_entries(self, account_id: str):
        history_entries = load_account_log_file_entries(
            account_id,
            self.account_service.account_dir(account_id) / "logs" / "app.log",
        )
        runtime_entries = self.log_store.list_entries(
            account_id,
            limit=self.log_store.max_entries_per_account,
        )
        return merge_account_log_entries(history_entries, runtime_entries)

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
