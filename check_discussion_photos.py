import argparse
import asyncio
from datetime import datetime
from typing import Optional

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.utils import get_peer_id

from controller import data_controller as dc


def _format_dt(value: Optional[datetime]) -> str:
    if not value:
        return "-"
    return value.isoformat(sep=" ", timespec="seconds")


def _summarize_ids(messages: list, limit: int) -> str:
    ids = [str(msg.id) for msg in messages[:limit]]
    suffix = "..." if len(messages) > limit else ""
    return ", ".join(ids) + suffix if ids else "-"


async def _collect_with_add(
    client: TelegramClient,
    discussion_chat_id: int,
    iterator,
) -> list:
    messages: list = []
    grouped_seen: set[int] = set()

    async def add_reply(reply) -> None:
        if not dc._is_photo_message(reply):
            return
        if reply.grouped_id:
            if reply.grouped_id in grouped_seen:
                return
            grouped_seen.add(reply.grouped_id)
            grouped = await dc._collect_group_messages(
                client,
                discussion_chat_id,
                reply.id,
                reply.grouped_id,
            )
            if grouped:
                messages.extend(grouped)
                return
        messages.append(reply)

    async for reply in iterator:
        await add_reply(reply)
    return messages


async def _run(args: argparse.Namespace) -> int:
    api_id, api_hash = dc._require_telegram_credentials()
    async with TelegramClient("session", api_id, api_hash) as client:
        channel_message = await client.get_messages(
            args.channel_id, ids=args.message_id
        )
        if not channel_message:
            print("Message not found in channel.")
            return 1

        candidate_ids = [args.message_id]
        grouped_id = getattr(channel_message, "grouped_id", None)
        if grouped_id:
            grouped = await dc._collect_group_messages(
                client,
                args.channel_id,
                args.message_id,
                grouped_id,
            )
            for msg in sorted(grouped, key=lambda item: item.id):
                if msg.id != args.message_id:
                    candidate_ids.append(msg.id)

        result = None
        last_exc: Optional[Exception] = None
        for candidate_id in candidate_ids:
            try:
                result = await client(
                    GetDiscussionMessageRequest(
                        peer=args.channel_id, msg_id=candidate_id
                    )
                )
            except RPCError as exc:
                last_exc = exc
                result = None
                continue
            if result.messages:
                break
            result = None
        if not result or not result.messages:
            preview = ", ".join(str(value) for value in candidate_ids[:5])
            suffix = "..." if len(candidate_ids) > 5 else ""
            if last_exc:
                print(
                    "ERROR: GetDiscussionMessageRequest failed. "
                    f"message_ids=[{preview}{suffix}] error={last_exc}"
                )
            else:
                print(
                    f"No discussion messages returned. message_ids=[{preview}{suffix}]"
                )
            return 1

        discussion_chat_id: Optional[int] = None
        for msg in result.messages:
            chat_id = getattr(msg, "chat_id", None)
            if chat_id and chat_id != args.channel_id:
                discussion_chat_id = chat_id
                break
        if discussion_chat_id is None:
            for chat in result.chats:
                chat_id = get_peer_id(chat)
                if chat_id != args.channel_id:
                    discussion_chat_id = chat_id
                    break
        if not discussion_chat_id:
            print("No discussion chat found for this post.")
            return 1

        root = next(
            (
                msg
                for msg in result.messages
                if getattr(msg, "chat_id", None) == discussion_chat_id
            ),
            None,
        )
        if not root:
            print("No root discussion message found.")
            return 1

        root_id = getattr(root, "id", None)
        if not root_id:
            print("Root discussion message has no id.")
            return 1

        alias = dc._get_channel_alias(args.channel_id)
        print(f"Channel alias: {alias or '-'}")
        print(f"Discussion chat id: {discussion_chat_id}")
        print(
            f"Root id: {root_id} | root date: {_format_dt(getattr(root, 'date', None))}"
        )

        direct: list = []
        try:
            direct = await _collect_with_add(
                client,
                discussion_chat_id,
                client.iter_messages(discussion_chat_id, reply_to=root_id),
            )
        except RPCError as exc:
            print(f"Direct replies failed: {exc}")
        direct_ids = _summarize_ids(direct, args.max_list)
        print(f"Direct replies: {len(direct)} | ids: {direct_ids}")

        fallback: list = []
        window_seconds = max(args.window_minutes, 0) * 60
        root_date = getattr(root, "date", None)
        grouped_seen: set[int] = set()

        async def add_fallback(reply) -> None:
            if not dc._is_photo_message(reply):
                return
            if reply.grouped_id:
                if reply.grouped_id in grouped_seen:
                    return
                grouped_seen.add(reply.grouped_id)
                grouped = await dc._collect_group_messages(
                    client,
                    discussion_chat_id,
                    reply.id,
                    reply.grouped_id,
                )
                if grouped:
                    fallback.extend(grouped)
                    return
            fallback.append(reply)

        try:
            async for reply in client.iter_messages(
                discussion_chat_id, limit=args.fallback_limit
            ):
                header = getattr(reply, "reply_to", None)
                if header:
                    top_id = getattr(header, "reply_to_top_id", None)
                    msg_id = getattr(header, "reply_to_msg_id", None)
                    if top_id != root_id and msg_id != root_id:
                        continue
                    await add_fallback(reply)
                    continue
                if window_seconds <= 0:
                    continue
                reply_id = getattr(reply, "id", None)
                if reply_id is not None and reply_id <= root_id:
                    continue
                if root_date is not None:
                    reply_date = getattr(reply, "date", None)
                    if reply_date is not None:
                        delta = (reply_date - root_date).total_seconds()
                        if delta < 0 or delta > window_seconds:
                            continue
                await add_fallback(reply)
        except RPCError as exc:
            print(f"Fallback scan failed: {exc}")

        fallback_ids = _summarize_ids(fallback, args.max_list)
        print(f"Fallback scan: {len(fallback)} | ids: {fallback_ids}")

        if args.aggressive is None:
            aggressive_enabled = True
        else:
            aggressive_enabled = args.aggressive

        aggressive: list = []
        if aggressive_enabled:
            try:
                aggressive = await _collect_with_add(
                    client,
                    discussion_chat_id,
                    client.iter_messages(
                        discussion_chat_id,
                        min_id=root_id,
                        limit=args.aggressive_limit,
                        reverse=True,
                    ),
                )
            except RPCError as exc:
                print(f"Aggressive scan failed: {exc}")
        aggressive_ids = _summarize_ids(aggressive, args.max_list)
        print(f"Aggressive scan: {len(aggressive)} | ids: {aggressive_ids}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check discussion photos for a Telegram post."
    )
    parser.add_argument("--channel-id", type=int, required=True)
    parser.add_argument("--message-id", type=int, required=True)
    parser.add_argument("--fallback-limit", type=int, default=200)
    parser.add_argument("--window-minutes", type=int, default=180)
    parser.add_argument("--aggressive", action="store_true", default=None)
    parser.add_argument("--no-aggressive", dest="aggressive", action="store_false")
    parser.add_argument("--aggressive-limit", type=int, default=50)
    parser.add_argument("--max-list", type=int, default=10)
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
