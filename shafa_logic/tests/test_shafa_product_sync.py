import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data import db


class ShafaProductSyncTests(unittest.TestCase):
    def _patch_local_db(self, db_path: Path):
        original_connect = db._connect
        db._DB_INITIALIZED_PATHS.discard(db_path)
        return patch(
            "data.db._connect",
            side_effect=lambda db_path_arg=db_path: original_connect(db_path),
        )

    def test_sync_uploaded_products_from_shafa_inserts_active_products(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
            with self._patch_local_db(db_path):
                db.init_db(db_path=db_path)
                result = db.sync_uploaded_products_from_shafa(
                    [
                        {
                            "product_id": "111",
                            "name": "Nike Air Force 1",
                            "created_at": "2024-01-10T09:15:00+00:00",
                            "status_title": "Активно",
                            "price": 2200,
                            "size": "41",
                            "raw_payload": {
                                "id": "111",
                                "name": "Nike Air Force 1",
                                "createdAt": "2024-01-10T09:15:00+00:00",
                                "price": 2200,
                                "size": "41",
                                "brand": {"id": 17, "name": "Nike"},
                            },
                        },
                        {
                            "product_id": "222",
                            "name": "Adidas Campus",
                            "created_at": "2024-02-01T12:00:00+00:00",
                            "status_title": "Активно",
                            "price": 1800,
                            "size": "42",
                            "raw_payload": {
                                "id": "222",
                                "name": "Adidas Campus",
                                "createdAt": "2024-02-01T12:00:00+00:00",
                                "price": 1800,
                                "size": "42",
                                "brand": {"id": 21, "name": "Adidas"},
                            },
                        },
                    ]
                )

                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT product_id, name, brand, size, price, shafa_created_at, status_title, is_active
                        FROM uploaded_products
                        ORDER BY product_id
                        """
                    ).fetchall()

                listed = db.list_uploaded_products(limit=10)

        self.assertEqual(
            result,
            {"total": 2, "inserted": 2, "updated": 0, "deactivated": 0},
        )
        self.assertEqual(
            rows,
            [
                (
                    "111",
                    "Nike Air Force 1",
                    17,
                    41,
                    2200,
                    "2024-01-10 09:15:00",
                    "Активно",
                    1,
                ),
                (
                    "222",
                    "Adidas Campus",
                    21,
                    42,
                    1800,
                    "2024-02-01 12:00:00",
                    "Активно",
                    1,
                ),
            ],
        )
        self.assertEqual(listed[0]["product_id"], "222")
        self.assertEqual(listed[0]["created_at"], "2024-02-01 12:00:00")

    def test_sync_uploaded_products_from_shafa_updates_existing_and_marks_missing_inactive(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
            with self._patch_local_db(db_path):
                db.init_db(db_path=db_path)
                db.sync_uploaded_products_from_shafa(
                    [
                        {
                            "product_id": "111",
                            "name": "Nike Air Force 1",
                            "created_at": "2024-01-10T09:15:00+00:00",
                            "status_title": "Активно",
                            "price": 2200,
                            "size": "41",
                            "raw_payload": {"id": "111", "name": "Nike Air Force 1"},
                        },
                        {
                            "product_id": "222",
                            "name": "Adidas Campus",
                            "created_at": "2024-02-01T12:00:00+00:00",
                            "status_title": "Активно",
                            "price": 1800,
                            "size": "42",
                            "raw_payload": {"id": "222", "name": "Adidas Campus"},
                        },
                    ]
                )

                result = db.sync_uploaded_products_from_shafa(
                    [
                        {
                            "product_id": "111",
                            "name": "Nike Air Force 1 '07",
                            "created_at": "2024-01-10T09:15:00+00:00",
                            "status_title": "Активно",
                            "price": 2300,
                            "size": "41",
                            "raw_payload": {"id": "111", "name": "Nike Air Force 1 '07"},
                        }
                    ]
                )

                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT product_id, name, price, is_active
                        FROM uploaded_products
                        ORDER BY product_id
                        """
                    ).fetchall()
                    product_111_count = conn.execute(
                        "SELECT COUNT(*) FROM uploaded_products WHERE product_id = ?",
                        ("111",),
                    ).fetchone()[0]

        self.assertEqual(
            result,
            {"total": 1, "inserted": 0, "updated": 1, "deactivated": 1},
        )
        self.assertEqual(
            rows,
            [
                ("111", "Nike Air Force 1 '07", 2300, 1),
                ("222", "Adidas Campus", 1800, 0),
            ],
        )
        self.assertEqual(product_111_count, 1)

    def test_add_column_if_missing_ignores_duplicate_column_race(self) -> None:
        class _FakeRows:
            def __init__(self, rows: list[dict]) -> None:
                self._rows = rows

            def fetchall(self) -> list[dict]:
                return self._rows

        class _FakeConnection:
            def __init__(self) -> None:
                self._pragma_calls = 0

            def execute(self, sql: str):
                if sql.startswith("PRAGMA table_info"):
                    self._pragma_calls += 1
                    if self._pragma_calls == 1:
                        return _FakeRows([{"name": "id"}])
                    return _FakeRows([{"name": "id"}, {"name": "status_title"}])
                raise sqlite3.OperationalError("duplicate column name: status_title")

        db._add_column_if_missing(
            _FakeConnection(),  # type: ignore[arg-type]
            "uploaded_products",
            "status_title",
            "TEXT",
        )
