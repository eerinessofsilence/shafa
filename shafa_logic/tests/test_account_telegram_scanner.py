import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import controller.data_controller as dc
import data.db as db


class _FakeTelegramClient:
    def __init__(self, messages_by_peer: dict[object, list[object]]) -> None:
        self.messages_by_peer = messages_by_peer
        self.calls: list[dict] = []

    async def iter_messages(self, peer, **kwargs):
        self.calls.append({"peer": peer, **kwargs})
        messages = list(self.messages_by_peer.get(peer, []))
        min_id = kwargs.get("min_id")
        if isinstance(min_id, int):
            messages = [msg for msg in messages if getattr(msg, "id", 0) > min_id]
        max_id = kwargs.get("max_id")
        if isinstance(max_id, int):
            messages = [msg for msg in messages if getattr(msg, "id", 0) < max_id]
        reverse = bool(kwargs.get("reverse"))
        messages = sorted(messages, key=lambda item: item.id, reverse=not reverse)
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


def _message(message_id: int, text: str, media: object | None = None):
    return SimpleNamespace(
        id=message_id,
        message=text,
        media=object() if media is None else media,
    )


class AccountTelegramScannerTests(unittest.TestCase):
    def test_telegram_products_are_unique_per_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                self.assertTrue(
                    db.save_telegram_product(
                        11,
                        501,
                        "valid",
                        parsed,
                        account_id="acc-1",
                    )
                )
                self.assertTrue(
                    db.save_telegram_product(
                        11,
                        501,
                        "valid",
                        parsed,
                        account_id="acc-2",
                    )
                )
                self.assertFalse(
                    db.save_telegram_product(
                        11,
                        501,
                        "valid",
                        parsed,
                        account_id="acc-1",
                    )
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM telegram_products"
                    ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_scan_advances_cursor_for_non_products_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {
                    "peer-11": [
                        _message(101, "valid-101"),
                        _message(102, "not-a-product"),
                        _message(103, "valid-duplicate"),
                    ]
                }
            )
            parsed = {
                "valid-101": {"name": "One", "price": "1600", "size": "41"},
                "not-a-product": {"name": "Two", "price": "", "size": "41"},
                "valid-duplicate": {"name": "Three", "price": "1700", "size": "42"},
            }
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: parsed[text],
                ),
            ):
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-1",
                )
                db.save_telegram_product(
                    11,
                    103,
                    "valid-duplicate",
                    parsed["valid-duplicate"],
                    account_id="acc-1",
                )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, channel_id, message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(cursor["last_checked_message_id"], 103)
        self.assertEqual([(row[0], row[1], row[2]) for row in rows], [
            ("acc-1", 11, 101),
            ("acc-1", 11, 103),
        ])

    def test_scan_stops_on_message_error_without_skipping_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {
                    "peer-11": [
                        _message(101, "valid-101"),
                        _message(102, "boom"),
                        _message(103, "valid-103"),
                    ]
                }
            )
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: (
                        {"name": "One", "price": "1600", "size": "41"}
                        if text == "valid-101"
                        else (_ for _ in ()).throw(RuntimeError("parser failed"))
                    ),
                ),
            ):
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-1",
                )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(cursor["last_checked_message_id"], 101)
        self.assertIn("parser failed", cursor["last_scan_error"])
        self.assertEqual([row[0] for row in rows], [101])

    def test_scan_respects_batch_limit_when_many_new_messages_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {
                    "peer-11": [
                        _message(message_id, f"valid-{message_id}")
                        for message_id in range(101, 301)
                    ]
                }
            )
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: {"name": text, "price": "1600", "size": "41"},
                ),
            ):
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-1",
                )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    count = conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM telegram_products
                        WHERE account_id = ?
                        """,
                        ("acc-1",),
                    ).fetchone()[0]

        self.assertEqual(result["inserted"], 150)
        self.assertEqual(cursor["last_checked_message_id"], 250)
        self.assertEqual(count, 150)
        self.assertEqual(client.calls[0]["limit"], 150)
        self.assertTrue(client.calls[0]["reverse"])

    def test_scanner_without_cursor_uses_existing_queue_as_live_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {"peer-11": [_message(89, "old-89"), _message(90, "old-90"), _message(91, "old-91"), _message(92, "new-92")]}
            )
            parsed = {
                "new-92": {"name": "New", "price": "1600", "size": "41"},
            }
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: parsed[text],
                ),
            ):
                for message_id in (89, 90, 91):
                    db.save_telegram_product(
                        11,
                        message_id,
                        f"queued-{message_id}",
                        {"name": f"Queued {message_id}", "price": "1500", "size": "41"},
                        account_id="acc-1",
                    )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(cursor["last_checked_message_id"], 92)
        self.assertEqual([row[0] for row in rows], [89, 90, 91, 92])
        self.assertEqual(client.calls[0]["min_id"], 91)
        self.assertEqual(client.calls[0]["limit"], 150)
        self.assertTrue(client.calls[0]["reverse"])

    def test_live_cursor_stays_on_tail_while_backfill_reads_older_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {"peer-11": [_message(89, "old-89"), _message(90, "old-90"), _message(91, "old-91")]}
            )
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    return_value={"name": "History", "price": "1600", "size": "41"},
                ),
            ):
                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(cursor["last_checked_message_id"], 91)
        self.assertEqual(cursor["backfill_before_message_id"], 89)
        self.assertEqual([row[0] for row in rows], [89, 90])
        self.assertEqual(client.calls[0]["limit"], 1)
        self.assertNotIn("min_id", client.calls[0])
        self.assertEqual(client.calls[1]["min_id"], 91)
        self.assertEqual(client.calls[2]["max_id"], 91)

    def test_scanner_sees_new_message_after_tail_baseline_is_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            messages = [_message(91, "tail-91")]
            client = _FakeTelegramClient({"peer-11": messages})
            parsed = {"new-92": {"name": "New", "price": "1600", "size": "41"}}
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: parsed[text],
                ),
            ):
                first_result = dc.scan_account_telegram_channels(batch_size=150)
                first_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                client.messages_by_peer["peer-11"].append(_message(92, "new-92"))

                second_result = dc.scan_account_telegram_channels(batch_size=150)
                second_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(first_result["inserted"], 0)
        self.assertEqual(first_cursor["last_checked_message_id"], 91)
        self.assertEqual(first_cursor["backfill_before_message_id"], 1)
        self.assertEqual(second_result["inserted"], 1)
        self.assertEqual(second_cursor["last_checked_message_id"], 92)
        self.assertEqual(second_cursor["backfill_before_message_id"], 1)
        self.assertEqual([row[0] for row in rows], [92])

    def test_backfill_cursor_moves_down_without_affecting_live_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient(
                {
                    "peer-11": [
                        _message(86, "old-86"),
                        _message(87, "old-87"),
                        _message(88, "old-88"),
                        _message(91, "tail-91"),
                    ]
                }
            )
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    return_value={"name": "History", "price": "1600", "size": "41"},
                ),
            ):
                first_result = dc.scan_account_telegram_channels(batch_size=2)
                first_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")
                second_result = dc.scan_account_telegram_channels(batch_size=2)
                second_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(first_result["inserted"], 2)
        self.assertEqual(first_cursor["last_checked_message_id"], 91)
        self.assertEqual(first_cursor["backfill_before_message_id"], 87)
        self.assertEqual(second_result["inserted"], 1)
        self.assertEqual(second_cursor["last_checked_message_id"], 91)
        self.assertEqual(second_cursor["backfill_before_message_id"], 86)
        self.assertEqual([row[0] for row in rows], [86, 87, 88])

    def test_scanner_skips_legacy_product_and_still_advances_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient({"peer-11": [_message(101, "valid-101")]})
            parsed = {"valid-101": {"name": "One", "price": "1600", "size": "41"}}
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: parsed[text],
                ),
            ):
                db.save_telegram_product(
                    11,
                    101,
                    "valid-101",
                    parsed["valid-101"],
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.mark_telegram_product_created(
                    11,
                    101,
                    created_product_id="legacy-product-1",
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-1",
                )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id
                        FROM telegram_products
                        ORDER BY account_id, message_id
                        """
                    ).fetchall()

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(cursor["last_checked_message_id"], 101)
        self.assertEqual(
            [(row[0], row[1]) for row in rows],
            [(db.LEGACY_TELEGRAM_ACCOUNT_ID, 101)],
        )

    def test_scanner_keeps_accounts_independent_for_same_message_and_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            client = _FakeTelegramClient({"peer-11": [_message(101, "valid-101")]})
            parsed = {"valid-101": {"name": "One", "price": "1600", "size": "41"}}
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-2"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: parsed[text],
                ),
            ):
                db.save_telegram_product(
                    11,
                    101,
                    "valid-101",
                    parsed["valid-101"],
                    account_id="acc-1",
                )
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=75,
                    account_id="acc-1",
                )
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-2",
                )

                result = dc.scan_account_telegram_channels(batch_size=150)
                cursor_acc_1 = db.get_telegram_scan_cursor(11, account_id="acc-1")
                cursor_acc_2 = db.get_telegram_scan_cursor(11, account_id="acc-2")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id
                        FROM telegram_products
                        ORDER BY account_id, message_id
                        """
                    ).fetchall()

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(cursor_acc_1["last_checked_message_id"], 75)
        self.assertEqual(cursor_acc_2["last_checked_message_id"], 101)
        self.assertEqual(
            [(row[0], row[1]) for row in rows],
            [("acc-1", 101), ("acc-2", 101)],
        )

    def test_scanner_processes_only_150_messages_per_pass_and_advances_cursor_incrementally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            messages = [
                _message(message_id, f"valid-{message_id}")
                for message_id in range(101, 301)
            ]
            client = _FakeTelegramClient({"peer-11": messages})
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
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
                    "controller.data_controller._is_photo_message",
                    return_value=True,
                ),
                patch(
                    "controller.data_controller.parse_message",
                    side_effect=lambda text: {"name": text, "price": "1600", "size": "41"},
                ),
            ):
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=100,
                    account_id="acc-1",
                )
                db.finish_telegram_scan(
                    11,
                    last_checked_message_id=888,
                    account_id="acc-2",
                )

                first_result = dc.scan_account_telegram_channels(batch_size=150)
                first_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")
                second_result = dc.scan_account_telegram_channels(batch_size=150)
                second_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")
                other_cursor = db.get_telegram_scan_cursor(11, account_id="acc-2")

                with sqlite3.connect(telegram_db_path) as conn:
                    count = conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM telegram_products
                        WHERE account_id = ?
                        """,
                        ("acc-1",),
                    ).fetchone()[0]

        self.assertEqual(first_result["inserted"], 150)
        self.assertEqual(first_cursor["last_checked_message_id"], 250)
        self.assertEqual(second_result["inserted"], 50)
        self.assertEqual(second_cursor["last_checked_message_id"], 300)
        self.assertEqual(other_cursor["last_checked_message_id"], 888)
        self.assertEqual(count, 200)


if __name__ == "__main__":
    unittest.main()
