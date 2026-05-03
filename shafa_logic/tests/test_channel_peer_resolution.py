import _test_path  # noqa: F401
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import controller.data_controller as dc


class _DummyMessage:
    def __init__(
        self,
        msg_id: int,
        chat_id: int,
        *,
        is_photo: bool,
        grouped_id: int | None = None,
        reply_to=None,
        date=None,
    ) -> None:
        self.id = msg_id
        self.chat_id = chat_id
        self.is_photo = is_photo
        self.grouped_id = grouped_id
        self.reply_to = reply_to
        self.date = date


class _DummyDiscussionResult:
    def __init__(self, messages, chats=None) -> None:
        self.messages = messages
        self.chats = chats or []


class _DiscussionClient:
    def __init__(self, result, replies) -> None:
        self.result = result
        self.replies = replies
        self.iter_calls = []

    async def __call__(self, request):
        return self.result

    async def iter_messages(
        self,
        peer,
        reply_to=None,
        limit=None,
        min_id=None,
        max_id=None,
        reverse=False,
    ):
        self.iter_calls.append((peer, reply_to, limit, min_id, max_id, reverse))
        for item in self.replies:
            yield item


class _DialogClient:
    def __init__(self, entities) -> None:
        self.entities = entities

    async def iter_dialogs(self):
        for entity in self.entities:
            yield SimpleNamespace(entity=entity)


class ChannelPeerResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_discussion_photos_uses_discussion_chat_entity(self) -> None:
        source_channel_id = -100111
        discussion_channel_id = -100999
        discussion_peer = SimpleNamespace(id=999, peer_id=discussion_channel_id)
        root = _DummyMessage(10, discussion_channel_id, is_photo=False)
        reply = _DummyMessage(11, discussion_channel_id, is_photo=True)
        client = _DiscussionClient(
            _DummyDiscussionResult(
                messages=[
                    _DummyMessage(222, source_channel_id, is_photo=True),
                    root,
                ],
                chats=[
                    SimpleNamespace(id=111, peer_id=source_channel_id),
                    discussion_peer,
                ],
            ),
            replies=[reply],
        )

        with (
            patch("controller.data_controller._get_channel_alias", return_value="main extra_photos"),
            patch(
                "controller.data_controller._is_photo_message",
                side_effect=lambda message: getattr(message, "is_photo", False),
            ),
            patch(
                "controller.data_controller.get_peer_id",
                side_effect=lambda entity: getattr(entity, "peer_id"),
            ),
            patch(
                "controller.data_controller.GetDiscussionMessageRequest",
                side_effect=lambda peer, msg_id: SimpleNamespace(peer=peer, msg_id=msg_id),
            ),
        ):
            result = await dc._collect_discussion_photos(
                client,
                object(),
                source_channel_id,
                222,
            )

        self.assertEqual([message.id for message in result], [11])
        self.assertIs(client.iter_calls[0][0], discussion_peer)

    async def test_resolve_channel_peer_falls_back_to_dialog_entity(self) -> None:
        channel_id = -1001754054922
        dialog_entity = SimpleNamespace(id=1754054922, peer_id=channel_id)
        client = _DialogClient([dialog_entity])

        with (
            patch("controller.data_controller._get_channel_record", return_value={}),
            patch(
                "controller.data_controller.get_peer_id",
                side_effect=lambda entity: getattr(entity, "peer_id"),
            ),
        ):
            result = await dc._resolve_channel_peer(client, channel_id)

        self.assertIs(result, dialog_entity)
