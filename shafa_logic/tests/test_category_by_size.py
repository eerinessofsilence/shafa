import _test_path  # noqa: F401
import unittest
from unittest.mock import patch

import controller.data_controller as dc
from data.db import get_size_id_by_name


class CategoryBySizeTests(unittest.TestCase):
    def test_women_category_for_sizes_36_to_41(self):
        category = dc._resolve_catalog_slug("36", ["37", "40", "41"], "")
        self.assertEqual(category, dc.WOMEN_SNEAKERS_CATEGORY)

    def test_default_category_when_any_size_out_of_women_range(self):
        category = dc._resolve_catalog_slug("41", ["42"], "")
        self.assertEqual(category, dc.DEFAULT_SHOES_CATEGORY)

    def test_women_category_for_range_text(self):
        category = dc._resolve_catalog_slug("36-41", [], "")
        self.assertEqual(category, dc.WOMEN_SNEAKERS_CATEGORY)

    def test_default_category_when_sizes_are_not_numeric(self):
        category = dc._resolve_catalog_slug("ONE SIZE", ["M"], "")
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

    def test_extract_sizes_keeps_default_step_one_without_catalog_slug(self):
        size, additional_sizes = dc.extract_sizes(["Розмір: 42-46 універсал"])
        self.assertEqual(size, "42")
        self.assertEqual(additional_sizes, ["43", "44", "45", "46"])

    def test_extract_sizes_uses_step_two_for_clothing_slug(self):
        size, additional_sizes = dc.extract_sizes(
            ["Розмір: 42-46 універсал"],
            even_range_step=True,
        )
        self.assertEqual(size, "42")
        self.assertEqual(additional_sizes, ["44", "46"])

    def test_extract_sizes_handles_comma_separated_clothing_ranges(self):
        size, additional_sizes = dc.extract_sizes(
            ["Розмір: 42-44,46-48"],
            even_range_step=True,
        )
        self.assertEqual(size, "42")
        self.assertEqual(additional_sizes, ["44", "46", "48"])

    def test_extract_numeric_sizes_keeps_step_one_for_mixed_parity_ranges(self):
        self.assertEqual(dc._extract_numeric_sizes("36-41"), [36.0, 37.0, 38.0, 39.0, 40.0, 41.0])

    @patch("controller.data_controller._resolve_brand_id", return_value=None)
    @patch("controller.data_controller._parse_price", return_value=1200)
    @patch("controller.data_controller.find_slug_by_word", return_value="shtany/bryuki")
    @patch("controller.data_controller._resolve_size_id")
    def test_build_product_raw_data_splits_range_into_additional_sizes(
        self,
        resolve_size_id,
        _find_slug_by_word,
        _parse_price,
        _resolve_brand_id,
    ):
        resolve_size_id.side_effect = lambda value, catalog_slug=None, preferred_system=None: {
            "42": 833,
            "44": 834,
            "46": 835,
        }.get(str(value))
        parsed = {
            "word_for_slack": "штани",
            "name": "Штани",
            "description": "desc",
            "size": "42-46 універсал",
            "additional_sizes": [],
            "price": "1200",
            "color": "чорний",
        }

        product_raw_data = dc._build_product_raw_data(parsed)

        self.assertEqual(product_raw_data["category"], "shtany/bryuki")
        self.assertEqual(product_raw_data["size"], 833)
        self.assertEqual(product_raw_data["additional_sizes"], [834, 835])

    @patch("controller.data_controller._resolve_brand_id", return_value=None)
    @patch("controller.data_controller._parse_price", return_value=1200)
    @patch("controller.data_controller.find_slug_by_word", return_value=None)
    @patch("controller.data_controller._resolve_size_id")
    def test_build_product_raw_data_keeps_shoes_range_logic_untouched(
        self,
        resolve_size_id,
        _find_slug_by_word,
        _parse_price,
        _resolve_brand_id,
    ):
        resolve_size_id.side_effect = lambda value, catalog_slug=None, preferred_system=None: {
            "36": 171,
            "37": 172,
            "38": 173,
            "39": 174,
            "40": 175,
            "41": 176,
        }.get(str(value))
        parsed = {
            "word_for_slack": "кроссовки",
            "name": "Кроссовки",
            "description": "desc",
            "size": "36-41",
            "additional_sizes": [],
            "price": "1200",
            "color": "чорний",
        }

        product_raw_data = dc._build_product_raw_data(parsed)

        self.assertEqual(product_raw_data["category"], "zhenskaya-obuv/krossovki")
        self.assertEqual(product_raw_data["size"], 171)
        self.assertEqual(product_raw_data["additional_sizes"], [172, 173, 174, 175, 176])

    @patch("controller.data_controller.find_slug_by_word", return_value="sport-otdyh/sportivnyye-shtany")
    def test_parse_message_uses_step_two_for_clothes_ranges(self, _find_slug_by_word):
        parsed = dc.parse_message(
            "Штани\n"
            "Розмір: 42-46 універсал\n"
            "Ціна 450 грн"
        )

        self.assertEqual(parsed["size"], "42")
        self.assertEqual(parsed["additional_sizes"], ["44", "46"])

    def test_build_product_raw_data_uses_clothing_size_ids_for_sport_pants(self):
        parsed = {
            "word_for_slack": "штани",
            "name": "Штани",
            "description": "desc",
            "size": "42",
            "additional_sizes": ["44", "46"],
            "price": "450",
            "color": "чорний",
            "brand": None,
        }

        product_raw_data = dc.build_product_raw_data(parsed)

        self.assertEqual(product_raw_data["category"], "sport-otdyh/sportivnyye-shtany")
        self.assertEqual(product_raw_data["size"], 6)
        self.assertEqual(product_raw_data["additional_sizes"], [7, 8])

    def test_build_product_raw_data_uses_shoe_size_ids_for_default_sneakers(self):
        parsed = {
            "word_for_slack": "",
            "name": "Кроссовки",
            "description": "desc",
            "size": "42",
            "additional_sizes": ["43", "44"],
            "price": "1190",
            "color": "чорний",
            "brand": None,
        }

        product_raw_data = dc.build_product_raw_data(parsed)

        self.assertEqual(product_raw_data["category"], "obuv/krossovki")
        self.assertEqual(product_raw_data["size"], 177)
        self.assertEqual(product_raw_data["additional_sizes"], [178, 179])

    def test_database_confirms_clothes_and_shoes_have_different_size_ids(self):
        self.assertEqual(get_size_id_by_name("42", catalog_slug="obuv/krossovki"), 177)
        self.assertEqual(get_size_id_by_name("42", catalog_slug="zhenskaya-obuv/krossovki"), 39)
        self.assertEqual(dc._resolve_size_id("42", catalog_slug="sport-otdyh/sportivnyye-shtany"), 6)
