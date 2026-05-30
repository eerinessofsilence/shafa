from __future__ import annotations

from pathlib import Path

from shafa_control import (
    Account,
    AccountRuntimeService,
    AccountSessionStore,
    configured_runtime_project_dir,
    default_project_dir,
    project_root_dir,
    python_candidates,
    resolve_project_dir,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.storage import JsonListStorage


def test_account_runtime_builds_env_and_paths(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    account = Account(id="acc-1", name="Primary", path=str(tmp_path / "project"))
    store.save_telegram_credentials(account, "777000", "secret-hash")

    env = runtime.account_env(account, app_mode="sneakers", base_env={"BASE": "1"})

    assert env["BASE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["SHAFA_APP_MODE"] == "sneakers"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["SHAFA_ACCOUNT_STATE_DIR"].endswith("accounts/acc-1")
    assert env["SHAFA_STORAGE_STATE_PATH"].endswith("accounts/acc-1/auth.json")
    assert env["SHAFA_DB_PATH"].endswith("accounts/acc-1/shafa.sqlite3")
    assert env["SHAFA_SHARED_TELEGRAM_DB_PATH"].endswith("telegram_shared/telegram_feed.sqlite3")
    assert env["SHAFA_CREATION_PRODUCTS_DB_PATH"].endswith(
        "telegram_shared/creation_products.sqlite3"
    )
    assert env["SHAFA_MEDIA_DIR_PATH"].endswith("accounts/acc-1/media")
    assert env["SHAFA_TELEGRAM_SESSION_PATH"].endswith("accounts/acc-1/telegram.session")
    assert env["SHAFA_TELEGRAM_CHANNELS_PATH"].endswith("accounts/acc-1/shafa_telegram_channels.json")
    assert env["SHAFA_TELEGRAM_QUEUE_SEED_MARKER_PATH"].endswith(
        "accounts/acc-1/seed_existing_telegram_products.pending"
    )
    assert "SHAFA_TELEGRAM_QUEUE_SEED_PENDING" not in env
    assert env["SHAFA_ACCOUNT_ID"] == "acc-1"
    assert env["SHAFA_ACCOUNT_NAME"] == "Primary"
    assert env["SHAFA_TELEGRAM_API_ID"] == "777000"
    assert env["SHAFA_TELEGRAM_API_HASH"] == "secret-hash"


def test_account_service_runtime_accounts_use_canonical_storage_not_stale_index(
    tmp_path: Path,
) -> None:
    accounts_dir = tmp_path / "accounts"
    storage_path = tmp_path / "accounts_state.json"
    accounts_dir.mkdir()
    storage_path.write_text(
        '[{"id":"acc-canonical","name":"Canonical","path":"/canonical"}]',
        encoding="utf-8",
    )
    (accounts_dir / "index.json").write_text(
        '[{"id":"acc-stale","name":"Stale","path":"/stale"}]',
        encoding="utf-8",
    )
    service = AccountService(
        storage=JsonListStorage(storage_path),
        accounts_dir=accounts_dir,
    )

    accounts = service.load_runtime_accounts()

    assert [account.id for account in accounts] == ["acc-canonical"]


def test_account_runtime_sets_account_price_markup(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    account = Account(
        id="acc-markup",
        name="Markup",
        path=str(tmp_path / "project"),
        markup_amount=650,
    )

    env = runtime.account_env(account, base_env={"SHAFA_PRICE_MARKUP": "400"})

    assert env["SHAFA_PRICE_MARKUP"] == "650"


def test_account_runtime_clears_inherited_price_markup(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    account = Account(id="acc-markup", name="Markup", path=str(tmp_path / "project"))

    env = runtime.account_env(account, base_env={"SHAFA_PRICE_MARKUP": "400"})

    assert "SHAFA_PRICE_MARKUP" not in env


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
    assert env["PYTHONIOENCODING"] == "utf-8"
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
    assert first_env["SHAFA_SHARED_TELEGRAM_DB_PATH"] == second_env["SHAFA_SHARED_TELEGRAM_DB_PATH"]
    assert first_env["SHAFA_TELEGRAM_CHANNELS_PATH"].endswith("accounts/acc-1/shafa_telegram_channels.json")
    assert second_env["SHAFA_TELEGRAM_CHANNELS_PATH"].endswith("accounts/acc-2/shafa_telegram_channels.json")
    assert first_env["SHAFA_TELEGRAM_CHANNELS_PATH"] != second_env["SHAFA_TELEGRAM_CHANNELS_PATH"]
    assert first_env["SHAFA_MEDIA_DIR_PATH"].endswith("accounts/acc-1/media")
    assert second_env["SHAFA_MEDIA_DIR_PATH"].endswith("accounts/acc-2/media")
    assert first_env["SHAFA_MEDIA_DIR_PATH"] != second_env["SHAFA_MEDIA_DIR_PATH"]


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


def test_account_runtime_exposes_pending_new_account_queue_seed_marker(tmp_path: Path) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    account = Account(id="acc-seed", name="Seed", path=str(tmp_path / "project"))
    store.mark_pending_telegram_queue_seed(account)

    env = runtime.account_env(account)

    assert env["SHAFA_TELEGRAM_QUEUE_SEED_PENDING"] == "1"
    assert env["SHAFA_TELEGRAM_QUEUE_SEED_MARKER_PATH"].endswith(
        "accounts/acc-seed/seed_existing_telegram_products.pending"
    )


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


def test_python_candidates_include_project_and_root_venvs(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    shafa_logic_dir = project_root / "shafa_logic"
    shafa_logic_dir.mkdir(parents=True)
    (shafa_logic_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

    candidates = python_candidates(shafa_logic_dir, windows=True)

    assert candidates == [
        shafa_logic_dir / ".venv" / "Scripts" / "python.exe",
        shafa_logic_dir / "venv" / "Scripts" / "python.exe",
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / "venv" / "Scripts" / "python.exe",
    ]
    assert project_root_dir(shafa_logic_dir) == project_root


def test_account_runtime_prefers_root_venv_when_project_path_is_shafa_logic(
    tmp_path: Path,
) -> None:
    store = AccountSessionStore(tmp_path, tmp_path / "accounts", tmp_path / "accounts_state.json")
    runtime = AccountRuntimeService(store)
    project_root = tmp_path / "project"
    shafa_logic_dir = project_root / "shafa_logic"
    shafa_logic_dir.mkdir(parents=True)
    (shafa_logic_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    python_exe = project_root / "venv" / "bin" / "python"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    account = Account(id="acc-win", name="Win", path=str(project_root))

    assert runtime.account_python(account) == str(python_exe)
