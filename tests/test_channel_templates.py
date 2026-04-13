from __future__ import annotations

from shafa_control import ChannelTemplateStore


def test_create_and_persist_channel_template(tmp_path) -> None:
    store = ChannelTemplateStore(tmp_path / "channel_templates.json")

    template = store.save_template("Default", ["t.me/one", "https://t.me/two"])
    reloaded = ChannelTemplateStore(tmp_path / "channel_templates.json").get_template("Default")

    assert template.links == ["https://t.me/one", "https://t.me/two"]
    assert reloaded.links == ["https://t.me/one", "https://t.me/two"]


def test_missing_template_file_returns_empty_list(tmp_path) -> None:
    store = ChannelTemplateStore(tmp_path / "missing.json")

    assert store.list_templates() == []


def test_empty_channel_list_is_rejected(tmp_path) -> None:
    store = ChannelTemplateStore(tmp_path / "channel_templates.json")

    try:
        store.save_template("Empty", [])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty channel list")


def test_template_data_integrity_after_restart(tmp_path) -> None:
    path = tmp_path / "channel_templates.json"
    store = ChannelTemplateStore(path)
    store.save_template("Sneakers", ["https://t.me/sneakers", "https://t.me/slack"])

    loaded = ChannelTemplateStore(path).list_templates()

    assert [(item.name, item.links) for item in loaded] == [
        ("Sneakers", ["https://t.me/sneakers", "https://t.me/slack"])
    ]


def test_combined_mode_and_template_behavior(tmp_path) -> None:
    config_path = tmp_path / "app_config.json"
    template_path = tmp_path / "channel_templates.json"

    from shafa_control import AppConfig, AppConfigStore

    AppConfigStore(config_path).save(AppConfig(mode="sneakers"))
    ChannelTemplateStore(template_path).save_template("Sneakers", ["https://t.me/sneakers"])

    assert AppConfigStore(config_path).load().mode == "sneakers"
    assert ChannelTemplateStore(template_path).get_template("Sneakers").links == ["https://t.me/sneakers"]
