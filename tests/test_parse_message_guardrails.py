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
