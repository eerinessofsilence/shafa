import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram_subscription.sync import (
    _channel_tuple_from_entity,
    _extract_search_query,
    _resolve_channel_tuples,
    get_telegram_channels,
    parse_id_bot_response,
    set_telegram_channels,
)


class TelegramSubscriptionTests(unittest.TestCase):
    def test_parse_id_bot_response_extracts_id_and_title(self) -> None:
        channel_id, title = parse_id_bot_response(
            "🆔 ID: -1001234567890\n📝 Title: Sample Channel\nUsername: ignore_me"
        )

        self.assertEqual(channel_id, -1001234567890)
        self.assertEqual(title, "Sample Channel")

    def test_parse_id_bot_response_raises_with_raw_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "Raw response"):
            parse_id_bot_response("unexpected bot text without id")

    def test_runtime_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            channels_path = Path(temp_dir) / "shafa_telegram_channels.json"
            expected = [(-1001, "Channel One", "main"), (-1002, "Channel Two", "main")]

            with patch("telegram_subscription.sync._mirror_channels_to_db"):
                set_telegram_channels(expected, path=channels_path)
                actual = get_telegram_channels(path=channels_path)

        self.assertEqual(actual, expected)

    def test_extract_search_query_prefers_username_from_link(self) -> None:
        self.assertEqual(
            _extract_search_query("https://t.me/generation_drop"),
            "@generation_drop",
        )

    def test_extract_search_query_supports_plain_username(self) -> None:
        self.assertEqual(_extract_search_query("generation_drop"), "@generation_drop")

    def test_channel_tuple_from_entity_prefers_peer_id_and_title(self) -> None:
        entity = type("Entity", (), {"id": 123, "title": "Sample Channel"})()

        with patch("telegram_subscription.sync._get_peer_id", return_value=-100123):
            result = _channel_tuple_from_entity(entity)

        self.assertEqual(result, (-100123, "Sample Channel", "main"))

    def test_full_pipeline_resolves_link_to_tuple(self) -> None:
        client = object()
        with (
            patch("telegram_subscription.sync._require_telegram_credentials", return_value=(1, "hash")),
            patch("telegram_subscription.sync._get_telegram_client_cls") as telegram_client_cls,
            patch("telegram_subscription.sync._ensure_channel_membership", new=AsyncMock(return_value=None)) as ensure_membership,
            patch(
                "telegram_subscription.sync._fetch_id_bot_response",
                new=AsyncMock(return_value="🆔 ID: -1001801709326\n📝 Title: GENERATION DROP / OPT 🌊"),
            ) as fetch_response,
        ):
            telegram_client_cls.return_value.return_value.__aenter__.return_value = client
            result = asyncio.run(_resolve_channel_tuples(["https://t.me/generation_drop"]))

        self.assertEqual(result, [(-1001801709326, "GENERATION DROP / OPT 🌊", "main")])
        ensure_membership.assert_awaited_once_with(client, "https://t.me/generation_drop")
        fetch_response.assert_awaited_once_with(client, "https://t.me/generation_drop")

    def test_full_pipeline_prefers_entity_resolution_without_id_bot(self) -> None:
        client = object()
        entity = type("Entity", (), {"id": 1801709326, "title": "GENERATION DROP / OPT 🌊"})()
        with (
            patch("telegram_subscription.sync._require_telegram_credentials", return_value=(1, "hash")),
            patch("telegram_subscription.sync._get_telegram_client_cls") as telegram_client_cls,
            patch(
                "telegram_subscription.sync._ensure_channel_membership",
                new=AsyncMock(return_value=entity),
            ) as ensure_membership,
            patch("telegram_subscription.sync._get_peer_id", return_value=-1001801709326),
            patch("telegram_subscription.sync._fetch_id_bot_response", new=AsyncMock()) as fetch_response,
        ):
            telegram_client_cls.return_value.return_value.__aenter__.return_value = client
            result = asyncio.run(_resolve_channel_tuples(["https://t.me/generation_drop"]))

        self.assertEqual(result, [(-1001801709326, "GENERATION DROP / OPT 🌊", "main")])
        ensure_membership.assert_awaited_once_with(client, "https://t.me/generation_drop")
        fetch_response.assert_not_awaited()

    def test_failure_tolerance_skips_bad_channel_and_keeps_batch_running(self) -> None:
        client = object()

        async def fetch_side_effect(_: object, link: str) -> str:
            if "bad" in link:
                return "broken response"
            return "🆔 ID: -1007\n📝 Title: Good Channel"

        with (
            patch("telegram_subscription.sync._require_telegram_credentials", return_value=(1, "hash")),
            patch("telegram_subscription.sync._get_telegram_client_cls") as telegram_client_cls,
            patch("telegram_subscription.sync._ensure_channel_membership", new=AsyncMock(return_value=None)),
            patch(
                "telegram_subscription.sync._fetch_id_bot_response",
                new=AsyncMock(side_effect=fetch_side_effect),
            ),
        ):
            telegram_client_cls.return_value.return_value.__aenter__.return_value = client
            result = asyncio.run(
                _resolve_channel_tuples(
                    ["https://t.me/bad_channel", "https://t.me/good_channel"]
                )
            )

        self.assertEqual(result, [(-1007, "Good Channel", "main")])


if __name__ == "__main__":
    unittest.main()
