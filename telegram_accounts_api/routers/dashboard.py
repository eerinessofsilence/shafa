from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from telegram_accounts_api.dependencies import get_dashboard_service
from telegram_accounts_api.models.dashboard import DashboardSummaryRead
from telegram_accounts_api.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(
    period: Literal["all", "week", "month", "quarter", "custom"] = Query("all"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummaryRead:
    try:
        return await service.get_summary(
            period=period,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
