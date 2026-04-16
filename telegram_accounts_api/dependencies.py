from __future__ import annotations

from functools import lru_cache

from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.channel_template_service import ChannelTemplateService
from telegram_accounts_api.services.telegram_service import TelegramService
from telegram_accounts_api.services.template_service import TemplateService
from telegram_accounts_api.utils.config import settings
from telegram_accounts_api.utils.storage import JsonListStorage


@lru_cache
def get_account_service() -> AccountService:
    return AccountService(
        storage=JsonListStorage(settings.accounts_file),
        accounts_dir=settings.accounts_dir,
        channel_template_service=get_channel_template_service(),
    )


@lru_cache
def get_template_service() -> TemplateService:
    return TemplateService(JsonListStorage(settings.templates_file))


@lru_cache
def get_channel_template_service() -> ChannelTemplateService:
    return ChannelTemplateService(
        storage=JsonListStorage(settings.channel_templates_file),
        account_service=_get_base_account_service(),
    )


@lru_cache
def _get_base_account_service() -> AccountService:
    return AccountService(
        storage=JsonListStorage(settings.accounts_file),
        accounts_dir=settings.accounts_dir,
    )


@lru_cache
def get_telegram_service() -> TelegramService:
    return TelegramService(
        account_service=get_account_service(),
        template_service=get_template_service(),
        base_dir=settings.base_dir,
    )
