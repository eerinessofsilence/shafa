from __future__ import annotations

import asyncio

from shafa_control import AppConfig, AppConfigStore
from controller import data_controller as dc


def test_app_config_store_round_trip(tmp_path, monkeypatch) -> None:
    store = AppConfigStore(tmp_path / "app_config.json")
    store.save(AppConfig(mode="sneakers"))

    loaded = store.load()

    assert loaded.mode == "sneakers"


def test_invalid_mode_falls_back_to_clothes_on_load(tmp_path) -> None:
    path = tmp_path / "app_config.json"
    path.write_text('{"mode":"broken"}', encoding="utf-8")

    loaded = AppConfigStore(path).load()

    assert loaded.mode == "clothes"


def test_clothes_mode_triggers_first_fetch(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "clothes")
    calls: list[str] = []

    async def fake_first_fetch() -> int:
        calls.append("first_fetch")
        return 1

    async def fake_fetch_messages(message_amount: int = 200) -> int:
        calls.append(f"fetch:{message_amount}")
        return 0

    monkeypatch.setattr(dc, "first_fetch", fake_first_fetch)
    monkeypatch.setattr(dc, "_fetch_messages", fake_fetch_messages)
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=dc.should_run_first_fetch(),
        )
    )

    assert result == {"ok": True}
    assert calls == ["first_fetch"]


def test_sneakers_mode_does_not_trigger_first_fetch(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")
    calls: list[str] = []

    async def fake_first_fetch() -> int:
        calls.append("first_fetch")
        return 1

    async def fake_fetch_messages(message_amount: int = 200) -> int:
        calls.append(f"fetch:{message_amount}")
        return 0

    monkeypatch.setattr(dc, "first_fetch", fake_first_fetch)
    monkeypatch.setattr(dc, "_fetch_messages", fake_fetch_messages)
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=dc.should_run_first_fetch(),
        )
    )

    assert result == {"ok": True}
    assert calls == ["fetch:50"]


def test_runtime_mode_is_globally_accessible(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")

    assert dc.get_runtime_mode() == "sneakers"


def test_sneakers_mode_filters_non_sneaker_items(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")

    assert dc.is_mode_allowed_parsed({"word_for_slack": "sneakers", "size": "40"}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "slack", "size": "40"}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "", "size": "40", "additional_sizes": []}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "", "size": "XS", "additional_sizes": []}) is False
