from __future__ import annotations

import subprocess
from pathlib import Path

from shafa_control import Account, AccountSessionStore, TelegramAuthService


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr)


def test_request_code_uses_account_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+38050")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        login_state = store.telegram_login_state_file(account)
        login_state.write_text("{}", encoding="utf-8")
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True
    assert captured == [["main.py", "--telegram-send-code", "+38050"]]
    assert service.has_pending_code(account) is True


def test_submit_code_returns_error_for_empty_code(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+38050")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    result = service.submit_code(account, " ")

    assert result.ok is False
    assert "Verification code is required" in result.message


def test_submit_code_runs_login_command(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+38050")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        return _completed(0, stdout="done")

    service = TelegramAuthService(store, runner)

    result = service.submit_code(account, "12345")

    assert result.ok is True
    assert captured == [[
        "main.py",
        "--telegram-login-phone",
        "+38050",
        "--telegram-login-code",
        "12345",
    ]]


def test_request_code_fails_without_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    result = service.request_code(account)

    assert result.ok is False
    assert "phone number" in result.message


def test_interactive_command_matches_terminal_flow(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    assert service.interactive_command() == ["main.py", "--telegram-auth-interactive"]
