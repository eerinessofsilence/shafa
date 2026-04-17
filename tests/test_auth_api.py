from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from shafa_control import Account, AccountSessionStore
from telegram_accounts_api.dependencies import get_account_service, get_auth_service
from telegram_accounts_api.main import app
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

    response = client.post(f"/accounts/{account_id}/auth/shafa/logout")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["cookies_count"] == 0
    assert store.auth_file(account).exists() is False

    account_payload = client.get(f"/accounts/{account_id}").json()
    assert account_payload["shafa_session_exists"] is False
