from __future__ import annotations

import subprocess
from pathlib import Path

from datetime import datetime, timedelta

from shafa_control import Account, AccountSessionStore, TelegramAuthRuntime, TelegramAuthService


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr)


def test_request_code_uses_account_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        login_state = store.telegram_login_state_file(account)
        login_state.write_text('{"current_auth_step":"WAITING_FOR_CODE"}', encoding="utf-8")
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True
    assert captured == [["main.py", "--telegram-send-code", "+380501112233"]]
    assert service.has_pending_code(account) is True


def test_submit_code_returns_error_for_empty_code(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    result = service.submit_code(account, " ")

    assert result.ok is False
    assert "5 or 6 digits" in result.message


def test_submit_code_runs_login_command(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        return _completed(0, stdout="done")

    service = TelegramAuthService(store, runner)

    result = service.submit_code(account, "123456")

    assert result.ok is True
    assert captured == [[
        "main.py",
        "--telegram-login-phone",
        "+380501112233",
        "--telegram-login-code",
        "123456",
    ]]


def test_request_code_fails_without_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    result = service.request_code(account)

    assert result.ok is False
    assert result.message == "Phone number is required for Telegram login"


def test_interactive_command_matches_terminal_flow(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    assert service.interactive_command() == ["main.py", "--telegram-auth-interactive"]


def test_reuse_status_detects_existing_session(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project")
    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    status = service.reuse_status(account)

    assert status is not None
    assert status.ok is True
    assert "Reusing existing Telegram session" in status.message


def test_runtime_state_machine_completes_sequentially() -> None:
    runtime = TelegramAuthRuntime(account_id="acc")
    runtime.start_step("WAIT_PHONE")

    assert runtime.transition("PHONE_PROMPT").ok is True
    assert runtime.state == "WAIT_CODE"
    assert runtime.transition("CODE_PROMPT").ok is True
    assert runtime.state == "AWAITING_CODE_INPUT"
    assert runtime.transition("CODE_SENT").ok is True
    assert runtime.state == "VERIFYING"
    assert runtime.transition("SUCCESS").ok is True
    assert runtime.state == "SUCCESS"


def test_runtime_state_machine_fails_on_repeated_prompt() -> None:
    runtime = TelegramAuthRuntime(account_id="acc")
    runtime.start_step("WAIT_PHONE")
    runtime.transition("PHONE_PROMPT")
    runtime.transition("CODE_PROMPT")

    status = runtime.transition("PHONE_PROMPT")

    assert status is not None
    assert status.ok is False


def test_runtime_timeout_reports_current_step() -> None:
    runtime = TelegramAuthRuntime(account_id="acc")
    runtime.start_step("WAIT_CODE")
    runtime.deadline = datetime.now() - timedelta(seconds=1)

    status = runtime.timeout_status()

    assert status is not None
    assert status.ok is False
    assert "code prompt" in status.message


def test_validate_phone_rejects_empty_and_placeholder(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    assert service.validate_phone("").message == "Phone number is required for Telegram login"
    assert service.validate_phone("+380...").message == "Phone number is required for Telegram login"
    assert service.validate_phone("  +380 (50) 111-22-33  ").message == "+380501112233"


def test_validate_code_requires_exactly_six_digits(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    assert service.validate_code("").ok is False
    assert service.validate_code("12345").ok is True
    assert service.validate_code("12345a").ok is False
    assert service.validate_code("123456").ok is True
    assert service.validate_code("1234567").ok is False


def test_auth_state_persists_phone_code_and_step(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+38050")

    service.persist_auth_state(
        account,
        phone_number=" +380501112233 ",
        verification_code=" 123456 ",
        current_auth_step="VERIFYING",
        code_confirmed=True,
        extra={"phone_code_hash": "hash"},
    )

    state = service.load_auth_state(account)

    assert state["phone_number"] == "+380501112233"
    assert state["verification_code"] == "123456"
    assert state["current_auth_step"] == "WAIT_CODE"
    assert state["phone_code_hash"] == "hash"
    assert state["code_confirmed"] is True
