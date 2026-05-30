from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram_accounts_api.services.cleanup_service import OutdatedProductCleanupService


class _FakeRuntime:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env or {}

    def account_env(self, account) -> dict[str, str]:
        return {
            "SHAFA_DB_PATH": str(Path(account.path) / "account.sqlite3"),
            "SHAFA_STORAGE_STATE_PATH": str(Path(account.path) / "auth.json"),
            "SHAFA_SHARED_TELEGRAM_DB_PATH": str(Path(account.path) / "telegram.sqlite3"),
            **self.env,
        }

    def account_python(self, _account) -> str:
        return "python"

    def export_channel_runtime_config(self, account) -> Path:
        return Path(account.path) / "channels.json"


class _FakeSessionStore:
    def is_valid_shafa_session(self, _account) -> bool:
        return True


class _FakeAccountService:
    def __init__(self, account, env: dict[str, str] | None = None) -> None:
        self.account = account
        self.runtime = _FakeRuntime(env)
        self.session_store = _FakeSessionStore()
        self.logs: list[str] = []
        self.log_store = SimpleNamespace(append=lambda *_args, **_kwargs: None)

    def load_runtime_accounts(self):
        return [self.account]

    def _active_process(self, _account_id: str):
        return None

    def _append_log(self, _account, message: str) -> None:
        self.logs.append(message)


class CleanupServiceTest(unittest.TestCase):
    def _account(self, project_dir: Path):
        (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
        return SimpleNamespace(
            id="acc-1",
            name="Alpha",
            path=str(project_dir),
            channel_links=[],
        )

    def test_global_direct_cleanup_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account = self._account(Path(temp_dir))
            fake_service = _FakeAccountService(account)
            cleanup = OutdatedProductCleanupService(fake_service)

            with (
                patch.dict(
                    "os.environ",
                    {
                        "SHAFA_GLOBAL_OLD_PRODUCT_CLEANUP_ENABLED": "",
                        "SHAFA_DISABLE_OUTDATED_PRODUCT_CLEANUP": "",
                    },
                    clear=False,
                ),
                patch("subprocess.run") as run,
            ):
                result = cleanup.run_once()

        run.assert_not_called()
        self.assertEqual(result["deactivated"], 0)
        self.assertTrue(
            any(
                "cleanup_mode=disabled" in line
                and "deactivation_mode=old_direct" in line
                and "will_call_shafa=false" in line
                for line in fake_service.logs
            )
        )

    def test_shared_mode_runs_planner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account = self._account(Path(temp_dir))
            fake_service = _FakeAccountService(
                account,
                {
                    "SHAFA_SHARED_DEACTIVATION_ENABLED": "1",
                    "SHAFA_SHARED_DEACTIVATION_PLANNER_ENABLED": "1",
                },
            )
            cleanup = OutdatedProductCleanupService(fake_service)

            completed = subprocess.CompletedProcess(
                ["python", "main.py"],
                0,
                stdout='{"checked": 2, "deactivated": 0, "failed": 0}\n',
            )
            with (
                patch.dict(
                    "os.environ",
                    {"SHAFA_GLOBAL_OLD_PRODUCT_CLEANUP_ENABLED": ""},
                    clear=False,
                ),
                patch("subprocess.run", return_value=completed) as run,
            ):
                result = cleanup.run_once()

        command = run.call_args.args[0]
        self.assertIn("--shared-deactivation-plan-once", command)
        self.assertNotIn("--deactivate-old-products-once", command)
        self.assertEqual(result["checked"], 2)
        self.assertTrue(
            any(
                "cleanup_mode=planner_only" in line
                and "deactivation_mode=shared_planner" in line
                and "will_call_shafa=false" in line
                for line in fake_service.logs
            )
        )

    def test_detached_direct_cleanup_age_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account = self._account(Path(temp_dir))
            fake_service = _FakeAccountService(account)
            cleanup = OutdatedProductCleanupService(fake_service)

            completed = subprocess.CompletedProcess(
                ["python", "main.py"],
                0,
                stdout='{"checked": 0, "deactivated": 0, "failed": 0}\n',
            )
            with (
                patch.dict(
                    "os.environ",
                    {
                        "SHAFA_GLOBAL_OLD_PRODUCT_CLEANUP_ENABLED": "1",
                        "SHAFA_TELEGRAM_PRODUCT_MAX_AGE_DAYS": "1",
                    },
                    clear=False,
                ),
                patch("subprocess.run", return_value=completed) as run,
            ):
                cleanup.run_once()

        command = run.call_args.args[0]
        age_index = command.index("--old-products-age-days") + 1
        self.assertEqual(command[age_index], "183")


if __name__ == "__main__":
    unittest.main()
