from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shafa_logic"))

from telegram_subscription import (  # noqa: E402
    complete_login,
    send_code,
    submit_password,
    sync_channels_from_runtime_config,
)


def test_telegram_subscription_exports_expected_functions() -> None:
    assert callable(complete_login)
    assert callable(send_code)
    assert callable(submit_password)
    assert callable(sync_channels_from_runtime_config)
