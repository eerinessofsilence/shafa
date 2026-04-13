from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shafa"))

from telegram_subscription import (  # noqa: E402
    complete_login,
    interactive_login,
    send_code,
    sync_channels_from_runtime_config,
)


def test_telegram_subscription_exports_expected_functions() -> None:
    assert callable(interactive_login)
    assert callable(complete_login)
    assert callable(send_code)
    assert callable(sync_channels_from_runtime_config)
