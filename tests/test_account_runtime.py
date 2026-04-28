from __future__ import annotations

from pathlib import Path

from shafa_control import (
    Account,
    AccountRuntimeService,
    AccountSessionStore,
    configured_runtime_project_dir,
    default_project_dir,
    resolve_project_dir,
)


def test_account_runtime_builds_env_and_paths(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    account = Account(id="acc-1", name="Primary", path=str(tmp_path / "project"))
    store.save_telegram_credentials(account, "777000", "secret-hash")

    env = runtime.account_env(account, app_mode="sneakers", base_env={"BASE": "1"})

    assert env["BASE"] == "1"
    assert env["SHAFA_APP_MODE"] == "sneakers"
    assert env["SHAFA_ACCOUNT_STATE_DIR"].endswith("accounts/acc-1")
    assert env["SHAFA_STORAGE_STATE_PATH"].endswith("accounts/acc-1/auth.json")
    assert env["SHAFA_DB_PATH"].endswith("accounts/acc-1/shafa.sqlite3")
    assert env["SHAFA_TELEGRAM_SESSION_PATH"].endswith("accounts/acc-1/telegram.session")
    assert env["SHAFA_TELEGRAM_API_ID"] == "777000"
    assert env["SHAFA_TELEGRAM_API_HASH"] == "secret-hash"


def test_account_runtime_uses_root_env_credentials(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    runtime.root_env_path = lambda: tmp_path / ".env"  # type: ignore[method-assign]
    (tmp_path / ".env").write_text(
        "SHAFA_TELEGRAM_API_ID=33979811\n"
        "SHAFA_TELEGRAM_API_HASH=secret-root-hash\n",
        encoding="utf-8",
    )
    account = Account(id="acc-3", name="Fallback", path=str(tmp_path / "project"))

    env = runtime.account_env(account, base_env={"BASE": "1"})

    assert env["BASE"] == "1"
    assert env["SHAFA_DB_PATH"].endswith("accounts/acc-3/shafa.sqlite3")
    assert env["SHAFA_TELEGRAM_API_ID"] == "33979811"
    assert env["SHAFA_TELEGRAM_API_HASH"] == "secret-root-hash"


def test_account_runtime_isolates_db_per_account_even_for_same_project(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    project_dir = tmp_path / "project"
    first = Account(id="acc-1", name="First", path=str(project_dir))
    second = Account(id="acc-2", name="Second", path=str(project_dir))

    first_env = runtime.account_env(first)
    second_env = runtime.account_env(second)

    assert first_env["SHAFA_DB_PATH"].endswith("accounts/acc-1/shafa.sqlite3")
    assert second_env["SHAFA_DB_PATH"].endswith("accounts/acc-2/shafa.sqlite3")
    assert first_env["SHAFA_DB_PATH"] != second_env["SHAFA_DB_PATH"]


def test_account_runtime_exports_channel_runtime_config(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    project_dir = tmp_path / "project"
    (project_dir / "shafa_logic").mkdir(parents=True)
    (project_dir / "shafa_logic" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    account = Account(
        id="acc-2",
        name="My Account",
        path=str(project_dir),
        channel_links=["t.me/one", "https://t.me/two"],
    )

    config_path = runtime.export_channel_runtime_config(account)

    assert config_path.exists()
    assert config_path.name == "my_account_telegram_channels.json"
    assert '"links": [' in config_path.read_text(encoding="utf-8")


def test_account_runtime_resolves_configured_runtime_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "backend-data" / "runtime-project"
    shafa_logic_dir = runtime_root / "shafa_logic"
    shafa_logic_dir.mkdir(parents=True)
    (shafa_logic_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setenv("SHAFA_RUNTIME_PROJECT_DIR", str(runtime_root))

    missing_project = tmp_path / "backend-data"

    assert configured_runtime_project_dir() == shafa_logic_dir
    assert default_project_dir(tmp_path) == shafa_logic_dir
    assert resolve_project_dir(missing_project) == shafa_logic_dir
