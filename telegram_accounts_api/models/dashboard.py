from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DashboardSeriesPointRead(BaseModel):
    date: date
    items: int = 0
    errors: int = 0


class DashboardSharedDeactivationAccountRead(BaseModel):
    account_id: str
    account_name: str | None = None
    deactivated_success_count: int = 0
    not_found_treated_as_done_count: int = 0
    total_done_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    retry_scheduled_count: int = 0


class DashboardRecentSharedDeactivationRead(BaseModel):
    account_id: str
    account_name: str | None = None
    telegram_product_key: str
    channel_id: int | None = None
    message_id: int | None = None
    product_title: str | None = None
    shafa_product_id: str
    status: str
    completed_at: datetime | None = None
    reason: str | None = None
    last_error: str | None = None


class DashboardSharedDeactivationSummaryRead(BaseModel):
    total_deactivated_products: int = 0
    deactivated_success_count: int = 0
    not_found_treated_as_done_count: int = 0
    total_done_count: int = 0
    per_account: list[DashboardSharedDeactivationAccountRead] = Field(
        default_factory=list
    )
    recent: list[DashboardRecentSharedDeactivationRead] = Field(default_factory=list)


class DashboardSummaryRead(BaseModel):
    generated_at: datetime
    range_start: date
    range_end: date
    total_accounts: int = 0
    active_accounts: int = 0
    ready_accounts: int = 0
    attention_accounts: int = 0
    item_successes_in_range: int = 0
    error_events_in_range: int = 0
    latest_run_account_name: str | None = None
    latest_run_at: datetime | None = None
    top_error_account_name: str | None = None
    top_error_account_errors: int = 0
    series: list[DashboardSeriesPointRead] = Field(default_factory=list)
    shared_deactivation: DashboardSharedDeactivationSummaryRead = Field(
        default_factory=DashboardSharedDeactivationSummaryRead
    )
