from __future__ import annotations

import subprocess
from pathlib import Path

from datetime import datetime, timedelta

from shafa_control import Account, AccountSessionStore, TelegramAuthRuntime, TelegramAuthService
from ui import AccountsPage, _preferred_project_dir


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr)


def test_request_code_uses_account_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        login_state = store.telegram_login_state_file(account)
        login_state.write_text(
            '{"phone_number":"+380501112233","current_auth_step":"WAITING_FOR_CODE","phone_code_hash":"hash-123"}',
            encoding="utf-8",
        )
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True
    assert captured == [["main.py", "--telegram-send-code", "+380501112233"]]
    assert service.has_pending_code(account) is True


def test_request_code_fails_when_state_was_not_confirmed(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")

    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0, stdout="ok"))

    result = service.request_code(account)

    assert result.ok is False
    assert "did not confirm" in result.message


def test_request_code_requires_phone_code_hash_in_state(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")

    def runner(_account: Account, _args: list[str]) -> subprocess.CompletedProcess:
        login_state = store.telegram_login_state_file(account)
        login_state.write_text(
            (
                '{'
                '"phone_number":"+380501112233",'
                '"current_auth_step":"WAITING_FOR_CODE",'
                '"phone_code_hash":"hash-123"'
                '}'
            ),
            encoding="utf-8",
        )
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True


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


def test_submit_code_reports_password_requirement_from_state(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")

    def runner(_account: Account, _args: list[str]) -> subprocess.CompletedProcess:
        store.telegram_login_state_file(account).write_text(
            '{"current_auth_step":"WAIT_PASSWORD"}',
            encoding="utf-8",
        )
        return _completed(0, stdout="password required")

    service = TelegramAuthService(store, runner)

    result = service.submit_code(account, "123456")

    assert result.ok is True
    assert result.pending_code is True
    assert result.message == "Telegram password required."


def test_submit_password_runs_password_command(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        return _completed(0, stdout="done")

    service = TelegramAuthService(store, runner)

    result = service.submit_password(account, "secret-pass")

    assert result.ok is True
    assert captured == [["main.py", "--telegram-login-password", "secret-pass"]]


def test_request_code_fails_without_phone(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="")
    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    result = service.request_code(account)

    assert result.ok is False
    assert result.message == "Phone number is required for Telegram login"


def test_request_code_does_not_resend_when_waiting_for_code(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    calls: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        calls.append(args)
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)
    service.persist_auth_state(
        account,
        phone_number="+380501112233",
        current_auth_step="WAIT_CODE",
        code_confirmed=False,
    )

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True
    assert "already requested" in result.message
    assert calls == []


def test_request_code_does_not_resend_when_waiting_for_password(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project", phone_number="+380501112233")
    calls: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        calls.append(args)
        return _completed(0, stdout="ok")

    service = TelegramAuthService(store, runner)
    service.persist_auth_state(
        account,
        phone_number="+380501112233",
        current_auth_step="WAIT_PASSWORD",
        code_confirmed=True,
    )

    result = service.request_code(account)

    assert result.ok is True
    assert result.pending_code is True
    assert "waiting for the 2FA password" in result.message
    assert calls == []


def test_reuse_status_detects_existing_session(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project")
    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        return _completed(0, stdout="Telegram session is authorized.")

    service = TelegramAuthService(store, runner)

    status = service.reuse_status(account)

    assert status is not None
    assert status.ok is True
    assert "Reusing existing Telegram session" in status.message
    assert captured == [["main.py", "--telegram-session-status"]]


def test_reuse_status_restores_session_from_login_state_path(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project")
    external_session = tmp_path / "legacy" / "telegram.session"
    external_session.parent.mkdir(parents=True, exist_ok=True)
    external_session.write_bytes(b"SQLite format 3\x00payload")
    store.telegram_login_state_file(account).write_text(
        (
            "{"
            f"\"session_path\":\"{external_session}\","
            "\"current_auth_step\":\"WAIT_CODE\""
            "}"
        ),
        encoding="utf-8",
    )
    captured: list[list[str]] = []

    def runner(_account: Account, args: list[str]) -> subprocess.CompletedProcess:
        captured.append(args)
        return _completed(0, stdout="Telegram session is authorized.")

    service = TelegramAuthService(store, runner)

    status = service.reuse_status(account)

    assert status is not None
    assert status.ok is True
    assert store.is_valid_telegram_session(account) is True
    assert store.telegram_session_file(account).read_bytes() == external_session.read_bytes()
    assert captured == [["main.py", "--telegram-session-status"]]


def test_copy_session_copies_session_and_credentials(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    source = Account(id="source", name="Source", path="/tmp/project", phone_number="+380501112233")
    target = Account(id="target", name="Target", path="/tmp/project")
    store.telegram_session_file(source).write_bytes(b"SQLite format 3\x00payload")
    store.telegram_credentials_file(source).write_text(
        "SHAFA_TELEGRAM_API_ID=777000\nSHAFA_TELEGRAM_API_HASH=secret-hash\n",
        encoding="utf-8",
    )

    service = TelegramAuthService(store, lambda *_args, **_kwargs: _completed(0))

    service.copy_session(source, target)

    assert store.telegram_session_file(target).read_bytes() == b"SQLite format 3\x00payload"
    assert store.telegram_credentials_file(target).read_text(encoding="utf-8") == (
        "SHAFA_TELEGRAM_API_ID=777000\nSHAFA_TELEGRAM_API_HASH=secret-hash\n"
    )


def test_reuse_status_rejects_unauthorized_existing_session(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    account = Account(id="acc", name="Test", path="/tmp/project")
    store.telegram_session_file(account).write_bytes(b"SQLite format 3\x00payload")
    service = TelegramAuthService(
        store,
        lambda *_args, **_kwargs: _completed(1, stderr="Telegram session is missing or unauthorized."),
    )

    status = service.reuse_status(account)

    assert status is None


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
    assert service.validate_code("12 345").message == "12345"
    assert service.validate_code("123-456").message == "123456"
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
        session_path="/tmp/telegram.session",
        code_confirmed=True,
        extra={"phone_code_hash": "hash"},
    )

    state = service.load_auth_state(account)

    assert state["phone_number"] == "+380501112233"
    assert state["verification_code"] == "123456"
    assert state["current_auth_step"] == "WAIT_CODE"
    assert state["phone_code_hash"] == "hash"
    assert state["session_path"] == "/tmp/telegram.session"
    assert state["code_confirmed"] is True


def test_request_code_button_stays_clickable_for_selected_account_without_credentials() -> None:
    class _FakeInput:
        def __init__(self, value: str) -> None:
            self._value = value

        def text(self) -> str:
            return self._value

    class _FakeButton:
        def __init__(self) -> None:
            self.enabled: bool | None = None

        def setEnabled(self, value: bool) -> None:
            self.enabled = value

    class _FakePage:
        def __init__(self) -> None:
            self.telegram_auth_in_progress = False
            self.telegram_credentials_ready = False
            self.phone_input = _FakeInput("")
            self.telegram_code_input = _FakeInput("")
            self.telegram_password_input = _FakeInput("")
            self.telegram_auth_btn = _FakeButton()
            self.telegram_submit_code_btn = _FakeButton()
            self.telegram_submit_password_btn = _FakeButton()

        def selected_row(self) -> int:
            return 0

    page = _FakePage()

    AccountsPage._sync_telegram_button_state(page)

    assert page.telegram_auth_btn.enabled is True
    assert page.telegram_submit_code_btn.enabled is False
    assert page.telegram_submit_password_btn.enabled is False


def test_preferred_project_dir_uses_shafa_logic_subproject_when_available(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("from telegram_accounts_api.main import app\n", encoding="utf-8")
    shafa_logic_dir = tmp_path / "shafa_logic"
    shafa_logic_dir.mkdir()
    (shafa_logic_dir / "main.py").write_text("print('cli')\n", encoding="utf-8")

    assert _preferred_project_dir(tmp_path) == shafa_logic_dir
