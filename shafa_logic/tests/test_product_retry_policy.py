import _test_path
import os
import unittest
from unittest.mock import patch

import controller.data_controller as dc
from core.product_failures import handle_non_retryable_product_failure


class ProductRetryPolicyTests(unittest.TestCase):
    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.increment_telegram_product_attempt")
    @patch("controller.data_controller._get_channel_ids")
    def test_first_failure_keeps_product_in_queue(
        self,
        get_channel_ids,
        increment_attempt,
        mark_created,
    ):
        with patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False):
            get_channel_ids.return_value = [1]
            increment_attempt.return_value = 1

            attempts, skipped = dc.register_product_failure(
                11543,
                failure_reason="NO_UPLOADABLE_PHOTOS",
            )

        self.assertEqual(attempts, 1)
        self.assertFalse(skipped)
        increment_attempt.assert_called_once_with(
            1,
            11543,
            failure_reason="NO_UPLOADABLE_PHOTOS",
            account_id="acc-1",
        )
        mark_created.assert_not_called()

    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.increment_telegram_product_attempt")
    def test_second_failure_marks_product_skipped(
        self,
        increment_attempt,
        mark_created,
    ):
        with patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False):
            increment_attempt.return_value = dc.MAX_PRODUCT_CREATE_ATTEMPTS

            attempts, skipped = dc.register_product_failure(
                11543,
                failure_reason="NO_UPLOADABLE_PHOTOS",
                channel_id=9,
            )

        self.assertEqual(attempts, dc.MAX_PRODUCT_CREATE_ATTEMPTS)
        self.assertTrue(skipped)
        increment_attempt.assert_called_once_with(
            9,
            11543,
            failure_reason="NO_UPLOADABLE_PHOTOS",
            account_id="acc-1",
        )
        mark_created.assert_called_once_with(
            9,
            11543,
            created_product_id=dc.SKIPPED_CREATE_RETRY_LIMIT,
            account_id="acc-1",
        )

    @patch("core.product_failures.register_product_failure")
    @patch("core.product_failures.mark_product_created")
    def test_non_retryable_failure_skips_product_immediately(
        self,
        mark_created,
        register_failure,
    ):
        handle_non_retryable_product_failure(
            message_id=11543,
            channel_id=9,
            failure_reason="BRAND_NOT_RESOLVED",
            detail_message="Не удалось распознать бренд. Запусти Bootstrap sizes/brands.",
        )

        register_failure.assert_not_called()
        mark_created.assert_called_once_with(
            11543,
            created_product_id="SKIPPED_BRAND_NOT_RESOLVED",
            channel_id=9,
        )
