import unittest
from unittest.mock import patch

import controller.data_controller as dc


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
        get_channel_ids.return_value = [1]
        increment_attempt.return_value = 1

        attempts, skipped = dc.register_product_failure(
            11543,
            failure_reason="NO_UPLOADABLE_PHOTOS",
        )

        self.assertEqual(attempts, 1)
        self.assertFalse(skipped)
        mark_created.assert_not_called()

    @patch("controller.data_controller.mark_telegram_product_created")
    @patch("controller.data_controller.increment_telegram_product_attempt")
    def test_second_failure_marks_product_skipped(
        self,
        increment_attempt,
        mark_created,
    ):
        increment_attempt.return_value = dc.MAX_PRODUCT_CREATE_ATTEMPTS

        attempts, skipped = dc.register_product_failure(
            11543,
            failure_reason="NO_UPLOADABLE_PHOTOS",
            channel_id=9,
        )

        self.assertEqual(attempts, dc.MAX_PRODUCT_CREATE_ATTEMPTS)
        self.assertTrue(skipped)
        mark_created.assert_called_once_with(
            9,
            11543,
            created_product_id=dc.SKIPPED_CREATE_RETRY_LIMIT,
        )
