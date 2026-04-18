import _test_path  # noqa: F401
import sqlite3
from pathlib import Path
from unittest.mock import patch

from data import db


def test_save_sizes_replaces_existing_catalog_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "shafa.sqlite3"
    original_connect = db._connect

    db._DB_INITIALIZED = False
    db._SIZE_ID_BY_NAME_CACHE = None
    db._SIZE_ID_BY_NAME_CATALOG_CACHE = None
    db._SIZE_IDS_CACHE = None
    db._SIZE_IDS_CATALOG_CACHE = None

    with patch("data.db._connect", side_effect=lambda db_path_arg=db_path: original_connect(db_path)):
        db.init_db(db_path=db_path)
        db.save_sizes(
            [
                {"id": 1, "primarySizeName": "36"},
                {"id": 2, "primarySizeName": "37"},
            ],
            catalog_slug="obuv/krossovki",
        )
        db.save_sizes(
            [
                {"id": 10, "primarySizeName": "38"},
            ],
            catalog_slug="obuv/krossovki",
        )

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT size_id, primary_size_name
                FROM size_catalogs
                WHERE catalog_slug = ?
                ORDER BY size_id
                """,
                ("obuv/krossovki",),
            ).fetchall()

    assert rows == [(10, "38")]
