import _test_path  # noqa: F401
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import io

from telegram_subscription.sync import (
    _channel_tuple_from_entity,
    _extract_search_query,
    _log,
    _resolve_channel_tuples,
    get_configured_telegram_channel_records,
    get_telegram_channel_records,
    get_telegram_channels,
    sync_channels_from_runtime_config,
    parse_id_bot_response,
    set_telegram_channels,
)


class TelegramSubscriptionTests(unittest.TestCase):
    @staticmethod
    def _make_client(authorized: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=authorized),
        )

    def test_parse_id_bot_response_extracts_id_and_title(self) -> None:
        channel_id, title = parse_id_bot_response(
            "🆔 ID: -1001234567890\n📝 Title: Sample Channel\nUsername: ignore_me"
        )

        self.assertEqual(channel_id, -1001234567890)
        self.assertEqual(title, "Sample Channel")

    def test_parse_id_bot_response_raises_with_raw_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "Raw response"):
            parse_id_bot_response("unexpected bot text without id")

    def test_log_falls_back_when_stdout_cannot_encode_unicode(self) -> None:
        class _BrokenEncodingStream(io.StringIO):
            encoding = "cp1251"

            def write(self, s: str) -> int:
                s.encode(self.encoding)
                return super().write(s)

        stream = _BrokenEncodingStream()

        with patch("sys.stdout", stream):
            _log("failed to resolve https://t.me/test: fox 🦊")

        self.assertIn("failed to resolve https://t.me/test: fox ?", stream.getvalue())

    def test_runtime_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            channels_path = Path(temp_dir) / "shafa_telegram_channels.json"
            expected = [
                (-1001, "Channel One", "main extra_photos"),
                (-1002, "Channel Two", "main extra_photos"),
            ]

            with patch("telegram_subscription.sync._mirror_channels_to_db"):
                set_telegram_channels([(-1001, "Channel One", "main"), (-1002, "Channel Two", "")], path=channels_path)
                actual = get_telegram_channels(path=channels_path)

        self.assertEqual(actual, expected)

    def test_runtime_json_preserves_source_link_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            channels_path = Path(temp_dir) / "shafa_telegram_channels.json"

            with patch("telegram_subscription.sync._mirror_channels_to_db"):
                set_telegram_channels(
                    [
                        {
                            "channel_id": -1001,
                            "name": "Channel One",
                            "alias": "main",
                            "source_link": "https://t.me/+invite_hash",
                        }
                    ],
                    path=channels_path,
                )
                records = get_telegram_channel_records(path=channels_path)

        self.assertEqual(records[0]["source_link"], "https://t.me/+invite_hash")

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

        self.assertEqual(result, (-100123, "Sample Channel", "main extra_photos"))

    def test_full_pipeline_resolves_link_to_tuple(self) -> None:
        client = self._make_client()
        with (
            patch("telegram_subscription.sync._require_telegram_credentials", return_value=(1, "hash")),
            patch("telegram_subscription.sync._get_telegram_client_cls") as telegram_client_cls,
            patch("telegram_subscription.sync._ensure_channel_membership", new=AsyncMock(return_value=None)) as ensure_membership,
            patch(
                "telegram_subscription.sync._fetch_id_bot_response",
                new=AsyncMock(return_value="🆔 ID: -1001801709326\n📝 Title: GENERATION DROP / OPT 🌊"),
            ) as fetch_response,
        ):
            telegram_client_cls.return_value = lambda *_args, **_kwargs: client
            result = asyncio.run(_resolve_channel_tuples(["https://t.me/generation_drop"]))

        self.assertEqual(result, [(-1001801709326, "GENERATION DROP / OPT 🌊", "main extra_photos")])
        ensure_membership.assert_awaited_once_with(client, "https://t.me/generation_drop")
        fetch_response.assert_awaited_once_with(client, "https://t.me/generation_drop")
        client.connect.assert_awaited_once()
        client.disconnect.assert_awaited_once()
        client.is_user_authorized.assert_awaited_once()

    def test_full_pipeline_prefers_entity_resolution_without_id_bot(self) -> None:
        client = self._make_client()
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
            telegram_client_cls.return_value = lambda *_args, **_kwargs: client
            result = asyncio.run(_resolve_channel_tuples(["https://t.me/generation_drop"]))

        self.assertEqual(result, [(-1001801709326, "GENERATION DROP / OPT 🌊", "main extra_photos")])
        ensure_membership.assert_awaited_once_with(client, "https://t.me/generation_drop")
        fetch_response.assert_not_awaited()

    def test_failure_tolerance_skips_bad_channel_and_keeps_batch_running(self) -> None:
        client = self._make_client()

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
            telegram_client_cls.return_value = lambda *_args, **_kwargs: client
            result = asyncio.run(
                _resolve_channel_tuples(
                    ["https://t.me/bad_channel", "https://t.me/good_channel"]
                )
            )

        self.assertEqual(result, [(-1007, "Good Channel", "main extra_photos")])

    def test_full_pipeline_raises_for_unauthorized_session(self) -> None:
        client = self._make_client(authorized=False)
        with (
            patch("telegram_subscription.sync._require_telegram_credentials", return_value=(1, "hash")),
            patch("telegram_subscription.sync._get_telegram_client_cls", return_value=lambda *_args, **_kwargs: client),
        ):
            with self.assertRaisesRegex(RuntimeError, "не авторизована"):
                asyncio.run(_resolve_channel_tuples(["https://t.me/generation_drop"]))

        client.connect.assert_awaited_once()
        client.disconnect.assert_awaited_once()
        client.is_user_authorized.assert_awaited_once()

    def test_sync_channels_reuses_saved_channels_when_session_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime_links.json"
            saved_channels_path = Path(temp_dir) / "shafa_telegram_channels.json"
            config_path.write_text(
                json.dumps({"links": ["https://t.me/generation_drop"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            saved_channels = [(-100123, "Saved Channel", "main extra_photos")]
            with patch("telegram_subscription.sync._runtime_channels_path", return_value=saved_channels_path):
                with patch("telegram_subscription.sync._mirror_channels_to_db"):
                    set_telegram_channels(saved_channels, path=saved_channels_path)
                with (
                    patch.dict("os.environ", {"SHAFA_TELEGRAM_CHANNEL_LINKS_FILE": str(config_path)}, clear=False),
                    patch(
                        "telegram_subscription.sync._resolve_channel_records",
                        side_effect=RuntimeError("Сессия Telegram отсутствует или не авторизована."),
                    ),
                ):
                    result = sync_channels_from_runtime_config()

        self.assertEqual(result, saved_channels)

    def test_sync_channels_keeps_only_configured_existing_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime_links.json"
            channels_path = Path(temp_dir) / "shafa_telegram_channels.json"
            config_path.write_text(
                json.dumps(
                    {"links": ["https://t.me/channel_one", "https://t.me/channel_two"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("telegram_subscription.sync._runtime_channels_path", return_value=channels_path):
                with patch("telegram_subscription.sync._mirror_channels_to_db"):
                    set_telegram_channels(
                        [
                            {
                                "channel_id": -1001,
                                "name": "Channel One",
                                "alias": "main",
                                "source_link": "https://t.me/channel_one",
                            },
                            {
                                "channel_id": -1009,
                                "name": "Stale Channel",
                                "alias": "main",
                                "source_link": "https://t.me/stale_channel",
                            },
                        ],
                        path=channels_path,
                    )
                with (
                    patch.dict(
                        "os.environ",
                        {"SHAFA_TELEGRAM_CHANNEL_LINKS_FILE": str(config_path)},
                        clear=False,
                    ),
                    patch(
                        "telegram_subscription.sync._resolve_channel_records",
                        new=AsyncMock(
                            return_value=[
                                {
                                    "channel_id": -1002,
                                    "name": "Channel Two",
                                    "alias": "main extra_photos",
                                    "source_link": "https://t.me/channel_two",
                                }
                            ]
                        ),
                    ),
                ):
                    result = sync_channels_from_runtime_config()
                    records = get_telegram_channel_records(path=channels_path)

        self.assertEqual(
            result,
            [
                (-1001, "Channel One", "main extra_photos"),
                (-1002, "Channel Two", "main extra_photos"),
            ],
        )
        self.assertEqual(
            [record["source_link"] for record in records],
            ["https://t.me/channel_one", "https://t.me/channel_two"],
        )

    def test_get_configured_records_filters_locally_without_extra_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime_links.json"
            channels_path = Path(temp_dir) / "shafa_telegram_channels.json"
            config_path.write_text(
                json.dumps(
                    {"links": ["https://t.me/channel_two"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("telegram_subscription.sync._runtime_channels_path", return_value=channels_path):
                with patch("telegram_subscription.sync._mirror_channels_to_db"):
                    set_telegram_channels(
                        [
                            {
                                "channel_id": -1001,
                                "name": "Channel One",
                                "alias": "main",
                                "source_link": "https://t.me/channel_one",
                            },
                            {
                                "channel_id": -1002,
                                "name": "Channel Two",
                                "alias": "main",
                                "source_link": "https://t.me/channel_two",
                            },
                        ],
                        path=channels_path,
                    )
                with patch.dict(
                    "os.environ",
                    {"SHAFA_TELEGRAM_CHANNEL_LINKS_FILE": str(config_path)},
                    clear=False,
                ):
                    records = get_configured_telegram_channel_records(path=channels_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["channel_id"], -1002)


if __name__ == "__main__":
    unittest.main()
