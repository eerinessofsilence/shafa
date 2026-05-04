import _test_path
import unittest

import controller.data_controller as dc


class ParseMessageGuardrailsTests(unittest.TestCase):
    def test_does_not_extract_price_or_size_from_model_codes(self):
        parsed = dc.parse_message("Puma 180 Grey White\nPM035")
        self.assertEqual(parsed["price"], "")
        self.assertEqual(parsed["size"], "")

    def test_extracts_price_from_numeric_only_line(self):
        parsed = dc.parse_message("Puma 180 Grey White\n1600")
        self.assertEqual(parsed["price"], "1600")

    def test_extracts_name_from_line_after_article_only(self):
        parsed = dc.parse_message(
            "Новинка\n"
            "Арт 1300\n"
            "🔥Жіночі кросівки Nike Air Force 1 pixel чорні 🔥\n"
            "37-41\n"
            "(32 пари)\n"
            "16 пар\n"
            "1600"
        )

        self.assertEqual(parsed["name"], "Nike Air Force 1 Pixel")

    def test_removes_parenthesized_unisex_and_color_from_article_name(self):
        parsed = dc.parse_message(
            "Арт XT6\n"
            "🔥Кросівки Salomon XT 6 білі (унісекс)🔥\n"
            "36-41\n"
            "1800"
        )

        self.assertEqual(parsed["name"], "Salomon XT 6")

    def test_rejects_size_range_after_article_as_name(self):
        parsed = dc.parse_message(
            "Арт 1301\n"
            "37-41\n"
            "🔥Жіночі кросівки Nike Air Force 1 pixel чорні 🔥\n"
            "1600"
        )

        self.assertEqual(parsed["name"], "")

    def test_rejects_pair_count_after_article_as_name(self):
        for garbage in ("(32 пари)", "16 пар"):
            with self.subTest(garbage=garbage):
                parsed = dc.parse_message(
                    "Арт 1302\n"
                    f"{garbage}\n"
                    "Nike Air Force 1\n"
                    "1600"
                )

                self.assertEqual(parsed["name"], "")
