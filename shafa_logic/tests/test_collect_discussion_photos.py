import _test_path
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import controller.data_controller as dc
from telethon.types import DocumentAttributeFilename


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
        self.discussion_results = None
        self.replies = replies or []
        self.fallback = fallback or []
        self.aggressive = aggressive or []
        self.call_count = 0
        self.iter_calls = []

    async def __call__(self, request):
        self.call_count += 1
        if self.discussion_results is not None:
            index = min(self.call_count - 1, len(self.discussion_results) - 1)
            return self.discussion_results[index]
        return self.discussion_result

    async def iter_messages(
        self, chat_id, reply_to=None, limit=None, min_id=None, reverse=False
    ):
        self.iter_calls.append((chat_id, reply_to, limit, min_id, reverse))
        if reply_to is not None:
            items = self.replies
        elif min_id is not None and reverse:
            items = self.aggressive
        else:
            items = self.fallback
        for item in items:
            yield item


class FakeTelegramClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
        with (
            patch(
                "controller.data_controller.load_telegram_channels",
                return_value=[{"channel_id": channel_id, "alias": "main extra_photos"}],
            ),
            patch(
                "controller.data_controller._is_photo_message",
                side_effect=lambda msg: getattr(msg, "is_photo", False),
            ),
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual([msg.id for msg in result], [11, 13])
        self.assertEqual(client.call_count, 1)

    async def test_tries_next_candidate_when_first_discussion_result_has_no_root(self):
        channel_id = 111
        message_id = 222
        discussion_chat_id = 999
        root = DummyMessage(10, discussion_chat_id, is_photo=False)
        replies = [DummyMessage(11, discussion_chat_id, is_photo=True)]
        client = FakeClient(DummyDiscussionResult([]), replies=replies)
        client.discussion_results = [
            DummyDiscussionResult([DummyMessage(message_id, channel_id, is_photo=True)]),
            DummyDiscussionResult(
                [DummyMessage(message_id, channel_id, is_photo=True), root]
            ),
        ]
        with (
            patch(
                "controller.data_controller.load_telegram_channels",
                return_value=[{"channel_id": channel_id, "alias": "main extra_photos"}],
            ),
            patch(
                "controller.data_controller._is_photo_message",
                side_effect=lambda msg: getattr(msg, "is_photo", False),
            ),
        ):
            result = await dc._collect_discussion_photos(
                client,
                channel_id,
                message_id,
                [message_id, message_id + 1],
            )
        self.assertEqual([msg.id for msg in result], [11])
        self.assertEqual(client.call_count, 2)

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
        client = FakeClient(
            DummyDiscussionResult([root]), replies=[], fallback=fallback
        )
        with (
            patch(
                "controller.data_controller.load_telegram_channels",
                return_value=[{"channel_id": channel_id, "alias": "extra_photos"}],
            ),
            patch(
                "controller.data_controller._is_photo_message",
                side_effect=lambda msg: getattr(msg, "is_photo", False),
            ),
            patch.dict(
                os.environ,
                {"SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES": "120"},
                clear=False,
            ),
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
            DummyMessage(
                12,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(hours=6),
            ),
            DummyMessage(
                13,
                discussion_chat_id,
                is_photo=True,
                date=root_date + timedelta(hours=7),
            ),
        ]
        client = FakeClient(
            DummyDiscussionResult([root]),
            replies=[],
            fallback=fallback,
            aggressive=aggressive,
        )
        with (
            patch(
                "controller.data_controller.load_telegram_channels",
                return_value=[{"channel_id": channel_id, "alias": "extra_photos"}],
            ),
            patch(
                "controller.data_controller._is_photo_message",
                side_effect=lambda msg: getattr(msg, "is_photo", False),
            ),
            patch.dict(
                os.environ,
                {
                    "SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES": "60",
                    "SHAFA_EXTRA_PHOTOS_AGGRESSIVE_LIMIT": "5",
                },
                clear=False,
            ),
        ):
            result = await dc._collect_discussion_photos(client, channel_id, message_id)
        self.assertEqual([msg.id for msg in result], [12, 13])


class ImageDocumentTests(unittest.TestCase):
    def test_rejects_heic_mime_type(self):
        document = SimpleNamespace(mime_type="image/heic", attributes=[])

        self.assertFalse(dc._is_image_document(document))

    def test_rejects_heic_filename(self):
        document = SimpleNamespace(
            mime_type="image/jpeg",
            attributes=[DocumentAttributeFilename(file_name="comment-photo.HEIC")],
        )

        self.assertFalse(dc._is_image_document(document))

    def test_accepts_regular_image_document(self):
        document = SimpleNamespace(
            mime_type="image/jpeg",
            attributes=[DocumentAttributeFilename(file_name="comment-photo.jpg")],
        )

        self.assertTrue(dc._is_image_document(document))


class ProductPhotoMessageIdsTests(unittest.TestCase):
    def test_collects_main_and_comment_message_ids(self):
        product_data = {
            "message_id": 10,
            "parsed_data": {
                "comment_messages": [
                    {"message_id": 11},
                    {"id": "12"},
                ],
                "comment_message_ids": [13, "14"],
            },
        }

        self.assertEqual(
            dc.get_product_photo_message_ids(product_data),
            [10, 11, 12, 13, 14],
        )


class DownloadProductPhotosAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_comment_message_ids(self):
        with patch(
            "controller.data_controller._download_message_photos",
            return_value=3,
        ) as download_photos:
            result = await dc.download_product_photos_async(
                10,
                "/tmp/photos",
                channel_id=111,
                message_ids=[10, 11, 12],
            )

        self.assertEqual(result, 3)
        download_photos.assert_awaited_once_with(
            111,
            10,
            "/tmp/photos",
            dc.MAX_DOWNLOAD_PHOTOS,
            message_ids=[10, 11, 12],
        )


class DownloadMessagePhotosTotalLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_cumulative_size_limit_per_product(self):
        messages = {
            10: DummyMessage(10, 111, is_photo=True),
            11: DummyMessage(11, 111, is_photo=True),
            12: DummyMessage(12, 111, is_photo=True),
        }

        class DownloadClient:
            async def get_messages(self, channel_id, ids):
                return messages.get(ids)

            async def download_media(self, message, file):
                path = os.path.join(file, f"{message.id}.jpg")
                size_map = {
                    10: dc.MAX_UPLOAD_BYTES // 2,
                    11: dc.MAX_UPLOAD_BYTES // 2,
                    12: dc.MAX_UPLOAD_BYTES // 4,
                }
                with open(path, "wb") as handle:
                    handle.write(b"0" * size_map[message.id])
                return path

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch(
                    "controller.data_controller.TelegramClient",
                    return_value=FakeTelegramClientContext(DownloadClient()),
                ),
                patch("controller.data_controller._require_telegram_credentials", return_value=(1, "hash")),
                patch("controller.data_controller._sync_channel_titles"),
                patch("controller.data_controller._collect_discussion_photos", return_value=[]),
                patch("controller.data_controller._is_photo_message", return_value=True),
                patch("controller.data_controller.verbose_photo_logs_enabled", return_value=False),
            ):
                downloaded = await dc._download_message_photos(
                    111,
                    10,
                    Path(tmpdir),
                    max_photos=10,
                    message_ids=[10, 11, 12],
                )

            self.assertEqual(downloaded, 2)
            self.assertTrue((Path(tmpdir) / "10.jpg").exists())
            self.assertTrue((Path(tmpdir) / "11.jpg").exists())
            self.assertFalse((Path(tmpdir) / "12.jpg").exists())
