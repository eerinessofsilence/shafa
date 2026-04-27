from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from shafa_control import Account, AccountSessionStore
from telegram_accounts_api.dependencies import get_account_service, get_auth_service
from telegram_accounts_api.main import app
from telegram_accounts_api.models.account import AccountCreate
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.utils.storage import JsonListStorage


def _make_client(tmp_path: Path):
    accounts_file = tmp_path / "accounts_state.json"
    accounts_dir = tmp_path / "accounts"
    storage = JsonListStorage(accounts_file)
    account_service = AccountService(storage=storage, accounts_dir=accounts_dir)
    store = AccountSessionStore(tmp_path, accounts_dir, accounts_file)

    def runner(account: Account, args: list[str]) -> subprocess.CompletedProcess:
        if "--telegram-send-code" in args:
            store.telegram_login_state_file(account).write_text(
                json.dumps(
                    {
                        "phone_number": account.phone_number,
                        "current_auth_step": "WAIT_CODE",
                        "phone_code_hash": "hash-123",
                        "session_path": str(store.telegram_session_file(account)),
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")
        if "--telegram-login-phone" in args:
            store.telegram_login_state_file(account).write_text(
                json.dumps(
                    {
                        "phone_number": account.phone_number,
                        "verification_code": args[-1],
                        "current_auth_step": "WAIT_PASSWORD",
                        "phone_code_hash": "hash-123",
                        "session_path": str(store.telegram_session_file(account)),
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, stdout="password required", stderr="")
        if "--telegram-login-password" in args:
            store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
            store.telegram_login_state_file(account).write_text(
                json.dumps(
                    {
                        "phone_number": account.phone_number,
                        "current_auth_step": "SUCCESS",
                        "session_path": str(store.telegram_session_file(account)),
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, stdout="done", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected command")

    auth_service = AccountAuthService(account_service=account_service, store=store, runner=runner)
    app.dependency_overrides[get_account_service] = lambda: account_service
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    return TestClient(app), store


def test_telegram_auth_api_runs_separate_steps(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Test", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]

    credentials_response = client.post(
        f"/accounts/{account_id}/auth/telegram/credentials",
        json={"api_id": "777000", "api_hash": "secret-hash"},
    )
    assert credentials_response.status_code == 200
    assert store.has_telegram_credentials(Account(id=account_id, name="Test", path="/tmp/project")) is True

    request_code_response = client.post(
        f"/accounts/{account_id}/auth/telegram/request-code",
        json={"phone": "+380501112233"},
    )
    assert request_code_response.status_code == 200
    assert request_code_response.json()["current_step"] == "WAIT_CODE"
    assert request_code_response.json()["phone_number"] == "+380501112233"

    submit_code_response = client.post(
        f"/accounts/{account_id}/auth/telegram/submit-code",
        json={"code": "12345"},
    )
    assert submit_code_response.status_code == 200
    assert submit_code_response.json()["current_step"] == "WAIT_PASSWORD"

    submit_password_response = client.post(
        f"/accounts/{account_id}/auth/telegram/submit-password",
        json={"password": "secret-pass"},
    )
    assert submit_password_response.status_code == 200
    assert submit_password_response.json()["connected"] is True
    assert submit_password_response.json()["current_step"] == "SUCCESS"


def test_telegram_auth_api_uses_backend_env_credentials(tmp_path: Path) -> None:
    client, _store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Env account", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]

    with patch.dict(
        os.environ,
        {
            "SHAFA_TELEGRAM_API_ID": "777000",
            "SHAFA_TELEGRAM_API_HASH": "secret-hash",
        },
        clear=False,
    ):
        status_response = client.get(f"/accounts/{account_id}/auth/telegram")
        assert status_response.status_code == 200
        assert status_response.json()["has_api_credentials"] is True

        request_code_response = client.post(
            f"/accounts/{account_id}/auth/telegram/request-code",
            json={"phone": "+380501112233"},
        )
        assert request_code_response.status_code == 200
        assert request_code_response.json()["current_step"] == "WAIT_CODE"


def test_telegram_status_keeps_code_step_when_old_session_exists(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Test", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    account = Account(id=account_id, name="Test", path="/tmp/project")

    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")

    credentials_response = client.post(
        f"/accounts/{account_id}/auth/telegram/credentials",
        json={"api_id": "777000", "api_hash": "secret-hash"},
    )
    assert credentials_response.status_code == 200

    request_code_response = client.post(
        f"/accounts/{account_id}/auth/telegram/request-code",
        json={"phone": "+380501112233"},
    )
    assert request_code_response.status_code == 200
    assert request_code_response.json()["connected"] is False
    assert request_code_response.json()["current_step"] == "WAIT_CODE"

    status_response = client.get(f"/accounts/{account_id}/auth/telegram")
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is False
    assert status_response.json()["current_step"] == "WAIT_CODE"


def test_telegram_logout_clears_session_and_returns_init_status(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Test", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    account = Account(id=account_id, name="Test", path="/tmp/project")

    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
    store.telegram_login_state_file(account).write_text(
        json.dumps(
            {
                "phone_number": "+380501112233",
                "current_auth_step": "SUCCESS",
                "session_path": str(store.telegram_session_file(account)),
            }
        ),
        encoding="utf-8",
    )

    response = client.post(f"/accounts/{account_id}/auth/telegram/logout")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["current_step"] == "INIT"
    assert response.json()["phone_number"] == "+380501112233"
    assert store.telegram_session_file(account).exists() is False

    account_payload = client.get(f"/accounts/{account_id}").json()
    assert account_payload["telegram_session_exists"] is False


def test_telegram_copy_session_copies_session_and_credentials(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    source_response = client.post(
        "/accounts",
        json={"name": "Source", "path": str(Path("/tmp/project")), "phone": "+380501112233", "channel_links": []},
    )
    target_response = client.post(
        "/accounts",
        json={"name": "Target", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert source_response.status_code == 201
    assert target_response.status_code == 201

    source_id = source_response.json()["id"]
    target_id = target_response.json()["id"]
    source = Account(id=source_id, name="Source", path="/tmp/project", phone_number="+380501112233")
    target = Account(id=target_id, name="Target", path="/tmp/project")

    store.telegram_session_file(source).write_bytes(b"SQLite format 3\x00payload")
    store.telegram_credentials_file(source).write_text(
        "SHAFA_TELEGRAM_API_ID=777000\nSHAFA_TELEGRAM_API_HASH=secret-hash\n",
        encoding="utf-8",
    )
    store.telegram_login_state_file(source).write_text(
        json.dumps(
            {
                "phone_number": "+380501112233",
                "current_auth_step": "SUCCESS",
                "session_path": str(store.telegram_session_file(source)),
            }
        ),
        encoding="utf-8",
    )

    response = client.post(
        f"/accounts/{target_id}/auth/telegram/copy-session",
        json={"source_account_id": source_id},
    )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["current_step"] == "SUCCESS"
    assert response.json()["phone_number"] == "+380501112233"
    assert store.telegram_session_file(target).read_bytes() == store.telegram_session_file(source).read_bytes()
    assert store.telegram_credentials_file(target).read_text(encoding="utf-8") == (
        "SHAFA_TELEGRAM_API_ID=777000\nSHAFA_TELEGRAM_API_HASH=secret-hash\n"
    )


def test_telegram_copy_session_rejects_same_account(tmp_path: Path) -> None:
    client, _store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Test", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]

    response = client.post(
        f"/accounts/{account_id}/auth/telegram/copy-session",
        json={"source_account_id": account_id},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Source and target accounts must be different."


def test_telegram_import_session_saves_uploaded_file(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Import", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    account = Account(id=account_id, name="Import", path="/tmp/project")

    response = client.post(
        f"/accounts/{account_id}/auth/telegram/import-session",
        files={
            "file": (
                "telegram.session",
                b"SQLite format 3\x00payload",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["current_step"] == "SUCCESS"
    assert store.telegram_session_file(account).read_bytes() == b"SQLite format 3\x00payload"

    account_payload = client.get(f"/accounts/{account_id}").json()
    assert account_payload["telegram_session_exists"] is True


def test_telegram_status_backfills_phone_from_authorized_session(tmp_path: Path) -> None:
    accounts_file = tmp_path / "accounts_state.json"
    accounts_dir = tmp_path / "accounts"
    storage = JsonListStorage(accounts_file)
    account_service = AccountService(storage=storage, accounts_dir=accounts_dir)
    store = AccountSessionStore(tmp_path, accounts_dir, accounts_file)
    auth_service = AccountAuthService(
        account_service=account_service,
        store=store,
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )

    created = asyncio.run(
        account_service.create_account(
            AccountCreate(
                name="Resolved phone",
                phone="",
                path=str(Path("/tmp/project")),
                channel_links=[],
            )
        )
    )
    account = Account(id=created.id, name=created.name, path=created.path)
    store.telegram_session_file(account).parent.mkdir(parents=True, exist_ok=True)
    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
    auth_service.telegram_auth.persist_auth_state(
        account,
        current_auth_step="SUCCESS",
        session_path=str(store.telegram_session_file(account)),
        code_confirmed=False,
    )

    with patch.object(
        auth_service,
        "_resolve_phone_from_session",
        AsyncMock(return_value="+380501112233"),
    ):
        status = asyncio.run(auth_service.get_telegram_status(created.id))

    assert status.connected is True
    assert status.phone_number == "+380501112233"

    updated_account = asyncio.run(account_service.get_account(created.id))
    assert updated_account.phone == "+380501112233"

    persisted_state = auth_service.telegram_auth.load_auth_state(
        Account(id=created.id, name=created.name, path=created.path),
    )
    assert persisted_state["phone_number"] == "+380501112233"


def test_shafa_auth_api_saves_cookies_for_backend(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Shafa", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]

    response = client.post(
        f"/accounts/{account_id}/auth/shafa/cookies",
        json={
            "cookies": [
                {
                    "name": "csrftoken",
                    "value": "token-123",
                    "secure": True,
                },
                {
                    "name": "sessionid",
                    "value": "session-456",
                    "domain": ".shafa.ua",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    account = Account(id=account_id, name="Shafa", path="/tmp/project")
    saved_state = json.loads(store.auth_file(account).read_text(encoding="utf-8"))
    assert saved_state["cookies"][0]["domain"] == ".shafa.ua"
    assert saved_state["cookies"][0]["name"] == "csrftoken"
    assert store.is_valid_shafa_session(account) is True


def test_shafa_auth_api_returns_profile_fields(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Shafa", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    account = Account(id=account_id, name="Shafa", path="/tmp/project")

    store.auth_file(account).write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "csrftoken",
                        "value": "token-123",
                        "domain": ".shafa.ua",
                    },
                    {
                        "name": "sessionid",
                        "value": "session-456",
                        "domain": ".shafa.ua",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    auth_service = app.dependency_overrides[get_auth_service]()
    with patch.object(
        auth_service,
        "_fetch_shafa_profile",
        return_value={"email": "seller@example.com", "phone": "+380501112233"},
    ):
        response = client.get(f"/accounts/{account_id}/auth/shafa")

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["email"] == "seller@example.com"
    assert response.json()["phone"] == "+380501112233"


def test_shafa_logout_clears_cookies_and_returns_disconnected_status(tmp_path: Path) -> None:
    client, store = _make_client(tmp_path)

    created = client.post(
        "/accounts",
        json={"name": "Shafa", "path": str(Path("/tmp/project")), "phone": "", "channel_links": []},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    account = Account(id=account_id, name="Shafa", path="/tmp/project")

    store.auth_file(account).write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "csrftoken",
                        "value": "token-123",
                        "domain": ".shafa.ua",
                    },
                    {
                        "name": "sessionid",
                        "value": "session-456",
                        "domain": ".shafa.ua",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(store.db_file(account)) as conn:
        conn.execute(
            """
            CREATE TABLE cookies (
                id INTEGER PRIMARY KEY,
                domain TEXT,
                name TEXT,
                value TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO cookies(domain, name, value) VALUES (?, ?, ?)",
            (".shafa.ua", "csrftoken", "token-123"),
        )

    response = client.post(f"/accounts/{account_id}/auth/shafa/logout")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["cookies_count"] == 0
    assert store.auth_file(account).exists() is False
    with sqlite3.connect(store.db_file(account)) as conn:
        cookies_count = conn.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
    assert cookies_count == 0

    account_payload = client.get(f"/accounts/{account_id}").json()
    assert account_payload["shafa_session_exists"] is False


def test_packaged_telegram_runner_does_not_require_project_main(tmp_path: Path) -> None:
    accounts_file = tmp_path / "accounts_state.json"
    accounts_dir = tmp_path / "accounts"
    storage = JsonListStorage(accounts_file)
    account_service = AccountService(storage=storage, accounts_dir=accounts_dir)
    store = AccountSessionStore(tmp_path, accounts_dir, accounts_file)
    service = AccountAuthService(account_service=account_service, store=store)
    account = Account(
        id="acc-1",
        name="Packaged",
        path=str(tmp_path / "backend-data"),
        phone_number="+380501112233",
    )

    class FakeTelegramClient:
        def __init__(self, *_args):
            self.disconnect_calls = 0

        async def connect(self):
            return None

        async def disconnect(self):
            self.disconnect_calls += 1

        async def send_code_request(self, phone: str):
            assert phone == "+380501112233"
            return SimpleNamespace(phone_code_hash="hash-123")

    with patch.object(
        service,
        "_telegram_client_config",
        return_value=(FakeTelegramClient, 777000, "hash", store.telegram_session_file(account)),
    ):
        result = service._run_account_command(
            account,
            ["main.py", "--telegram-send-code", "+380501112233"],
        )

    assert result.returncode == 0
    state = json.loads(store.telegram_login_state_file(account).read_text(encoding="utf-8"))
    assert state["current_auth_step"] == "WAIT_CODE"
    assert state["phone_code_hash"] == "hash-123"
