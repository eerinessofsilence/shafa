from __future__ import annotations

from fastapi import APIRouter, Depends

from telegram_accounts_api.dependencies import get_dashboard_service
from telegram_accounts_api.models.dashboard import DashboardSummaryRead
from telegram_accounts_api.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummaryRead:
    return await service.get_summary()
