from __future__ import annotations

from functools import lru_cache

from shafa_control import AccountSessionStore

from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.services.channel_template_service import ChannelTemplateService
from telegram_accounts_api.services.dashboard_service import DashboardService
from telegram_accounts_api.services.telegram_service import TelegramService
from telegram_accounts_api.services.template_service import TemplateService
from telegram_accounts_api.utils.account_logging import AccountLogStore, get_account_log_store as get_shared_account_log_store
from telegram_accounts_api.utils.config import settings
from telegram_accounts_api.utils.storage import JsonListStorage


@lru_cache
def _get_account_service_cached() -> AccountService:
    return AccountService(
        storage=JsonListStorage(settings.accounts_file),
        accounts_dir=settings.accounts_dir,
        channel_template_service=_get_channel_template_service_cached(),
    )


async def get_account_service() -> AccountService:
    return _get_account_service_cached()


@lru_cache
def _get_template_service_cached() -> TemplateService:
    return TemplateService(JsonListStorage(settings.templates_file))


async def get_template_service() -> TemplateService:
    return _get_template_service_cached()


@lru_cache
def _get_channel_template_service_cached() -> ChannelTemplateService:
    return ChannelTemplateService(
        storage=JsonListStorage(settings.channel_templates_file),
        account_service=_get_base_account_service(),
    )


async def get_channel_template_service() -> ChannelTemplateService:
    return _get_channel_template_service_cached()


@lru_cache
def _get_base_account_service() -> AccountService:
    return AccountService(
        storage=JsonListStorage(settings.accounts_file),
        accounts_dir=settings.accounts_dir,
    )


@lru_cache
def _get_telegram_service_cached() -> TelegramService:
    return TelegramService(
        account_service=_get_account_service_cached(),
        template_service=_get_template_service_cached(),
        base_dir=settings.base_dir,
    )


async def get_telegram_service() -> TelegramService:
    return _get_telegram_service_cached()


@lru_cache
def _get_auth_service_cached() -> AccountAuthService:
    store = AccountSessionStore(
        base_dir=settings.base_dir,
        accounts_dir=settings.accounts_dir,
        legacy_state_file=settings.accounts_file,
    )
    return AccountAuthService(
        account_service=_get_account_service_cached(),
        store=store,
    )


async def get_auth_service() -> AccountAuthService:
    return _get_auth_service_cached()


@lru_cache
def _get_account_log_store_cached() -> AccountLogStore:
    return get_shared_account_log_store()


async def get_account_log_store() -> AccountLogStore:
    return _get_account_log_store_cached()


@lru_cache
def _get_dashboard_service_cached() -> DashboardService:
    return DashboardService(
        account_service=_get_account_service_cached(),
        log_store=_get_account_log_store_cached(),
    )


async def get_dashboard_service() -> DashboardService:
    return _get_dashboard_service_cached()
