from __future__ import annotations

import json
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
    store.auth_file(account).write_text('{"cookies":[{"name":"csrftoken"}]}', encoding="utf-8")
    store.telegram_session_file(account).write_bytes(b"sqlite")
    store.telegram_login_state_file(account).write_text("{}", encoding="utf-8")

    assert store.is_valid_shafa_session(account) is True
    assert store.is_valid_telegram_session(account) is True
    assert store.has_pending_telegram_code(account) is True

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

    store.copy_telegram_session(source, target)
    assert store.is_valid_telegram_session(target) is True

    exported = tmp_path / "exported.session"
    store.export_telegram_session(target, exported)
    assert exported.exists()

    imported_target = Account(id="imp", name="Imported", path="/tmp/project")
    store.import_telegram_session(imported_target, exported)
    assert store.is_valid_telegram_session(imported_target) is True
