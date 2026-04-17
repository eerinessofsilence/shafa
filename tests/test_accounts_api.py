from __future__ import annotations

import io
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telegram_accounts_api.dependencies import get_account_service
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.storage import JsonListStorage


class _FakeRunningProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.stdout = io.StringIO("")
        self._stopped = threading.Event()

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        finished = self._stopped.wait(timeout)
        if not finished:
            raise subprocess.TimeoutExpired(cmd="fake-process", timeout=timeout or 0)
        return int(self.returncode or 0)

    def request_stop(self, code: int = 0) -> None:
        self.returncode = code
        self._stopped.set()


class AccountsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_dir = self.base_dir / "accounts"
        self._write_accounts(
            [
                {
                    "id": "acc-1",
                    "name": "Initial account",
                    "phone_number": "+380000000000",
                    "path": "/tmp/project",
                    "branch": "main",
                    "open_browser": False,
                    "timer_minutes": 5,
                    "channel_links": ["https://t.me/example_channel"],
                    "status": "stopped",
                    "last_run": None,
                    "errors": 3,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )

        self.service = AccountService(
            storage=JsonListStorage(self.accounts_file),
            accounts_dir=self.accounts_dir,
        )
        app.dependency_overrides[get_account_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def _write_accounts(self, payload: list[dict]) -> None:
        self.accounts_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_accounts(self) -> list[dict]:
        return json.loads(self.accounts_file.read_text(encoding="utf-8"))

    def _make_project(self, name: str = "project") -> Path:
        project_dir = self.base_dir / name
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
        return project_dir

    def _write_valid_shafa_session(self, account_id: str) -> None:
        account_dir = self.accounts_dir / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        (account_dir / "auth.json").write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "csrftoken",
                            "value": "token-123",
                            "domain": ".shafa.ua",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_patch_updates_only_allowed_fields(self) -> None:
        response = self.client.patch(
            "/accounts/acc-1",
            json={
                "name": "Updated account",
                "path": "/tmp/updated-project",
                "open_browser": True,
                "timer_minutes": 15,
                "channel_links": [
                    "t.me/updated_channel",
                    "https://t.me/second_channel",
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Updated account")
        self.assertEqual(payload["path"], "/tmp/updated-project")
        self.assertEqual(payload["open_browser"], True)
        self.assertEqual(payload["timer_minutes"], 15)
        self.assertEqual(
            payload["channel_links"],
            [
                "https://t.me/updated_channel",
                "https://t.me/second_channel",
            ],
        )
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["errors"], 3)
        self.assertEqual(payload["branch"], "main")

        stored_payload = self._read_accounts()[0]
        self.assertEqual(stored_payload["name"], "Updated account")
        self.assertEqual(stored_payload["path"], "/tmp/updated-project")
        self.assertEqual(stored_payload["open_browser"], True)
        self.assertEqual(stored_payload["timer_minutes"], 15)
        self.assertEqual(
            stored_payload["channel_links"],
            [
                "https://t.me/updated_channel",
                "https://t.me/second_channel",
            ],
        )
        self.assertEqual(stored_payload["status"], "stopped")
        self.assertEqual(stored_payload["errors"], 3)
        self.assertNotEqual(
            stored_payload["updated_at"],
            "2026-01-01T00:00:00+00:00",
        )

    def test_patch_returns_404_for_unknown_account(self) -> None:
        response = self.client.patch(
            "/accounts/missing-account",
            json={"name": "Nope"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_patch_validates_payload(self) -> None:
        empty_name = self.client.patch("/accounts/acc-1", json={"name": ""})
        invalid_timer = self.client.patch(
            "/accounts/acc-1",
            json={"timer_minutes": 0},
        )

        self.assertEqual(empty_name.status_code, 422)
        self.assertEqual(invalid_timer.status_code, 422)

    def test_get_account_returns_actual_session_flags(self) -> None:
        account_dir = self.accounts_dir / "acc-1"
        account_dir.mkdir(parents=True, exist_ok=True)
        (account_dir / "auth.json").write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "csrftoken",
                            "value": "token-123",
                            "domain": ".shafa.ua",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (account_dir / "telegram.session").write_bytes(b"SQLite format 3\x00payload")

        response = self.client.get("/accounts/acc-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["shafa_session_exists"], True)
        self.assertEqual(payload["telegram_session_exists"], True)

    def test_create_account_uses_base_dir_when_path_is_empty(self) -> None:
        response = self.client.post(
            "/accounts",
            json={
                "name": "Default path account",
                "phone": "",
                "path": "",
                "branch": "main",
                "open_browser": False,
                "timer_minutes": 5,
                "channel_links": [],
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["path"], str(self.base_dir))

        stored_accounts = self._read_accounts()
        created_account = next(item for item in stored_accounts if item["id"] == payload["id"])
        self.assertEqual(created_account["path"], str(self.base_dir))

    def test_start_account_requires_valid_shafa_session(self) -> None:
        project_dir = self._make_project()

        created = self.client.post(
            "/accounts",
            json={
                "name": "Runtime account",
                "phone": "",
                "path": str(project_dir),
                "branch": "main",
                "open_browser": False,
                "timer_minutes": 5,
                "channel_links": [],
            },
        )
        self.assertEqual(created.status_code, 201)
        account_id = created.json()["id"]

        response = self.client.post(f"/accounts/{account_id}/start")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Shafa session", response.json()["detail"])

        refreshed = self.client.get(f"/accounts/{account_id}")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["status"], "stopped")

    def test_start_and_stop_account_manage_runtime_process(self) -> None:
        project_dir = self._make_project()
        process = _FakeRunningProcess()

        created = self.client.post(
            "/accounts",
            json={
                "name": "Runtime account",
                "phone": "",
                "path": str(project_dir),
                "branch": "main",
                "open_browser": False,
                "timer_minutes": 5,
                "channel_links": [],
            },
        )
        self.assertEqual(created.status_code, 201)
        account_id = created.json()["id"]
        self._write_valid_shafa_session(account_id)

        self.service._spawn_process = lambda account, launch_context: process
        self.service._terminate_process = lambda proc: proc.request_stop()

        started = self.client.post(f"/accounts/{account_id}/start")

        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "started")
        self.assertEqual(started.json()["last_run"] is not None, True)

        refreshed = self.client.get(f"/accounts/{account_id}")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["status"], "started")

        stopped = self.client.post(f"/accounts/{account_id}/stop")

        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertEqual(process.returncode, 0)

    def test_cors_allows_renderer_origins(self) -> None:
        renderer_origin = self.client.options(
            "/accounts/acc-1",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "PATCH",
            },
        )
        null_origin = self.client.options(
            "/accounts/acc-1",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "PATCH",
            },
        )

        self.assertEqual(renderer_origin.status_code, 200)
        self.assertEqual(
            renderer_origin.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:5173",
        )
        self.assertEqual(null_origin.status_code, 200)
        self.assertEqual(
            null_origin.headers.get("access-control-allow-origin"),
            "null",
        )


if __name__ == "__main__":
    unittest.main()
