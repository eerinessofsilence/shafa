import _test_path  # noqa: F401
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.requests import deactivate_product
from data.db import list_pending_invalid_uploaded_products


class DeactivateInvalidProductsTests(unittest.TestCase):
    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_uploaded_product_identity")
    def test_find_invalid_uploaded_products_uses_raw_payload_name(
        self,
        is_valid_uploaded_product_identity,
        list_active_uploaded_product_payloads,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
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
            is_valid_uploaded_product_identity.side_effect = [False, True]

            result = deactivate_product.find_invalid_uploaded_products(db_path=db_path)

        self.assertEqual(
            result,
            [
                {
                    "product_id": 12345,
                    "name": "Bad title",
                    "created_at": "2026-05-07 12:00:00",
                    "invalid_reason": "missing_brand_and_clothes_name",
                }
            ],
        )

    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_uploaded_product_identity")
    def test_find_invalid_uploaded_products_cleans_special_symbols_before_validation(
        self,
        is_valid_uploaded_product_identity,
        list_active_uploaded_product_payloads,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
            list_active_uploaded_product_payloads.return_value = [
                {
                    "product_id": "12345",
                    "name": "fallback",
                    "raw_payload": json.dumps(
                        {"name": '!!! Футболка-туніка /// з льону ???'}
                    ),
                    "created_at": "2026-05-07 12:00:00",
                }
            ]
            is_valid_uploaded_product_identity.return_value = True

            result = deactivate_product.find_invalid_uploaded_products(db_path=db_path)

        self.assertEqual(result, [])
        is_valid_uploaded_product_identity.assert_called_once_with(
            "Футболка-туніка з льону",
            None,
        )

    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_uploaded_product_identity")
    @patch("core.requests.deactivate_product._load_account_active_product_name_index")
    @patch("core.requests.deactivate_product._deactivate_products_with_cookies")
    @patch("core.requests.deactivate_product._load_shafa_cookies_for_account")
    def test_deactivate_invalid_uploaded_products_marks_successful_items(
        self,
        load_shafa_cookies_for_account,
        deactivate_products_with_cookies,
        load_account_active_product_name_index,
        is_valid_uploaded_product_identity,
        list_active_uploaded_product_payloads,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
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
            is_valid_uploaded_product_identity.side_effect = [False, False, True]
            load_shafa_cookies_for_account.return_value = [{"name": "csrftoken", "value": "token"}]
            load_account_active_product_name_index.return_value = {
                "bad title 1": [901],
                "bad title 2": [902],
            }
            deactivate_products_with_cookies.side_effect = [
                {"isSuccess": True, "errors": []},
                {"isSuccess": False, "errors": [{"field": "id"}]},
            ]

            result = deactivate_product._deactivate_invalid_uploaded_products_for_account(
                account_name="default",
                storage_state_path=None,
                db_path=db_path,
            )
            pending = list_pending_invalid_uploaded_products(db_path=db_path)

        self.assertEqual(result["account"], "default")
        self.assertEqual(result["deactivated"], [902])
        self.assertEqual(len(result["invalid"]), 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["product_id"], "101")
        deactivate_products_with_cookies.assert_any_call([902], [{"name": "csrftoken", "value": "token"}])
        deactivate_products_with_cookies.assert_any_call([901], [{"name": "csrftoken", "value": "token"}])

    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_uploaded_product_identity")
    @patch("core.requests.deactivate_product._load_account_active_product_name_index")
    @patch("core.requests.deactivate_product._deactivate_products_with_cookies")
    @patch("core.requests.deactivate_product._load_shafa_cookies_for_account")
    def test_deactivate_invalid_uploaded_products_retries_with_db_cookies_after_auth_error(
        self,
        load_shafa_cookies_for_account,
        deactivate_products_with_cookies,
        load_account_active_product_name_index,
        is_valid_uploaded_product_identity,
        list_active_uploaded_product_payloads,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
            storage_state_path = Path(temp_dir) / "auth.json"
            list_active_uploaded_product_payloads.return_value = [
                {
                    "product_id": "101",
                    "name": "bad-1",
                    "raw_payload": json.dumps({"name": "Bad title 1"}),
                    "created_at": "2026-05-07 12:00:00",
                }
            ]
            is_valid_uploaded_product_identity.return_value = False
            load_shafa_cookies_for_account.side_effect = [
                [{"name": "csrftoken", "value": "storage-token"}],
                [{"name": "csrftoken", "value": "db-token"}],
            ]
            load_account_active_product_name_index.side_effect = [
                RuntimeError(
                    "GraphQL errors: [{'message': 'User not authenticated.', 'path': ['viewer']}]"
                ),
                {"bad title 1": [901]},
            ]
            deactivate_products_with_cookies.return_value = {
                "isSuccess": True,
                "errors": [],
            }

            result = deactivate_product._deactivate_invalid_uploaded_products_for_account(
                account_name="default",
                storage_state_path=storage_state_path,
                db_path=db_path,
            )

        self.assertEqual(result["deactivated"], [901])
        self.assertEqual(result["errors"], [])
        self.assertEqual(load_shafa_cookies_for_account.call_count, 2)
        self.assertEqual(
            load_shafa_cookies_for_account.call_args_list[0].kwargs,
            {
                "storage_state_path": storage_state_path,
                "db_path": db_path,
            },
        )
        self.assertEqual(
            load_shafa_cookies_for_account.call_args_list[1].kwargs,
            {
                "storage_state_path": None,
                "db_path": db_path,
            },
        )
        deactivate_products_with_cookies.assert_called_once_with(
            [901],
            [{"name": "csrftoken", "value": "db-token"}],
        )

    @patch("core.requests.deactivate_product.list_active_uploaded_product_payloads")
    @patch("core.requests.deactivate_product.is_valid_uploaded_product_identity")
    def test_find_invalid_uploaded_products_skips_rows_without_numeric_product_id(
        self,
        is_valid_uploaded_product_identity,
        list_active_uploaded_product_payloads,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shafa.sqlite3"
            list_active_uploaded_product_payloads.return_value = [
                {
                    "product_id": "abc",
                    "name": "bad",
                    "raw_payload": json.dumps({"name": "Bad title"}),
                    "created_at": "2026-05-07 12:00:00",
                }
            ]
            is_valid_uploaded_product_identity.return_value = False

            result = deactivate_product.find_invalid_uploaded_products(db_path=db_path)

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

    @patch("core.requests.deactivate_product._deactivate_invalid_uploaded_products_for_account")
    @patch("core.requests.deactivate_product._discover_shafa_account_contexts")
    def test_deactivate_next_invalid_uploaded_product_processes_only_one_item(
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
                "checked": 5,
                "invalid": [{"product_id": 11, "name": "Bad 1", "created_at": "2026-05-07"}],
                "deactivated": [1011],
                "errors": [],
            },
        ]

        result = deactivate_product.deactivate_next_invalid_uploaded_product()

        self.assertEqual(
            result["deactivated"],
            [{"account": "acc-1", "product_id": 1011}],
        )
        deactivate_for_account.assert_called_once_with(
            account_name="acc-1",
            storage_state_path=Path("/tmp/acc-1/auth.json"),
            db_path=Path("/tmp/acc-1/shafa.sqlite3"),
            max_items=1,
        )

    @patch("core.requests.deactivate_product._deactivate_invalid_uploaded_products_for_account")
    @patch("core.requests.deactivate_product._discover_shafa_account_contexts")
    def test_deactivate_next_invalid_uploaded_product_skips_account_level_auth_error(
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
                "deactivated": [],
                "errors": [{"product_id": None, "name": "", "reason": "authentication_required"}],
            },
            {
                "account": "acc-2",
                "checked": 2,
                "invalid": [{"product_id": 22, "name": "Bad 2", "created_at": "2026-05-07"}],
                "deactivated": [2022],
                "errors": [],
            },
        ]

        result = deactivate_product.deactivate_next_invalid_uploaded_product()

        self.assertEqual(
            result["deactivated"],
            [{"account": "acc-2", "product_id": 2022}],
        )
        self.assertEqual(
            result["errors"],
            [
                {
                    "account": "acc-1",
                    "product_id": None,
                    "name": "",
                    "reason": "authentication_required",
                }
            ],
        )
        self.assertEqual(deactivate_for_account.call_count, 2)


if __name__ == "__main__":
    unittest.main()
