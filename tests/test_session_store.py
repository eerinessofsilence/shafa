from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from shafa_control import Account, AccountSessionStore


def test_session_store_writes_index_and_account_manifest(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(
        id="acc-1",
        name="Primary",
        path="/tmp/project",
        phone_number="+380123456789",
        channel_links=["https://t.me/example"],
    )

    store.save_accounts([account])

    index_payload = json.loads((tmp_path / "Shuffa" / "index.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((tmp_path / "Shuffa" / "acc-1" / "account.json").read_text(encoding="utf-8"))

    assert index_payload[0]["id"] == "acc-1"
    assert index_payload[0]["phone_number"] == "+380123456789"
    assert manifest_payload["telegram_session_path"].endswith("Shuffa/acc-1/telegram.session")
    assert manifest_payload["browser_session_path"].endswith("Shuffa/acc-1/auth.json")
    assert manifest_payload["telegram_credentials_path"].endswith("Shuffa/acc-1/.env")
    assert manifest_payload["telegram_credentials_configured"] is False


def test_session_store_reads_legacy_file_when_index_missing(tmp_path: Path) -> None:
    legacy_file = tmp_path / "accounts_state.json"
    legacy_file.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-1",
                    "name": "Legacy",
                    "path": "/tmp/legacy",
                    "phone_number": "+1",
                }
            ]
        ),
        encoding="utf-8",
    )
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "accounts",
        legacy_state_file=legacy_file,
    )

    accounts = store.load_accounts()

    assert [account.id for account in accounts] == ["legacy-1"]
    assert accounts[0].status == "stopped"
    assert accounts[0].process is None


def test_session_store_validates_and_deletes_sessions(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(id="acc-2", name="Secondary", path="/tmp/project")
    store.auth_file(account).write_text(
        '{"cookies":[{"name":"csrftoken","value":"token","domain":".shafa.ua"}]}',
        encoding="utf-8",
    )
    store.telegram_session_file(account).write_bytes(b"sqlite")
    store.telegram_login_state_file(account).write_text("{}", encoding="utf-8")

    assert store.is_valid_shafa_session(account) is True
    assert store.is_valid_telegram_session(account) is True
    assert store.has_pending_telegram_code(account) is False

    store.delete_shafa_session(account)
    store.delete_telegram_session(account)

    assert store.is_valid_shafa_session(account) is False
    assert store.is_valid_telegram_session(account) is False
    assert store.has_pending_telegram_code(account) is False


def test_session_store_copies_imports_and_exports_telegram_sessions(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    source = Account(id="src", name="Source", path="/tmp/project")
    target = Account(id="dst", name="Target", path="/tmp/project")
    source_session = store.telegram_session_file(source)
    source_session.write_bytes(b"SQLite format 3\x00payload")
    store.save_telegram_credentials(source, "123456", "hash-value")

    store.copy_telegram_session(source, target)
    assert store.is_valid_telegram_session(target) is True
    assert store.has_telegram_credentials(target) is True
    assert store.load_telegram_credentials(target)["SHAFA_TELEGRAM_API_ID"] == "123456"

    exported = tmp_path / "exported.session"
    store.export_telegram_session(target, exported)
    assert exported.exists()

    imported_target = Account(id="imp", name="Imported", path="/tmp/project")
    store.import_telegram_session(imported_target, exported)
    assert store.is_valid_telegram_session(imported_target) is True


def test_has_pending_telegram_code_only_for_active_auth_steps(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(id="acc", name="Test", path="/tmp/project")
    state_file = store.telegram_login_state_file(account)

    state_file.write_text('{"current_auth_step":"IDLE"}', encoding="utf-8")
    assert store.has_pending_telegram_code(account) is False

    state_file.write_text('{"current_auth_step":"WAIT_CODE_INPUT"}', encoding="utf-8")
    assert store.has_pending_telegram_code(account) is True

    state_file.write_text('{"current_auth_step":"FAILED"}', encoding="utf-8")
    assert store.has_pending_telegram_code(account) is False


def test_session_store_copies_shafa_session(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    source = Account(id="src", name="Source", path="/tmp/project")
    target = Account(id="dst", name="Target", path="/tmp/project")
    store.auth_file(source).write_text(
        '{"cookies":[{"name":"csrftoken","value":"token","domain":".shafa.ua"}]}',
        encoding="utf-8",
    )

    store.copy_shafa_session(source, target)

    assert store.is_valid_shafa_session(target) is True


def test_session_store_rejects_shafa_session_without_shafa_csrftoken(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(id="acc-3", name="Broken", path="/tmp/project")

    store.auth_file(account).write_text(
        '{"cookies":[{"name":"sessionid","value":"x","domain":".example.com"}]}',
        encoding="utf-8",
    )
    assert store.is_valid_shafa_session(account) is False

    store.auth_file(account).write_text(
        '{"cookies":[{"name":"csrftoken","value":"","domain":".shafa.ua"}]}',
        encoding="utf-8",
    )
    assert store.is_valid_shafa_session(account) is False


def test_session_store_persists_telegram_credentials_in_env_file(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(id="acc-4", name="Creds", path="/tmp/project")

    path = store.save_telegram_credentials(account, "777000", "secret-hash")

    assert path.name == ".env"
    assert "SHAFA_TELEGRAM_API_ID=777000" in path.read_text(encoding="utf-8")
    assert store.has_telegram_credentials(account) is True
    assert store.load_telegram_credentials(account) == {
        "SHAFA_TELEGRAM_API_ID": "777000",
        "SHAFA_TELEGRAM_API_HASH": "secret-hash",
    }


def test_delete_shafa_session_clears_runtime_cookie_store(tmp_path: Path) -> None:
    store = AccountSessionStore(
        base_dir=tmp_path,
        accounts_dir=tmp_path / "Shuffa",
        legacy_state_file=tmp_path / "accounts_state.json",
    )
    account = Account(id="acc-5", name="Cookie DB", path="/tmp/project")

    store.auth_file(account).write_text(
        '{"cookies":[{"name":"csrftoken","value":"token","domain":".shafa.ua"}]}',
        encoding="utf-8",
    )
    db_path = store.db_file(account)

    with sqlite3.connect(db_path) as conn:
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
            (".shafa.ua", "csrftoken", "token"),
        )
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO products(name) VALUES (?)", ("kept-row",))

    store.delete_shafa_session(account)

    assert store.auth_file(account).exists() is False
    with sqlite3.connect(db_path) as conn:
        cookies_count = conn.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
        products_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert cookies_count == 0
    assert products_count == 1
