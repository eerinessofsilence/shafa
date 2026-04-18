import _test_path
import unittest
from unittest.mock import Mock, patch

from core.requests.get_sizes import get_sizes


class GetSizesTests(unittest.TestCase):
    @patch("core.requests.get_sizes.save_sizes")
    @patch("core.requests.get_sizes.read_response_json")
    def test_reads_sizes_from_v3_batch_filter_size(self, read_response_json, save_sizes):
        ctx = Mock()
        ctx.request.post.return_value = object()
        read_response_json.return_value = [
            {
                "data": {
                    "filterSize": [
                        {
                            "id": 171,
                            "primarySizeName": "36",
                            "secondarySizeName": None,
                            "__typename": "ProductSizeType",
                        },
                        {
                            "id": 172,
                            "primarySizeName": "37",
                            "secondarySizeName": None,
                            "__typename": "ProductSizeType",
                        },
                        {
                            "id": 172,
                            "primarySizeName": "37",
                            "secondarySizeName": None,
                            "__typename": "ProductSizeType",
                        },
                    ]
                }
            }
        ]

        sizes = get_sizes(ctx, "token", catalog_slug="obuv/krossovki")

        self.assertEqual(
            sizes,
            [
                {
                    "id": 171,
                    "primarySizeName": "36",
                    "secondarySizeName": None,
                    "__typename": "ProductSizeType",
                },
                {
                    "id": 172,
                    "primarySizeName": "37",
                    "secondarySizeName": None,
                    "__typename": "ProductSizeType",
                },
            ],
        )
        save_sizes.assert_called_once_with(sizes, catalog_slug="obuv/krossovki")
