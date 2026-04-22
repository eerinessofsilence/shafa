from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DashboardSeriesPointRead(BaseModel):
    date: date
    items: int = 0
    errors: int = 0


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
