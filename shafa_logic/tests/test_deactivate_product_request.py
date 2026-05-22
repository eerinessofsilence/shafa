import _test_path  # noqa: F401

import json
import unittest
from unittest.mock import patch

from core.requests.deactivate_product import deactivate_product


class DeactivateProductRequestTests(unittest.TestCase):
    def test_deactivate_product_sends_expected_mutation(self) -> None:
        captured: dict[str, object] = {}

        def _fake_request_json(url, payload, headers, cookies):
            captured["url"] = url
            captured["payload"] = json.loads(payload.decode("utf-8"))
            captured["headers"] = headers
            captured["cookies"] = cookies
            return {"data": {"deactivateProducts": {"isSuccess": True, "errors": []}}}

        with (
            patch(
                "core.requests.deactivate_product._load_shafa_cookies",
                return_value=[{"name": "csrftoken", "value": "token"}],
            ),
            patch(
                "core.requests.deactivate_product._get_csrftoken_from_cookies",
                return_value="token",
            ),
            patch(
                "core.requests.deactivate_product._request_json",
                side_effect=_fake_request_json,
            ),
        ):
            deactivate_product("208499836")

        payload = captured["payload"]
        self.assertEqual(payload["operationName"], "deactivateProducts")
        self.assertEqual(
            payload["variables"],
            {
                "includeIds": [208499836],
                "excludeIds": None,
                "allProducts": False,
            },
        )
        self.assertIn("deactivateProducts", payload["query"])

    def test_deactivate_product_raises_top_level_graphql_error(self) -> None:
        with (
            patch(
                "core.requests.deactivate_product._load_shafa_cookies",
                return_value=[{"name": "csrftoken", "value": "token"}],
            ),
            patch(
                "core.requests.deactivate_product._get_csrftoken_from_cookies",
                return_value="token",
            ),
            patch(
                "core.requests.deactivate_product._request_json",
                return_value={
                    "errors": [{"message": "User not authenticated."}],
                    "data": {"deactivateProducts": None},
                },
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "User not authenticated"):
                deactivate_product("208499836")

    def test_deactivate_product_raises_business_error(self) -> None:
        with (
            patch(
                "core.requests.deactivate_product._load_shafa_cookies",
                return_value=[{"name": "csrftoken", "value": "token"}],
            ),
            patch(
                "core.requests.deactivate_product._get_csrftoken_from_cookies",
                return_value="token",
            ),
            patch(
                "core.requests.deactivate_product._request_json",
                return_value={
                    "data": {
                        "deactivateProducts": {
                            "isSuccess": False,
                            "errors": [
                                {
                                    "field": "__all__",
                                    "messages": [
                                        {"code": "user_already_start_activation_deactivation"}
                                    ],
                                }
                            ],
                        }
                    }
                },
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "user_already_start_activation_deactivation",
            ):
                deactivate_product("208499836")


if __name__ == "__main__":
    unittest.main()
