import _test_path
import json
import unittest
from unittest.mock import patch
import os

import controller.data_controller as dc


class PickNextProductTests(unittest.TestCase):
    def test_price_validation_accepts_three_digit_price(self):
        self.assertTrue(dc.is_valid_product_price("500"))
        self.assertFalse(dc.is_valid_product_price("20000"))

    @patch("controller.data_controller._build_product_raw_data")
    @patch("controller.data_controller.parse_message")
    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.claim_next_telegram_product_for_creation")
    def test_skips_pending_row_with_invalid_price_after_reparse(
        self,
        claim_next_product,
        mark_created,
        parse_message,
        build_product_raw_data,
    ):
        with patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False):
            bad_row = {
                "channel_id": 1,
                "message_id": 10,
                "created_at": "2026-02-11 10:00:00",
                "raw_message": "bad",
                "parsed_data": json.dumps({"name": "bad", "price": "20000", "size": "41"}),
            }
            good_row = {
                "channel_id": 1,
                "message_id": 11,
                "created_at": "2026-02-11 10:01:00",
                "raw_message": "good",
                "parsed_data": json.dumps(
                    {"name": "Жіноча сукня міді", "price": "1600", "size": "41"}
                ),
            }
            claim_next_product.side_effect = [bad_row, good_row]
            parse_message.side_effect = [
                {"name": "Пальто жіноче", "price": "20000", "size": "41"},
                {
                    "name": "Жіноча сукня міді",
                    "price": "1600",
                    "size": "41",
                    "additional_sizes": [],
                },
            ]
            build_product_raw_data.return_value = {
                "name": "Жіноча сукня міді",
                "size": 176,
                "price": 1600,
            }

            result = dc._pick_next_product_for_upload()

        mark_created.assert_called_once_with(
            1,
            10,
            created_product_id="SKIPPED_INVALID_PRICE",
            account_id="acc-1",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["message_id"], 11)

    @patch("controller.data_controller._build_product_raw_data")
    @patch("controller.data_controller.parse_message")
    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.claim_next_telegram_product_for_creation")
    def test_skips_pending_row_without_price_or_size_after_reparse(
        self,
        claim_next_product,
        mark_created,
        parse_message,
        build_product_raw_data,
    ):
        with patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False):
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
                "parsed_data": json.dumps(
                    {"name": "Жіноча сукня міді", "price": "1600", "size": "41"}
                ),
            }
            claim_next_product.side_effect = [bad_row, good_row]
            parse_message.side_effect = [
                {"name": "bad", "price": "", "size": ""},
                {
                    "name": "Жіноча сукня міді",
                    "price": "1600",
                    "size": "41",
                    "additional_sizes": [],
                },
            ]
            build_product_raw_data.return_value = {
                "name": "Жіноча сукня міді",
                "size": 176,
                "price": 1600,
            }

            result = dc._pick_next_product_for_upload()

        mark_created.assert_called_once_with(
            1,
            10,
            created_product_id="SKIPPED_MISSING_DATA",
            account_id="acc-1",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["message_id"], 11)

    @patch("controller.data_controller._build_product_raw_data")
    @patch("controller.data_controller.parse_message")
    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.claim_next_telegram_product_for_creation")
    def test_skips_pending_row_without_name_after_reparse(
        self,
        claim_next_product,
        mark_created,
        parse_message,
        build_product_raw_data,
    ):
        with patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False):
            bad_row = {
                "channel_id": 1,
                "message_id": 10,
                "created_at": "2026-02-11 10:00:00",
                "raw_message": "bad",
                "parsed_data": json.dumps({"name": "bad", "price": "1600", "size": "41"}),
            }
            good_row = {
                "channel_id": 1,
                "message_id": 11,
                "created_at": "2026-02-11 10:01:00",
                "raw_message": "good",
                "parsed_data": json.dumps(
                    {"name": "Жіноча сукня міді", "price": "1600", "size": "41"}
                ),
            }
            claim_next_product.side_effect = [bad_row, good_row]
            parse_message.side_effect = [
                {"name": "", "price": "1600", "size": "41"},
                {
                    "name": "Жіноча сукня міді",
                    "price": "1600",
                    "size": "41",
                    "additional_sizes": [],
                },
            ]
            build_product_raw_data.return_value = {
                "name": "Жіноча сукня міді",
                "size": 176,
                "price": 1600,
            }

            result = dc._pick_next_product_for_upload()

        mark_created.assert_called_once_with(
            1,
            10,
            created_product_id="SKIPPED_MISSING_DATA",
            account_id="acc-1",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["message_id"], 11)
