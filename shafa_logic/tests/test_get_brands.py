import _test_path  # noqa: F401
import unittest
from unittest.mock import Mock, patch

from core.requests.get_brands import get_brands


class GetBrandsTests(unittest.TestCase):
    @patch("core.requests.get_brands.save_brands")
    @patch("core.requests.get_brands.read_response_json")
    def test_merges_top_brands_and_brands(self, read_response_json, save_brands):
        ctx = Mock()
        ctx.request.post.return_value = object()
        read_response_json.return_value = {
            "data": {
                "filterTopBrands": {
                    "topBrands": [
                        {"id": 10, "name": "Nike"},
                        {"id": 20, "name": "Asics"},
                    ],
                    "brands": [
                        {"id": 20, "name": "Asics"},
                        {"id": 30, "name": "Sandro Paris"},
                    ],
                }
            }
        }

        brands = get_brands(ctx, "token")

        self.assertEqual(
            brands,
            [
                {"id": 10, "name": "Nike"},
                {"id": 20, "name": "Asics"},
                {"id": 30, "name": "Sandro Paris"},
            ],
        )
        save_brands.assert_called_once_with(brands)
