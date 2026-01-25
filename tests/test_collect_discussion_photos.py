import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import controller.data_controller as dc


class DummyMessage:
    def __init__(
        self,
        msg_id,
        chat_id,
        is_photo=True,
        grouped_id=None,
        reply_to=None,
        date=None,
    ):
        self.id = msg_id
        self.chat_id = chat_id
        self.is_photo = is_photo
        self.grouped_id = grouped_id
        self.reply_to = reply_to
        self.date = date


class DummyDiscussionResult:
    def __init__(self, messages, chats=None):
        self.messages = messages
        self.chats = chats or []


class FakeClient:
    def __init__(self, discussion_result, replies=None, fallback=None, aggressive=None):
        self.discussion_result = discussion_result
        self.replies = replies or []
        self.fallback = fallback or []
        self.aggressive = aggressive or []
        self.call_count = 0
        self.iter_calls = []

    async def __call__(self, request):
        self.call_count += 1
        return self.discussion_result

    async def iter_messages(self, chat_id, reply_to=None, limit=None, min_id=None, reverse=False):
        self.iter_calls.append((chat_id, reply_to, limit, min_id, reverse))
        if reply_to is not None:
            items = self.replies
        elif min_id is not None and reverse:
            items = self.aggressive
        else:
            items = self.fallback
        for item in items:
            yield item


class CollectDiscussionPhotosTests(unittest.IsolatedAsyncioTestCase):
    async def test_skip_without_extra_photos_alias(self):
        channel_id = 111
        message_id = 222
        discussion_chat_id = 999
        root = DummyMessage(10, discussion_chat_id, is_photo=False)
        client = FakeClient(DummyDiscussionResult([root]))
        with patch(
            "controller.data_controller.load_telegram_channels",
            return_value=[{"channel_id": channel_id, "alias": "nope"}],
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual(result, [])
        self.assertEqual(client.call_count, 0)

    async def test_collects_photo_replies_for_alias(self):
        channel_id = 111
        message_id = 222
        discussion_chat_id = 999
        root = DummyMessage(10, discussion_chat_id, is_photo=False)
        replies = [
            DummyMessage(11, discussion_chat_id, is_photo=True),
            DummyMessage(12, discussion_chat_id, is_photo=False),
            DummyMessage(13, discussion_chat_id, is_photo=True),
        ]
        client = FakeClient(DummyDiscussionResult([root]), replies=replies)
        with patch(
            "controller.data_controller.load_telegram_channels",
            return_value=[{"channel_id": channel_id, "alias": "main extra_photos"}],
        ), patch(
            "controller.data_controller._is_photo_message",
            side_effect=lambda msg: getattr(msg, "is_photo", False),
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual([msg.id for msg in result], [11, 13])
        self.assertEqual(client.call_count, 1)

    async def test_collects_non_reply_photos_within_window(self):
        channel_id = 111
        message_id = 222
        discussion_chat_id = 999
        root_date = datetime(2025, 1, 1, 12, 0, 0)
        root = DummyMessage(10, discussion_chat_id, is_photo=False, date=root_date)
        fallback = [
            DummyMessage(
                11,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(minutes=30),
            ),
            DummyMessage(
                12,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(hours=5),
            ),
            DummyMessage(
                9,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(minutes=10),
            ),
        ]
        client = FakeClient(DummyDiscussionResult([root]), replies=[], fallback=fallback)
        with patch(
            "controller.data_controller.load_telegram_channels",
            return_value=[{"channel_id": channel_id, "alias": "extra_photos"}],
        ), patch(
            "controller.data_controller._is_photo_message",
            side_effect=lambda msg: getattr(msg, "is_photo", False),
        ), patch.dict(
            os.environ,
            {"SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES": "120"},
            clear=False,
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual([msg.id for msg in result], [11])

    async def test_aggressive_collects_photos_after_root(self):
        channel_id = 111
        message_id = 222
        discussion_chat_id = 999
        root_date = datetime(2025, 1, 1, 12, 0, 0)
        root = DummyMessage(10, discussion_chat_id, is_photo=False, date=root_date)
        fallback = [
            DummyMessage(
                11,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(hours=5),
            ),
        ]
        aggressive = [
            DummyMessage(12, discussion_chat_id, is_photo=True, date=root_date + timedelta(hours=6)),
            DummyMessage(13, discussion_chat_id, is_photo=True, date=root_date + timedelta(hours=7)),
        ]
        client = FakeClient(
            DummyDiscussionResult([root]),
            replies=[],
            fallback=fallback,
            aggressive=aggressive,
        )
        with patch(
            "controller.data_controller.load_telegram_channels",
            return_value=[{"channel_id": channel_id, "alias": "extra_photos"}],
        ), patch(
            "controller.data_controller._is_photo_message",
            side_effect=lambda msg: getattr(msg, "is_photo", False),
        ), patch.dict(
            os.environ,
            {
                "SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES": "60",
                "SHAFA_EXTRA_PHOTOS_AGGRESSIVE_LIMIT": "5",
            },
            clear=False,
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual([msg.id for msg in result], [12, 13])
