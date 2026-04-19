import _test_path  # noqa: F401
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TelegramChannelStorageTests(unittest.TestCase):
    def test_channel_crud_uses_runtime_json_and_not_legacy_db_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_path = Path(temp_dir) / "shafa_telegram_channels.json"
            db_path = Path(temp_dir) / "shafa.sqlite3"

            with (
                patch("telegram_subscription.sync._runtime_channels_path", return_value=runtime_path),
                patch("telegram_subscription.sync._mirror_channels_to_db"),
            ):
                import data.db as data_db

                runtime_path.write_text("[]", encoding="utf-8")
                data_db._DB_INITIALIZED = False
                data_db.init_db(db_path)
                data_db.save_telegram_channels([(-1001, "Channel One", "main")])
                self.assertEqual(
                    data_db.load_telegram_channels(),
                    [{"channel_id": -1001, "name": "Channel One", "alias": "main extra_photos"}],
                )

                self.assertTrue(data_db.rename_telegram_channel(-1001, "Renamed"))
                self.assertTrue(data_db.update_telegram_channel_alias(-1001, "extra_photos"))
                self.assertEqual(
                    data_db.load_telegram_channels(),
                    [{"channel_id": -1001, "name": "Renamed", "alias": "main extra_photos"}],
                )

                data_db.delete_telegram_channel(-1001)
                self.assertEqual(data_db.load_telegram_channels(), [])

            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            self.assertNotIn("telegram_channels", tables)


if __name__ == "__main__":
    unittest.main()
