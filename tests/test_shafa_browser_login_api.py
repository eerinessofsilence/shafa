from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shafa_control import AccountSessionStore
from telegram_accounts_api.dependencies import get_account_service, get_auth_service
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import (
    AccountAuthService,
    _shafa_login_launch_command,
)
from telegram_accounts_api.utils.storage import JsonListStorage
from tests.asgi_client import SyncASGITestClient, async_dependency


class ShafaBrowserLoginApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_dir = self.base_dir / "accounts"
        self.accounts_file.write_text(
            json.dumps(
                [
                    {
                        "id": "acc-1",
                        "name": "Waffle",
                        "phone": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.account_service = AccountService(
            storage=JsonListStorage(self.accounts_file),
            accounts_dir=self.accounts_dir,
        )
        self.launched_commands: list[tuple[str, list[str]]] = []
        store = AccountSessionStore(
            base_dir=self.base_dir,
            accounts_dir=self.accounts_dir,
            legacy_state_file=self.accounts_file,
        )

        def launcher(account, args: list[str]) -> None:
            self.launched_commands.append((account.id, args))

        self.auth_service = AccountAuthService(
            account_service=self.account_service,
            store=store,
            shafa_login_launcher=launcher,
        )
        app.dependency_overrides[get_account_service] = async_dependency(self.account_service)
        app.dependency_overrides[get_auth_service] = async_dependency(self.auth_service)
        self.addCleanup(app.dependency_overrides.clear)
        self.client = SyncASGITestClient(app)

    def test_browser_login_endpoint_starts_shafa_flow(self) -> None:
        response = self.client.post("/accounts/acc-1/auth/shafa/browser-login")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.launched_commands, [("acc-1", ["main.py", "--login-shafa"])])
        self.assertIn("запущен", response.json()["message"].lower())

    def test_windows_shafa_login_uses_direct_python_command(self) -> None:
        with (
            patch(
                "telegram_accounts_api.services.auth_service.subprocess.CREATE_NO_WINDOW",
                0x08000000,
                create=True,
            ),
            patch(
                "telegram_accounts_api.services.auth_service.subprocess.CREATE_NEW_PROCESS_GROUP",
                0x00000200,
                create=True,
            ),
        ):
            command, creationflags = _shafa_login_launch_command(
                r"C:\App\.venv\Scripts\python.exe",
                ["main.py", "--login-shafa"],
                windows=True,
            )

        self.assertEqual(
            command,
            [r"C:\App\.venv\Scripts\python.exe", "main.py", "--login-shafa"],
        )
        self.assertFalse(command[0].lower().endswith("pythonw.exe"))
        self.assertEqual(creationflags, 0x08000200)

    def test_shafa_login_launcher_passes_confirmation_file_env(self) -> None:
        project_dir = self.base_dir / "project" / "shafa_logic"
        project_dir.mkdir(parents=True)
        (project_dir / "main.py").write_text("print('login')\n", encoding="utf-8")
        account = self.account_service.load_runtime_accounts()[0]
        account.path = str(project_dir)
        captured = {}

        class _Process:
            def poll(self):
                return None

        def _fake_popen(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]
            captured["cwd"] = kwargs["cwd"]
            return _Process()

        with (
            patch(
                "telegram_accounts_api.services.auth_service.subprocess.Popen",
                side_effect=_fake_popen,
            ),
            patch("telegram_accounts_api.services.auth_service.time.sleep"),
        ):
            self.auth_service._launch_shafa_login(account, ["main.py", "--login-shafa"])

        confirmation_file = self.accounts_dir / account.id / "shafa_login.confirm"
        self.assertEqual(
            captured["env"]["SHAFA_LOGIN_CONFIRMATION_FILE"],
            str(confirmation_file),
        )
        self.assertEqual(captured["env"]["SHAFA_LOGIN_FRESH_CONTEXT"], "1")
        self.assertEqual(captured["cwd"], str(project_dir))


if __name__ == "__main__":
    unittest.main()
