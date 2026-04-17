from __future__ import annotations

import logging

from telegram_accounts_api.utils.account_logging import install_account_log_handler


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    install_account_log_handler()
