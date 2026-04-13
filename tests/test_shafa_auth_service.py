from __future__ import annotations

from pathlib import Path

from shafa_control import Account, AccountSessionStore, ShafaAuthService


def test_shafa_auth_service_creates_and_confirms_context(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    service = ShafaAuthService(store)
    account = Account(id="acc-1", name="A", path="/tmp/project")

    env, context = service.create_login_context(account, {"BASE": "1"})
    service.confirm_login(context)

    assert env["BASE"] == "1"
    assert "SHAFA_LOGIN_CONFIRMATION_FILE" in env
    assert context.confirmation_file.exists()

    service.clear_context(context)
    assert not context.confirmation_file.exists()
