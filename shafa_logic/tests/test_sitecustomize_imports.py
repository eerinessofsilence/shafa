from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_can_import_telegram_accounts_api_from_shafa_logic_cwd() -> None:
    shafa_logic_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import telegram_accounts_api"],
        cwd=shafa_logic_dir,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_can_import_telegram_accounts_api_from_desktop_ui_cwd() -> None:
    desktop_ui_dir = Path(__file__).resolve().parents[2] / "desktop-ui"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import telegram_accounts_api"],
        cwd=desktop_ui_dir,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
