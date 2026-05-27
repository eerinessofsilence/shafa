import _test_path  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import controller.data_controller as dc


class _FakeTelegramClient:
    def __init__(self, messages_by_peer: dict[object, list[object]]) -> None:
        self.messages_by_peer = messages_by_peer
        self.calls: list[dict] = []

    async def iter_messages(self, peer, **kwargs):
        self.calls.append({"peer": peer, **kwargs})
        messages = list(self.messages_by_peer.get(peer, []))
        search = str(kwargs.get("search") or "").casefold()
        if search:
            messages = [
                message
                for message in messages
                if search in str(getattr(message, "message", "") or "").casefold()
            ]
        limit = kwargs.get("limit")
        if isinstance(limit, int):
            messages = messages[:limit]
        for message in messages:
            yield message


class _FakeTelegramContext:
    def __init__(self, client: _FakeTelegramClient) -> None:
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _message(message_id: int, text: str):
    return SimpleNamespace(id=message_id, message=text, date=None)


class TelegramNameLookupTests(unittest.TestCase):
    def test_find_telegram_matches_by_product_name_returns_exact_match(self) -> None:
        nike_message = "Название: Nike Air Force 1\nЦена: 1600\nРазмер: 41"
        adidas_message = "Название: Adidas Campus\nЦена: 1700\nРазмер: 42"
        client = _FakeTelegramClient(
            {"peer-11": [_message(101, nike_message), _message(102, adidas_message)]}
        )
        parsed = {
            nike_message: {"name": "Nike Air Force 1", "brand": "Nike"},
            adidas_message: {"name": "Adidas Campus", "brand": "Adidas"},
        }
        with (
            patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            patch("controller.data_controller._get_channel_ids", return_value=[11]),
            patch(
                "controller.data_controller._sync_channel_titles",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "controller.data_controller._resolve_channel_peer",
                new=AsyncMock(return_value="peer-11"),
            ),
            patch(
                "controller.data_controller._require_telegram_credentials",
                return_value=(1, "hash"),
            ),
            patch(
                "controller.data_controller.create_telegram_client",
                return_value=_FakeTelegramContext(client),
            ),
            patch(
                "controller.data_controller.parse_message",
                side_effect=lambda text: parsed[text],
            ),
        ):
            results = dc.find_telegram_matches_by_product_name(
                "Nike Air Force 1",
                per_channel_limit=3,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], 101)
        self.assertEqual(results[0]["parsed_name"], "Nike Air Force 1")
        self.assertEqual(results[0]["channel_id"], 11)

    def test_find_telegram_matches_by_product_name_uses_token_fallback(self) -> None:
        exact_message = "Название: Nike Air Force 1\nЦена: 1600\nРазмер: 41"
        unrelated_message = "Название: Nike Blazer Mid\nЦена: 1700\nРазмер: 42"
        client = _FakeTelegramClient(
            {
                "peer-11": [
                    _message(201, exact_message),
                    _message(202, unrelated_message),
                ]
            }
        )
        parsed = {
            exact_message: {"name": "Nike Air Force 1", "brand": "Nike"},
            unrelated_message: {"name": "Nike Blazer Mid", "brand": "Nike"},
        }
        with (
            patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            patch("controller.data_controller._get_channel_ids", return_value=[11]),
            patch(
                "controller.data_controller._sync_channel_titles",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "controller.data_controller._resolve_channel_peer",
                new=AsyncMock(return_value="peer-11"),
            ),
            patch(
                "controller.data_controller._require_telegram_credentials",
                return_value=(1, "hash"),
            ),
            patch(
                "controller.data_controller.create_telegram_client",
                return_value=_FakeTelegramContext(client),
            ),
            patch(
                "controller.data_controller.parse_message",
                side_effect=lambda text: parsed[text],
            ),
        ):
            results = dc.find_telegram_matches_by_product_name(
                "Nike Air Force 1 Low",
                per_channel_limit=3,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], 201)
        search_queries = [str(call.get("search") or "") for call in client.calls]
        self.assertIn("Nike Air Force 1 Low", search_queries)
        self.assertIn("Force", search_queries)

    @patch("controller.data_controller.find_telegram_matches_by_product_name")
    def test_inspect_shafa_product_telegram_age_marks_old_match_as_eligible(
        self,
        find_matches,
    ) -> None:
        old_date = (datetime.now(timezone.utc) - timedelta(days=220)).isoformat()
        find_matches.return_value = [
            {
                "channel_id": 11,
                "channel_name": "Main",
                "message_id": 501,
                "parsed_name": "Nike Air Force 1",
                "score": 0.97,
                "telegram_message_date": old_date,
            }
        ]

        result = dc.inspect_shafa_product_telegram_age(
            "Nike Air Force 1",
            older_than_days=183,
        )

        self.assertEqual(result["status"], "eligible")
        self.assertTrue(result["eligible_for_deactivation"])
        best_match = result["best_match"]
        self.assertIsInstance(best_match, dict)
        self.assertGreater(float(best_match["message_age_days"]), 183.0)

    @patch("controller.data_controller.find_telegram_matches_by_product_name")
    def test_inspect_shafa_product_telegram_age_keeps_fresh_match_active(
        self,
        find_matches,
    ) -> None:
        fresh_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        find_matches.return_value = [
            {
                "channel_id": 11,
                "channel_name": "Main",
                "message_id": 777,
                "parsed_name": "Nike Air Force 1",
                "score": 0.99,
                "telegram_message_date": fresh_date,
            }
        ]

        result = dc.inspect_shafa_product_telegram_age(
            "Nike Air Force 1",
            older_than_days=183,
        )

        self.assertEqual(result["status"], "not_old_enough")
        self.assertFalse(result["eligible_for_deactivation"])
