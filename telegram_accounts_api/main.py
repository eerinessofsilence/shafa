from __future__ import annotations

from fastapi import FastAPI

from telegram_accounts_api.routers import accounts, channel_templates, health, telegram, templates
from telegram_accounts_api.utils.config import settings
from telegram_accounts_api.utils.exceptions import register_exception_handlers
from telegram_accounts_api.utils.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="REST API for managing Telegram accounts stored in a JSON file.",
)


register_exception_handlers(app)
app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(channel_templates.router)
app.include_router(templates.router)
app.include_router(telegram.router)
