from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHAFA_LOGIC_DIR = ROOT / "shafa_logic"
for path in (ROOT, SHAFA_LOGIC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

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


def test_clothes_mode_uses_db_queue_without_direct_fetch(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "clothes")
    calls: list[str] = []
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})
    monkeypatch.setattr(dc, "telegram_products_exist", lambda **kwargs: False)

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=dc.should_run_first_fetch(),
        )
    )

    assert result == {"ok": True}
    assert calls == []


def test_sneakers_mode_uses_db_queue_without_direct_fetch(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")
    calls: list[str] = []
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})
    monkeypatch.setattr(dc, "telegram_products_exist", lambda **kwargs: False)

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=dc.should_run_first_fetch(),
        )
    )

    assert result == {"ok": True}
    assert calls == []


def test_runtime_mode_is_globally_accessible(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")

    assert dc.get_runtime_mode() == "sneakers"


def test_sneakers_mode_filters_non_sneaker_items(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "sneakers")

    assert dc.is_mode_allowed_parsed({"word_for_slack": "sneakers", "size": "40"}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "slack", "size": "40"}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "", "size": "40", "additional_sizes": []}) is True
    assert dc.is_mode_allowed_parsed({"word_for_slack": "", "size": "XS", "additional_sizes": []}) is False


def test_clothes_mode_skips_first_fetch_when_shared_feed_exists(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "clothes")
    monkeypatch.setattr(dc, "telegram_products_exist", lambda **kwargs: True)

    assert dc.should_run_first_fetch() is False


def test_shared_fetch_skip_uses_existing_queue_without_new_poll(monkeypatch) -> None:
    monkeypatch.setenv("SHAFA_APP_MODE", "clothes")
    calls: list[str] = []
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=False,
        )
    )

    assert result == {"ok": True}
    assert calls == []


def test_get_next_product_for_upload_accepts_scan_before_pick_and_skips_poll(monkeypatch) -> None:
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})
    monkeypatch.setattr(
        dc,
        "_claim_shared_telegram_fetch",
        lambda: (_ for _ in ()).throw(AssertionError("fetch should not be claimed")),
    )

    result = dc.get_next_product_for_upload(
        message_amount=50,
        first_fetch_check=False,
        scan_before_pick=False,
    )

    assert result == {"ok": True}


def test_get_next_product_for_upload_prefers_existing_queue_before_poll(monkeypatch) -> None:
    monkeypatch.setattr(dc, "_pick_next_product_for_upload", lambda: {"ok": True})
    monkeypatch.setattr(
        dc,
        "_claim_shared_telegram_fetch",
        lambda: (_ for _ in ()).throw(AssertionError("fetch should not be claimed")),
    )

    result = asyncio.run(
        dc.get_next_product_for_upload_async(
            message_amount=50,
            first_fetch_check=True,
            scan_before_pick=True,
        )
    )

    assert result == {"ok": True}
