from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram_channels import (
    DEFAULT_CHANNEL_ALIAS,
    export_runtime_config,
    load_runtime_config,
    parse_id_bot_response,
    resolve_channel_tuples,
    sanitize_channel_links,
)


class StubIdBotClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def fetch_response(self, link: str) -> str:
        return self.responses[link]


def test_sanitize_channel_links_normalizes_and_deduplicates() -> None:
    links = sanitize_channel_links(
        [
            "t.me/sample_channel",
            "https://t.me/sample_channel",
            " https://t.me/another_channel ",
        ]
    )

    assert links == [
        "https://t.me/sample_channel",
        "https://t.me/another_channel",
    ]


def test_parse_id_bot_response_extracts_id_and_title() -> None:
    channel_id, title = parse_id_bot_response(
        "Chat ID: -1001234567890\nTitle: My Sample Channel"
    )

    assert channel_id == -1001234567890
    assert title == "My Sample Channel"


def test_export_and_load_runtime_config(tmp_path: Path) -> None:
    output_path = export_runtime_config(
        account_name="Account 1",
        account_path="/tmp/account",
        links=["t.me/sample_channel"],
        output_dir=tmp_path,
    )

    config = load_runtime_config(output_path)

    assert config.account_name == "Account 1"
    assert config.account_path == "/tmp/account"
    assert config.links == ["https://t.me/sample_channel"]


def test_resolve_channel_tuples_builds_expected_shape() -> None:
    link = "https://t.me/sample_channel"
    client = StubIdBotClient(
        {
            link: "ID: -100777\nTitle: Sample Title",
        }
    )

    result = resolve_channel_tuples([link], client)

    assert result == [(-100777, "Sample Title", DEFAULT_CHANNEL_ALIAS)]
