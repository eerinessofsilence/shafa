import _test_path
import unittest
from unittest.mock import Mock, patch

from core.requests.get_brands import (
    CLOTHING_BRANDS_CATALOG_SLUG,
    get_brands,
    get_clothing_brands,
    resolve_brand_catalog_slug,
)


class GetBrandsTests(unittest.TestCase):
    def test_resolve_brand_catalog_slug_maps_clothing_to_shared_slug(self):
        self.assertEqual(
            resolve_brand_catalog_slug("sport-otdyh/sportivnyye-shtany"),
            CLOTHING_BRANDS_CATALOG_SLUG,
        )
        self.assertEqual(
            resolve_brand_catalog_slug("verhnyaya-odezhda/palto"),
            CLOTHING_BRANDS_CATALOG_SLUG,
        )
        self.assertEqual(
            resolve_brand_catalog_slug("obuv/krossovki"),
            "obuv/krossovki",
        )

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

    @patch("core.requests.get_brands.save_brands")
    @patch("core.requests.get_brands.read_response_json")
    def test_get_brands_uses_shared_clothing_slug_for_clothing_catalog(
        self,
        read_response_json,
        save_brands,
    ):
        ctx = Mock()
        ctx.request.post.return_value = object()
        read_response_json.return_value = {
            "data": {"filterTopBrands": {"topBrands": [], "brands": []}}
        }

        get_brands(ctx, "token", catalog_slug="sport-otdyh/sportivnyye-shtany")

        payload = ctx.request.post.call_args.kwargs["data"]
        self.assertIn(CLOTHING_BRANDS_CATALOG_SLUG, payload)
        save_brands.assert_called_once_with([])

    @patch("core.requests.get_brands.get_brands")
    def test_get_clothing_brands_uses_shared_clothing_slug(self, get_brands_mock):
        get_brands_mock.return_value = []
        ctx = Mock()

        get_clothing_brands(ctx, "token")

        get_brands_mock.assert_called_once_with(
            ctx,
            "token",
            catalog_slug=CLOTHING_BRANDS_CATALOG_SLUG,
        )
