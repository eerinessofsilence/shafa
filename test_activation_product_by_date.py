import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent
SHAFA_LOGIC_DIR = ROOT_DIR / "shafa_logic"
for path in (ROOT_DIR, SHAFA_LOGIC_DIR):
    text_path = str(path)
    if text_path not in sys.path:
        sys.path.insert(0, text_path)

from activation_product_by_date import (
    ActivationCandidate,
    AccountSession,
    DEFAULT_ACTIVATION_SLEEP_MAX_SECONDS,
    DEFAULT_ACTIVATION_SLEEP_MIN_SECONDS,
    DEFAULT_MAX_ACCOUNT_WORKERS,
    DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
    _default_shared_telegram_db_path,
    activate_candidates,
    backfill_missing_telegram_message_dates_for_product_ids,
    build_arg_parser,
    clear_telegram_message_dates_for_product_ids,
    collect_current_account_candidates,
    list_inactive_uploaded_products_from_account_db,
    mark_uploaded_product_active,
    parse_telegram_datetime,
    select_product_for_activation_by_telegram_identity,
    select_products_for_activation,
)


class ActivationProductByDateTests(unittest.TestCase):
    def _create_account_db(self, path: Path) -> None:
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE uploaded_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT,
                    name TEXT,
                    raw_payload TEXT,
                    status_title TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO uploaded_products (
                    product_id, name, raw_payload, status_title, is_active
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("101", "Fresh inactive", '{"message_id": 501}', "Деактивовано", 0),
                    ("102", "Old inactive", '{"message_id": 502}', "Деактивовано", 0),
                    ("103", "No telegram", '{"message_id": 503}', "Деактивовано", 0),
                    ("104", "Exactly 183", '{"message_id": 504}', "Деактивовано", 0),
                    ("105", "Too old", '{"message_id": 505}', "Деактивовано", 0),
                ],
            )

    def _create_telegram_db(self, path: Path, today: date) -> None:
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE telegram_products (
                    account_id TEXT,
                    channel_id INTEGER,
                    message_id INTEGER,
                    created_product_id TEXT,
                    status TEXT,
                    created INTEGER,
                    telegram_message_date TEXT,
                    parsed_data TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO telegram_products (
                    account_id,
                    channel_id,
                    message_id,
                    created_product_id,
                    status,
                    created,
                    telegram_message_date,
                    parsed_data,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'created', 1, ?, '{}', datetime('now'))
                """,
                [
                    (
                        "acc-1",
                        11,
                        501,
                        "101",
                        (today - timedelta(days=100)).isoformat(),
                    ),
                    (
                        "acc-1",
                        11,
                        504,
                        "104",
                        (today - timedelta(days=183)).isoformat(),
                    ),
                    (
                        "acc-1",
                        11,
                        505,
                        "105",
                        (today - timedelta(days=184)).isoformat(),
                    ),
                    (
                        "acc-1",
                        11,
                        502,
                        "102",
                        (today - timedelta(days=200)).isoformat(),
                    ),
                ],
            )

    def test_parse_telegram_datetime_accepts_date_and_datetime(self) -> None:
        self.assertEqual(
            parse_telegram_datetime("2026-06-02").date(),
            date(2026, 6, 2),
        )
        self.assertEqual(
            parse_telegram_datetime("2026-06-02T10:30:00+00:00").date(),
            date(2026, 6, 2),
        )
        self.assertIsNone(parse_telegram_datetime("bad"))

    def test_select_products_for_activation_requires_fresh_telegram_match(self) -> None:
        today = date(2026, 6, 2)
        products = [
            {"id": 101, "name": "Fresh", "_products_type": "DEACTIVATED"},
            {"id": 102, "name": "Old", "_products_type": "DEACTIVATED"},
            {"id": 103, "name": "Missing telegram", "_products_type": "DEACTIVATED"},
            {"id": 104, "name": "Exactly 183", "_products_type": "DEACTIVATED"},
            {"id": 105, "name": "Too old", "_products_type": "DEACTIVATED"},
        ]
        with tempfile.TemporaryDirectory() as raw_dir:
            base = Path(raw_dir)
            account_db = base / "shafa.sqlite3"
            telegram_db = base / "telegram_feed.sqlite3"
            self._create_account_db(account_db)
            self._create_telegram_db(telegram_db, today)

            with patch.dict(
                os.environ,
                {
                    "SHAFA_ACCOUNT_ID": "acc-1",
                    "SHAFA_DB_PATH": str(account_db),
                    "SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db),
                },
                clear=True,
            ):
                candidates = select_products_for_activation(
                    products,
                    today=today,
                    max_age_days=183,
                )

        self.assertEqual(
            [candidate.product_id for candidate in candidates],
            ["101", "104"],
        )
        self.assertEqual(candidates[0].telegram_age_days, 100)
        self.assertEqual(candidates[0].channel_id, 11)
        self.assertEqual(candidates[0].message_id, 501)
        self.assertEqual(candidates[0].age_source, "telegram_message_date")
        self.assertEqual(candidates[1].telegram_age_days, 183)

    def test_select_products_uses_account_db_created_at_when_telegram_mapping_missing(self) -> None:
        today = date(2026, 6, 2)
        with tempfile.TemporaryDirectory() as raw_dir:
            account_db = Path(raw_dir) / "shafa.sqlite3"
            with sqlite3.connect(account_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE uploaded_products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_id TEXT,
                        name TEXT,
                        price INTEGER,
                        raw_payload TEXT,
                        created_at TEXT,
                        shafa_created_at TEXT,
                        is_active INTEGER,
                        status_title TEXT
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO uploaded_products (
                        product_id,
                        name,
                        price,
                        raw_payload,
                        created_at,
                        shafa_created_at,
                        is_active,
                        status_title
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "201",
                            "Fresh local inactive",
                            860,
                            "{}",
                            (today - timedelta(days=25)).isoformat(),
                            "",
                            0,
                            "Деактивовано",
                        ),
                        (
                            "202",
                            "Old local inactive",
                            500,
                            "{}",
                            (today - timedelta(days=220)).isoformat(),
                            "",
                            0,
                            "Деактивовано",
                        ),
                        (
                            "203",
                            "Active local",
                            500,
                            "{}",
                            (today - timedelta(days=25)).isoformat(),
                            "",
                            1,
                            "Активно",
                        ),
                    ],
                )

            with patch.dict(os.environ, {"SHAFA_DB_PATH": str(account_db)}, clear=True):
                products = list_inactive_uploaded_products_from_account_db()
                candidates = select_products_for_activation(
                    products,
                    today=today,
                    max_age_days=183,
                )

        self.assertEqual([product["id"] for product in products], ["202", "201"])
        self.assertEqual([candidate.product_id for candidate in candidates], ["201"])
        self.assertEqual(candidates[0].telegram_age_days, 25)
        self.assertEqual(candidates[0].age_source, "account_db_created_at")
        self.assertIsNone(candidates[0].channel_id)
        self.assertIsNone(candidates[0].message_id)

    def test_collection_backfills_missing_telegram_date_by_created_product_id(self) -> None:
        today = date(2026, 6, 2)
        with tempfile.TemporaryDirectory() as raw_dir:
            base = Path(raw_dir)
            account_db = base / "shafa.sqlite3"
            telegram_db = base / "telegram_feed.sqlite3"
            self._create_account_db(account_db)
            with sqlite3.connect(telegram_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_products (
                        account_id TEXT,
                        channel_id INTEGER,
                        message_id INTEGER,
                        created_product_id TEXT,
                        status TEXT,
                        created INTEGER,
                        telegram_message_date TEXT,
                        parsed_data TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        account_id,
                        channel_id,
                        message_id,
                        created_product_id,
                        status,
                        created,
                        telegram_message_date,
                        parsed_data,
                        updated_at
                    )
                    VALUES ('legacy-acc', -1001849992155, 156539, '101', 'created', 1, '', '{}', datetime('now'))
                    """
                )

            def fake_backfill(rows: list[dict[str, object]]) -> dict[str, int]:
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["account_id"], "legacy-acc")
                self.assertEqual(str(rows[0]["created_product_id"]), "101")
                with sqlite3.connect(telegram_db) as conn:
                    conn.execute(
                        """
                        UPDATE telegram_products
                        SET telegram_message_date = ?
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        (
                            (today - timedelta(days=25)).isoformat(),
                            rows[0]["account_id"],
                            rows[0]["channel_id"],
                            rows[0]["message_id"],
                        ),
                    )
                return {"updated": 1, "failed": 0}

            stats: dict[str, int] = {}
            with patch.dict(
                os.environ,
                {
                    "SHAFA_ACCOUNT_ID": "acc-1",
                    "SHAFA_DB_PATH": str(account_db),
                    "SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db),
                },
                clear=True,
            ):
                with patch("activation_product_by_date.fetch_inactive_products", return_value=[]):
                    with patch(
                        "activation_product_by_date._backfill_telegram_message_dates_from_telegram_async",
                        side_effect=fake_backfill,
                    ):
                        with redirect_stdout(StringIO()):
                            candidates = collect_current_account_candidates(
                                page_size=50,
                                product_types=["INACTIVE"],
                                max_age_days=183,
                                telegram_date_backfill_limit=10,
                                telegram_date_backfill_batch_size=50,
                                telegram_date_backfill_sleep_min_seconds=0,
                                telegram_date_backfill_sleep_max_seconds=0,
                                backfill_stats=stats,
                            )

            with sqlite3.connect(telegram_db) as conn:
                stored_date = conn.execute(
                    "SELECT telegram_message_date FROM telegram_products WHERE created_product_id = '101'"
                ).fetchone()[0]

        self.assertEqual([candidate.product_id for candidate in candidates], ["101"])
        self.assertEqual(candidates[0].age_source, "telegram_message_date")
        self.assertEqual(candidates[0].channel_id, -1001849992155)
        self.assertEqual(candidates[0].message_id, 156539)
        self.assertEqual(stats["date_backfill_checked"], 1)
        self.assertEqual(stats["date_loaded_from_telegram"], 1)
        self.assertEqual(stats["date_load_failed"], 0)
        self.assertEqual(stored_date, (today - timedelta(days=25)).isoformat())

    def test_collection_skips_when_missing_telegram_date_backfill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            base = Path(raw_dir)
            account_db = base / "shafa.sqlite3"
            telegram_db = base / "telegram_feed.sqlite3"
            self._create_account_db(account_db)
            with sqlite3.connect(telegram_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_products (
                        account_id TEXT,
                        channel_id INTEGER,
                        message_id INTEGER,
                        created_product_id TEXT,
                        status TEXT,
                        created INTEGER,
                        telegram_message_date TEXT,
                        parsed_data TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        account_id,
                        channel_id,
                        message_id,
                        created_product_id,
                        status,
                        created,
                        telegram_message_date,
                        parsed_data,
                        updated_at
                    )
                    VALUES ('legacy-acc', -1001849992155, 156539, '101', 'created', 1, NULL, '{}', datetime('now'))
                    """
                )

            stats: dict[str, int] = {}
            with patch.dict(
                os.environ,
                {
                    "SHAFA_ACCOUNT_ID": "acc-1",
                    "SHAFA_DB_PATH": str(account_db),
                    "SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db),
                },
                clear=True,
            ):
                with patch("activation_product_by_date.fetch_inactive_products", return_value=[]):
                    with patch(
                        "activation_product_by_date._backfill_telegram_message_dates_from_telegram_async",
                        return_value={"updated": 0, "failed": 1},
                    ):
                        with redirect_stdout(StringIO()):
                            candidates = collect_current_account_candidates(
                                page_size=50,
                                product_types=["INACTIVE"],
                                max_age_days=183,
                                telegram_date_backfill_limit=10,
                                telegram_date_backfill_batch_size=50,
                                telegram_date_backfill_sleep_min_seconds=0,
                                telegram_date_backfill_sleep_max_seconds=0,
                                backfill_stats=stats,
                            )

        self.assertEqual(candidates, [])
        self.assertEqual(stats["date_backfill_checked"], 1)
        self.assertEqual(stats["date_loaded_from_telegram"], 0)
        self.assertEqual(stats["date_load_failed"], 1)

    def test_select_product_by_telegram_identity_uses_telegram_date_boundary(self) -> None:
        today = date(2026, 6, 2)
        with tempfile.TemporaryDirectory() as raw_dir:
            base = Path(raw_dir)
            account_db = base / "shafa.sqlite3"
            telegram_db = base / "telegram_feed.sqlite3"
            self._create_account_db(account_db)
            self._create_telegram_db(telegram_db, today)

            with patch.dict(
                os.environ,
                {
                    "SHAFA_ACCOUNT_ID": "acc-1",
                    "SHAFA_DB_PATH": str(account_db),
                    "SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db),
                },
                clear=True,
            ):
                exact = select_product_for_activation_by_telegram_identity(
                    11,
                    504,
                    today=today,
                    max_age_days=183,
                )
                too_old = select_product_for_activation_by_telegram_identity(
                    11,
                    505,
                    today=today,
                    max_age_days=183,
                )

        self.assertIsNotNone(exact)
        self.assertEqual(exact.product_id, "104")
        self.assertEqual(exact.telegram_age_days, 183)
        self.assertIsNone(too_old)

    def test_activate_candidates_tracks_success_and_marks_active(self) -> None:
        candidates = [
            ActivationCandidate("101", "Fresh", date(2026, 3, 1), 94),
            ActivationCandidate("102", "Second", date(2026, 3, 2), 93),
        ]
        activated = []
        marked = []

        def _fake_activate(product_id: str) -> None:
            if product_id == "102":
                raise RuntimeError("failed")
            activated.append(product_id)

        def _fake_mark(product_id: str, *, status_title: str) -> bool:
            marked.append((product_id, status_title))
            return True

        with redirect_stdout(StringIO()):
            result = activate_candidates(
                candidates,
                activate_func=_fake_activate,
                mark_active_func=_fake_mark,
                sleep_min_seconds=0,
                sleep_max_seconds=0,
            )

        self.assertEqual(result, {"activated": 1, "failed": 1, "mark_failed": 0})
        self.assertEqual(activated, ["101"])
        self.assertEqual(marked, [("101", "Активно")])

    def test_activate_candidates_can_emit_live_logs_through_callback(self) -> None:
        candidates = [
            ActivationCandidate("101", "Fresh", date(2026, 3, 1), 94),
        ]
        logs = []

        with redirect_stdout(StringIO()) as stdout:
            result = activate_candidates(
                candidates,
                activate_func=lambda product_id: None,
                mark_active_func=lambda product_id, *, status_title: True,
                sleep_min_seconds=0,
                sleep_max_seconds=0,
                account_name="Account 1",
                log_func=logs.append,
            )

        self.assertEqual(result, {"activated": 1, "failed": 0, "mark_failed": 0})
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(any("First activation attempt" in line for line in logs))
        self.assertTrue(any("Activating 101" in line for line in logs))
        self.assertTrue(any("OK 101" in line for line in logs))

    def test_mark_uploaded_product_active_updates_account_db(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            account_db = Path(raw_dir) / "shafa.sqlite3"
            self._create_account_db(account_db)
            with patch.dict(os.environ, {"SHAFA_DB_PATH": str(account_db)}, clear=True):
                self.assertTrue(mark_uploaded_product_active("101"))

            with sqlite3.connect(account_db) as conn:
                row = conn.execute(
                    """
                    SELECT is_active, status_title
                    FROM uploaded_products
                    WHERE product_id = '101'
                    """
                ).fetchone()

        self.assertEqual(row, (1, "Активно"))

    def test_clear_telegram_message_dates_for_product_ids_limits_updates(self) -> None:
        today = date(2026, 6, 2)
        with tempfile.TemporaryDirectory() as raw_dir:
            telegram_db = Path(raw_dir) / "telegram_feed.sqlite3"
            self._create_telegram_db(telegram_db, today)

            with patch.dict(
                os.environ,
                {
                    "SHAFA_ACCOUNT_ID": "acc-1",
                    "SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db),
                },
                clear=True,
            ):
                cleared = clear_telegram_message_dates_for_product_ids(
                    ["101", "104", "105"],
                    limit=2,
                )

            with sqlite3.connect(telegram_db) as conn:
                missing_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM telegram_products
                    WHERE created_product_id IN ('101', '104', '105')
                      AND telegram_message_date IS NULL
                    """
                ).fetchone()[0]

        self.assertEqual(cleared, 2)
        self.assertEqual(missing_count, 2)

    def test_backfill_missing_dates_batches_and_sleeps_between_batches(self) -> None:
        with patch(
            "activation_product_by_date._load_missing_telegram_date_rows_for_product_ids",
            side_effect=[
                [{"message_id": 1}, {"message_id": 2}],
                [{"message_id": 3}],
                [{"message_id": 3}],
                [],
            ],
        ) as load_missing:
            with patch(
                "activation_product_by_date._backfill_telegram_message_dates_from_telegram_async",
                side_effect=[
                    {"updated": 2, "failed": 0},
                    {"updated": 0, "failed": 1},
                ],
            ):
                with patch("activation_product_by_date.random.uniform", return_value=0) as uniform:
                    with patch("activation_product_by_date.time.sleep") as sleep:
                        with redirect_stdout(StringIO()):
                            result = backfill_missing_telegram_message_dates_for_product_ids(
                                ["101", "102", "103"],
                                limit=3,
                                batch_size=2,
                                sleep_min_seconds=30,
                                sleep_max_seconds=60,
                            )

        self.assertEqual(result, {"checked": 3, "updated": 2, "failed": 1})
        self.assertEqual(load_missing.call_count, 3)
        uniform.assert_called_once_with(30.0, 60.0)
        sleep.assert_not_called()

    def test_parser_has_activation_arguments(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--dry-run",
                "--products-type",
                "DEACTIVATED",
                "--max-age-days",
                "183",
                "--telegram-id",
                "11",
                "--message-id",
                "501",
                "--telegram-date-backfill-limit",
                "50",
                "--clear-telegram-dates-limit",
                "2",
                "--exclude-account-id",
                "АКК 3",
                "--telegram-date-backfill-batch-size",
                "25",
                "--telegram-date-backfill-sleep-min",
                "30",
                "--telegram-date-backfill-sleep-max",
                "60",
            ]
        )

        self.assertTrue(args.dry_run)
        self.assertEqual(args.products_type, ["DEACTIVATED"])
        self.assertEqual(args.max_age_days, 183)
        self.assertEqual(args.telegram_id, 11)
        self.assertEqual(args.message_id, 501)
        self.assertEqual(args.telegram_date_backfill_limit, 50)
        self.assertEqual(args.clear_telegram_dates_limit, 2)
        self.assertEqual(args.exclude_account_id, ["АКК 3"])
        self.assertEqual(args.telegram_date_backfill_batch_size, 25)
        self.assertEqual(args.telegram_date_backfill_sleep_min, 30)
        self.assertEqual(args.telegram_date_backfill_sleep_max, 60)

    def test_parser_default_backfill_limit_is_not_one_batch(self) -> None:
        args = build_arg_parser().parse_args(["--dry-run"])

        self.assertEqual(
            args.telegram_date_backfill_limit,
            DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
        )
        self.assertGreater(args.telegram_date_backfill_limit, args.telegram_date_backfill_batch_size)

    def test_parser_default_activation_sleep_is_8_to_15_seconds(self) -> None:
        args = build_arg_parser().parse_args(["--dry-run"])

        self.assertEqual(args.sleep_min, DEFAULT_ACTIVATION_SLEEP_MIN_SECONDS)
        self.assertEqual(args.sleep_max, DEFAULT_ACTIVATION_SLEEP_MAX_SECONDS)
        self.assertEqual(args.sleep_min, 8.0)
        self.assertEqual(args.sleep_max, 15.0)

    def test_parser_default_parallel_workers_is_5(self) -> None:
        args = build_arg_parser().parse_args(["--all-accounts", "--parallel-accounts"])

        self.assertTrue(args.parallel_accounts)
        self.assertEqual(args.max_workers, DEFAULT_MAX_ACCOUNT_WORKERS)
        self.assertEqual(args.max_workers, 5)

    def test_default_shared_db_path_uses_accounts_base_dir(self) -> None:
        session = AccountSession(
            account_id="acc-1",
            name="Account 1",
            state_dir=Path("C:/repo/runtime/desktop-backend-data/accounts/acc-1"),
            auth_path=Path("C:/repo/runtime/desktop-backend-data/accounts/acc-1/auth.json"),
            db_path=Path("C:/repo/runtime/desktop-backend-data/accounts/acc-1/shafa.sqlite3"),
            media_dir=Path("C:/repo/runtime/desktop-backend-data/accounts/acc-1/media"),
            accounts_dir=Path("C:/repo/runtime/desktop-backend-data/accounts"),
        )

        self.assertEqual(
            _default_shared_telegram_db_path(session),
            Path("C:/repo/runtime/desktop-backend-data/telegram_shared/telegram_feed.sqlite3"),
        )


if __name__ == "__main__":
    unittest.main()
