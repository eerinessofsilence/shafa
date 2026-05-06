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

<<<<<<< HEAD
<<<<<<< HEAD
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

        self.assertEqual(parsed["name"], "Жіночі кросівки Nike Air Force 1 pixel чорні")

    def test_keeps_human_article_name_details(self):
        parsed = dc.parse_message(
            "Арт XT6\n"
            "🔥Кросівки Salomon XT 6 білі (унісекс)🔥\n"
            "36-41\n"
            "1800"
        )

        self.assertEqual(parsed["name"], "Кросівки Salomon XT 6 білі (унісекс)")

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

    def test_prefers_brand_model_line_before_article_over_packaging_field(self):
        parsed = dc.parse_message(
            "📌🤎🤎🤎🤎🤎🤎🤎\n"
            "\n"
            "👕 Nike W Dunk Low Pink - Metallic Gold\n"
            "\n"
            "➖Дроп ціна: 2400 грн\n"
            "\n"
            "⏺Виробник: Вʼєтнам\n"
            "⏺Розміри: 36-41\n"
            "⏺Матеріал: шкіра, замша\n"
            "⏺Артикул: NK900\n"
            "⏺Пакування: брендова коробка та папір, додаткові шнурки, смаколики"
        )

        self.assertEqual(parsed["name"], "Nike W Dunk Low Pink - Metallic Gold")
        self.assertEqual(parsed["brand"], "Nike")
        self.assertEqual(parsed["price"], "2400")
        self.assertEqual(parsed["size"], "36")

    def test_falls_back_to_article_line_when_shirt_line_is_forbidden(self):
        parsed = dc.parse_message(
            "👕 Пакування: брендова коробка та папір\n"
            "Арт 1300\n"
            "🔥Жіночі кросівки Nike Air Force 1 pixel чорні 🔥\n"
            "37-41\n"
            "1600"
        )

        self.assertEqual(parsed["name"], "Жіночі кросівки Nike Air Force 1 pixel чорні")

    def test_does_not_use_arbitrary_line_without_allowed_source(self):
        parsed = dc.parse_message(
            "Nike W Dunk Low Pink - Metallic Gold\n"
            "Дроп ціна: 2400 грн\n"
            "Розміри: 36-41"
        )

        self.assertEqual(parsed["name"], "")

    def test_does_not_skip_past_invalid_article_next_line(self):
        parsed = dc.parse_message(
            "Арт NK900\n"
            "Пакування: брендова коробка та папір, смаколики\n"
            "Nike W Dunk Low Pink - Metallic Gold\n"
            "2400"
        )

=======
=======
>>>>>>> fb61016 (feat: delete async telegram sessions)
    def test_ignores_telegram_service_error_lines(self):
        parsed = dc.parse_message(
            "Куртка Nike Air\n"
            "Ціна: 1800 грн\n"
            "Розмір: M\n"
            "Не удалось получить обсуждение для сообщения: channel_id=-1001296785640\n"
            "Security error while unpacking a received message: "
            "Server replied with a wrong session ID (see FAQ for details)\n"
            "error=Server replied with a wrong session ID."
        )
        self.assertEqual(parsed["name"], "Куртка Nike Air")
        self.assertEqual(parsed["price"], "1800")
        self.assertEqual(parsed["size"], "M")

    def test_service_error_message_does_not_become_product_name(self):
        parsed = dc.parse_message(
            "Не удалось получить обсуждение для сообщения: channel_id=-1001296785640\n"
            "Security error while unpacking a received message: "
            "Server replied with a wrong session ID (see FAQ for details)"
        )
<<<<<<< HEAD
>>>>>>> fb61016 (feat: delete async telegram sessions)
=======
>>>>>>> fb61016 (feat: delete async telegram sessions)
        self.assertEqual(parsed["name"], "")
