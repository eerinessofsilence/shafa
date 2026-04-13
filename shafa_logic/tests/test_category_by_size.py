import unittest
from unittest.mock import patch

import controller.data_controller as dc


class CategoryBySizeTests(unittest.TestCase):
    def test_women_category_for_sizes_36_to_41(self):
        category = dc._resolve_catalog_slug("36", ["37", "40", "41"])
        self.assertEqual(category, dc.WOMEN_SNEAKERS_CATEGORY)

    def test_default_category_when_any_size_out_of_women_range(self):
        category = dc._resolve_catalog_slug("41", ["42"])
        self.assertEqual(category, dc.DEFAULT_SHOES_CATEGORY)

    def test_women_category_for_range_text(self):
        category = dc._resolve_catalog_slug("36-41", [])
        self.assertEqual(category, dc.WOMEN_SNEAKERS_CATEGORY)

    def test_default_category_when_sizes_are_not_numeric(self):
        category = dc._resolve_catalog_slug("ONE SIZE", ["M"])
        self.assertEqual(category, dc.DEFAULT_SHOES_CATEGORY)

    @patch("controller.data_controller.get_size_id_by_name")
    def test_resolve_size_id_supports_decimal_token(self, get_size_id_by_name):
        get_size_id_by_name.side_effect = lambda name, catalog_slug=None: {
            "41": 176
        }.get(name)
        self.assertEqual(dc._resolve_size_id("41.0"), 176)

    @patch("controller.data_controller.get_size_id_by_name")
    def test_resolve_size_id_supports_range_token(self, get_size_id_by_name):
        get_size_id_by_name.side_effect = lambda name, catalog_slug=None: {
            "36": 171
        }.get(name)
        self.assertEqual(dc._resolve_size_id("36-41"), 171)
