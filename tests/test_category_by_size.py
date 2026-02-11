import unittest

import controller.data_controller as dc


class CategoryBySizeTests(unittest.TestCase):
    def test_women_category_for_sizes_36_to_41(self):
        category = dc._resolve_catalog_slug("36", ["37", "40", "41"])
        self.assertEqual(category, dc.WOMEN_SNEAKERS_CATEGORY)

    def test_default_category_when_any_size_out_of_women_range(self):
        category = dc._resolve_catalog_slug("41", ["42"])
        self.assertEqual(category, dc.DEFAULT_SHOES_CATEGORY)

    def test_default_category_when_sizes_are_not_numeric(self):
        category = dc._resolve_catalog_slug("ONE SIZE", ["M"])
        self.assertEqual(category, dc.DEFAULT_SHOES_CATEGORY)
