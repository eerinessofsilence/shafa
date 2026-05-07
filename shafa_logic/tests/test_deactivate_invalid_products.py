import _test_path  # noqa: F401
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core.requests import deactivate_product


class DeactivateInvalidProductsTests(unittest.TestCase):
    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_product_name")
    def test_find_invalid_uploaded_products_uses_raw_payload_name(
        self,
        is_valid_product_name,
        list_active_uploaded_product_payloads,
    ):
        list_active_uploaded_product_payloads.return_value = [
            {
                "product_id": "12345",
                "name": "fallback",
                "raw_payload": json.dumps({"name": "Bad title"}),
                "created_at": "2026-05-07 12:00:00",
            },
            {
                "product_id": "12346",
                "name": "valid",
                "raw_payload": json.dumps({"name": "Valid title"}),
                "created_at": "2026-05-07 12:01:00",
            },
        ]
        is_valid_product_name.side_effect = [False, True]

        result = deactivate_product.find_invalid_uploaded_products()

        self.assertEqual(
            result,
            [
                {
                    "product_id": 12345,
                    "name": "Bad title",
                    "created_at": "2026-05-07 12:00:00",
                }
            ],
        )

    @patch("core.requests.deactivate_product.mark_uploaded_products_deactivated")
    @patch("core.requests.deactivate_product._deactivate_products_with_cookies")
    @patch("core.requests.deactivate_product._load_shafa_cookies_for_account")
    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_product_name")
    def test_deactivate_invalid_uploaded_products_marks_successful_items(
        self,
        is_valid_product_name,
        list_active_uploaded_product_payloads,
        load_shafa_cookies_for_account,
        deactivate_products_with_cookies,
        mark_uploaded_products_deactivated,
    ):
        list_active_uploaded_product_payloads.return_value = [
            {
                "product_id": "101",
                "name": "bad-1",
                "raw_payload": json.dumps({"name": "Bad title 1"}),
                "created_at": "2026-05-07 12:00:00",
            },
            {
                "product_id": "102",
                "name": "bad-2",
                "raw_payload": json.dumps({"name": "Bad title 2"}),
                "created_at": "2026-05-07 12:01:00",
            },
            {
                "product_id": "103",
                "name": "good",
                "raw_payload": json.dumps({"name": "Good title"}),
                "created_at": "2026-05-07 12:02:00",
            },
        ]
        is_valid_product_name.side_effect = [False, False, True]
        load_shafa_cookies_for_account.return_value = [{"name": "csrftoken", "value": "token"}]
        deactivate_products_with_cookies.side_effect = [
            {"isSuccess": True, "errors": []},
            {"isSuccess": False, "errors": [{"field": "id"}]},
        ]

        result = deactivate_product._deactivate_invalid_uploaded_products_for_account(
            account_name="default",
            storage_state_path=None,
            db_path=Path("/home/slava/shafa_app/data/shafa.sqlite3"),
        )

        self.assertEqual(result["account"], "default")
        self.assertEqual(result["deactivated"], [101])
        self.assertEqual(len(result["invalid"]), 2)
        self.assertEqual(len(result["errors"]), 1)
        mark_uploaded_products_deactivated.assert_called_once_with(
            [101],
            db_path=Path("/home/slava/shafa_app/data/shafa.sqlite3"),
        )

    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_product_name")
    def test_find_invalid_uploaded_products_skips_rows_without_numeric_product_id(
        self,
        is_valid_product_name,
        list_active_uploaded_product_payloads,
    ):
        list_active_uploaded_product_payloads.return_value = [
            {
                "product_id": "abc",
                "name": "bad",
                "raw_payload": json.dumps({"name": "Bad title"}),
                "created_at": "2026-05-07 12:00:00",
            }
        ]
        is_valid_product_name.return_value = False

        result = deactivate_product.find_invalid_uploaded_products()

        self.assertEqual(result, [])

    @patch("core.requests.deactivate_product._deactivate_invalid_uploaded_products_for_account")
    @patch("core.requests.deactivate_product._discover_shafa_account_contexts")
    def test_deactivate_invalid_uploaded_products_processes_all_accounts(
        self,
        discover_accounts,
        deactivate_for_account,
    ):
        discover_accounts.return_value = [
            {
                "name": "acc-1",
                "storage_state_path": Path("/tmp/acc-1/auth.json"),
                "db_path": Path("/tmp/acc-1/shafa.sqlite3"),
            },
            {
                "name": "acc-2",
                "storage_state_path": Path("/tmp/acc-2/auth.json"),
                "db_path": Path("/tmp/acc-2/shafa.sqlite3"),
            },
        ]
        deactivate_for_account.side_effect = [
            {
                "account": "acc-1",
                "checked": 3,
                "invalid": [{"product_id": 11, "name": "Bad 1", "created_at": "2026-05-07"}],
                "deactivated": [11],
                "errors": [],
            },
            {
                "account": "acc-2",
                "checked": 2,
                "invalid": [{"product_id": 22, "name": "Bad 2", "created_at": "2026-05-07"}],
                "deactivated": [],
                "errors": [{"product_id": 22, "name": "Bad 2", "reason": "missing_cookies"}],
            },
        ]

        result = deactivate_product.deactivate_invalid_uploaded_products()

        self.assertEqual(result["checked"], 5)
        self.assertEqual(
            result["deactivated"],
            [{"account": "acc-1", "product_id": 11}],
        )
        self.assertEqual(
            result["invalid"],
            [
                {"account": "acc-1", "product_id": 11, "name": "Bad 1", "created_at": "2026-05-07"},
                {"account": "acc-2", "product_id": 22, "name": "Bad 2", "created_at": "2026-05-07"},
            ],
        )
        self.assertEqual(
            result["errors"],
            [{"account": "acc-2", "product_id": 22, "name": "Bad 2", "reason": "missing_cookies"}],
        )


if __name__ == "__main__":
    unittest.main()
