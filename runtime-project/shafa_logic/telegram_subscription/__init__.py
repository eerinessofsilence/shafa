__all__ = [
    "complete_login",
    "get_telegram_channels",
    "send_code",
    "session_status",
    "set_telegram_channels",
    "submit_password",
    "sync_channels_from_runtime_config",
]


def __getattr__(name: str):
    if name in {"complete_login", "send_code", "session_status", "submit_password"}:
        from . import auth

        return getattr(auth, name)

    if name in {"get_telegram_channels", "set_telegram_channels", "sync_channels_from_runtime_config"}:
        from . import sync

        return getattr(sync, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
