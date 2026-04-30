from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _load_config_module(monkeypatch):
    sys.modules.pop("telegram_accounts_api.utils.config", None)
    return importlib.import_module("telegram_accounts_api.utils.config")


def test_get_settings_uses_desktop_data_dir_when_present(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_ACCOUNTS_BASE_DIR", raising=False)
    monkeypatch.setenv("SHAFA_DESKTOP_DATA_DIR", str(tmp_path / "desktop-data"))
    monkeypatch.delenv("ACCOUNTS_STATE_FILE", raising=False)
    monkeypatch.delenv("MESSAGE_TEMPLATES_FILE", raising=False)
    monkeypatch.delenv("CHANNEL_TEMPLATES_STATE_FILE", raising=False)
    monkeypatch.delenv("ACCOUNTS_DIR", raising=False)

    module = _load_config_module(monkeypatch)
    settings = module.get_settings()

    expected_base_dir = (tmp_path / "desktop-data").resolve()
    assert settings.base_dir == expected_base_dir
    assert settings.accounts_file == expected_base_dir / "accounts_state.json"
    assert settings.templates_file == expected_base_dir / "message_templates.json"
    assert settings.channel_templates_file == expected_base_dir / "telegram_templates" / "channel_templates.json"
    assert settings.accounts_dir == expected_base_dir / "accounts"


def test_get_settings_defaults_to_project_root_without_env(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_ACCOUNTS_BASE_DIR", raising=False)
    monkeypatch.delenv("SHAFA_DESKTOP_DATA_DIR", raising=False)
    monkeypatch.delenv("ACCOUNTS_STATE_FILE", raising=False)
    monkeypatch.delenv("MESSAGE_TEMPLATES_FILE", raising=False)
    monkeypatch.delenv("CHANNEL_TEMPLATES_STATE_FILE", raising=False)
    monkeypatch.delenv("ACCOUNTS_DIR", raising=False)

    module = _load_config_module(monkeypatch)
    settings = module.get_settings()

    expected_base_dir = Path(__file__).resolve().parents[1]
    assert settings.base_dir == expected_base_dir
    assert settings.accounts_file == expected_base_dir / "accounts_state.json"


def test_get_settings_migrates_legacy_channel_templates_file(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "desktop-data"
    base_dir.mkdir()
    legacy_file = base_dir / "telegram_channel_templates.json"
    legacy_file.write_text('[{"name":"Legacy","links":["https://t.me/legacy"]}]', encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_ACCOUNTS_BASE_DIR", str(base_dir))
    monkeypatch.delenv("SHAFA_DESKTOP_DATA_DIR", raising=False)
    monkeypatch.delenv("CHANNEL_TEMPLATES_STATE_FILE", raising=False)

    module = _load_config_module(monkeypatch)
    settings = module.get_settings()

    expected_file = base_dir.resolve() / "telegram_templates" / "channel_templates.json"
    assert settings.channel_templates_file == expected_file
    assert expected_file.read_text(encoding="utf-8") == legacy_file.read_text(encoding="utf-8")
