import json
import unittest
from unittest.mock import patch

import controller.data_controller as dc


class PickNextProductTests(unittest.TestCase):
    @patch("controller.data_controller._build_product_raw_data")
    @patch("controller.data_controller.parse_message")
    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.get_next_uncreated_telegram_product")
    @patch("controller.data_controller._get_channel_ids")
    def test_skips_pending_row_without_price_or_size_after_reparse(
        self,
        get_channel_ids,
        get_next_uncreated,
        mark_created,
        parse_message,
        build_product_raw_data,
    ):
        get_channel_ids.return_value = [1]
        bad_row = {
            "channel_id": 1,
            "message_id": 10,
            "created_at": "2026-02-11 10:00:00",
            "raw_message": "bad",
            "parsed_data": json.dumps({"name": "bad", "price": "180", "size": "035"}),
        }
        good_row = {
            "channel_id": 1,
            "message_id": 11,
            "created_at": "2026-02-11 10:01:00",
            "raw_message": "good",
            "parsed_data": json.dumps({"name": "good", "price": "1600", "size": "41"}),
        }
        get_next_uncreated.side_effect = [bad_row, good_row]
        parse_message.side_effect = [
            {"name": "bad", "price": "", "size": ""},
            {"name": "good", "price": "1600", "size": "41", "additional_sizes": []},
        ]
        build_product_raw_data.return_value = {"size": 176, "price": 1600}

        result = dc._pick_next_product_for_upload()

        mark_created.assert_called_once_with(
            1,
            10,
            created_product_id="SKIPPED_MISSING_DATA",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["message_id"], 11)
