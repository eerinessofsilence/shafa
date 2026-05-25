import _test_path  # noqa: F401
from unittest.mock import patch

import controller.data_controller as dc


def _reset_brand_caches() -> None:
    dc._BRAND_PATTERNS = None
    dc._MASKED_BRAND_INDEX = None
    dc._MULTIWORD_MASKED_BRAND_INDEX = None


def test_fallback_brand_prefers_brand_like_token_in_clothing_name() -> None:
    assert dc._fallback_brand_from_name("Неймовірне пальто Zara oversize") == "Zara"


def test_parse_message_extracts_brand_for_clothing_name() -> None:
    _reset_brand_caches()
    try:
        with patch("controller.data_controller.list_brand_names", return_value=["Zara"]):
            parsed = dc.parse_message(
                "Неймовірне пальто Zara oversize\n"
                "Розмір: S M L\n"
                "Ціна: 1200 грн"
            )
    finally:
        _reset_brand_caches()

    assert parsed["brand"] == "Zara"


def test_parse_message_extracts_clothing_brand_from_promotional_line_without_brand_db() -> None:
    _reset_brand_caches()
    try:
        with patch("controller.data_controller.list_brand_names", return_value=[]):
            parsed = dc.parse_message(
                "Штани,Брюки\n"
                "Модель 1133\n"
                "Тканина: Костюмка\n"
                "Розміри: 42-44; 46-48; 50-52\n"
                "Кольори: чорний, шоколад\n"
                "Ціна 400 грн\n"
                "Хіт цього сезону ZARA\n"
            )
    finally:
        _reset_brand_caches()

    assert parsed["name"] == "Штани,Брюки"
    assert parsed["brand"] == "ZARA"


def test_parse_message_does_not_treat_made_in_line_as_brand() -> None:
    _reset_brand_caches()
    try:
        with patch("controller.data_controller.list_brand_names", return_value=[]):
            parsed = dc.parse_message(
                "Штани\n"
                "Made in Turkey\n"
                "Розмір: S M L\n"
                "Ціна: 500 грн\n"
            )
    finally:
        _reset_brand_caches()

    assert parsed["brand"] == ""


def test_parse_message_extracts_brand_from_leetspeak_token() -> None:
    _reset_brand_caches()
    try:
        with patch("controller.data_controller.list_brand_names", return_value=["Nike"]):
            parsed = dc.parse_message(
                "N1ke V2K Run\n"
                "Жіночі кросівки\n"
                "Розмір: 41\n"
                "Ціна: 3300 грн\n"
            )
    finally:
        _reset_brand_caches()

    assert parsed["brand"] == "Nike"


def test_parse_message_extracts_brand_from_common_masked_variants() -> None:
    _reset_brand_caches()
    try:
        with patch(
            "controller.data_controller.list_brand_names",
            return_value=["Nike", "Adidas", "Puma", "Reebok", "Gucci", "Balenciaga"],
        ):
            cases = [
                ("Ad1das Campus\nРозмір: 42\nЦіна: 2900 грн\n", "Adidas"),
                ("Puma! RS-X\nРозмір: 41\nЦіна: 2600 грн\n", "Puma"),
                ("N!ke V2K Run\nРозмір: 40\nЦіна: 3300 грн\n", "Nike"),
                ("N1k3 Vomero\nРозмір: 43\nЦіна: 3500 грн\n", "Nike"),
                ("PyMA Palermo\nРозмір: 39\nЦіна: 3100 грн\n", "Puma"),
                ("Re1bok Classic\nРозмір: 40\nЦіна: 2800 грн\n", "Reebok"),
                ("Gucc1 Marmont\nРозмір: 38\nЦіна: 7200 грн\n", "Gucci"),
                ("Balenc1aga Track\nРозмір: 41\nЦіна: 8900 грн\n", "Balenciaga"),
            ]
            for message, expected_brand in cases:
                parsed = dc.parse_message(message)
                assert parsed["brand"] == expected_brand
    finally:
        _reset_brand_caches()


def test_canonicalize_name_brand_replaces_leetspeak_brand_token() -> None:
    assert dc._canonicalize_name_brand("N1ke V2K Run", "Nike") == "Nike V2K Run"


def test_canonicalize_name_brand_replaces_common_masked_variants() -> None:
    cases = [
        ("Ad1das Campus", "Adidas", "Adidas Campus"),
        ("N!ke V2K Run", "Nike", "Nike V2K Run"),
        ("N1k3 Vomero", "Nike", "Nike Vomero"),
        ("PyMA Palermo", "Puma", "Puma Palermo"),
        ("Re1bok Classic", "Reebok", "Reebok Classic"),
        ("Gucc1 Marmont", "Gucci", "Gucci Marmont"),
        ("Balenc1aga Track", "Balenciaga", "Balenciaga Track"),
        ("New B4lance 530", "New Balance", "New Balance 530"),
    ]
    for name, brand, expected in cases:
        assert dc._canonicalize_name_brand(name, brand) == expected


def test_parse_message_normalizes_masked_brand_in_name() -> None:
    _reset_brand_caches()
    try:
        with patch(
            "controller.data_controller.list_brand_names",
            return_value=["Puma", "Reebok"],
        ):
            parsed = dc.parse_message(
                "PyMA Palermo\n"
                "Re1bok Classic\n"
                "Розмір: 39\n"
                "Ціна: 3100 грн\n"
            )
    finally:
        _reset_brand_caches()

    assert parsed["brand"] == "Puma"
    assert parsed["name"] == "Puma Palermo"


def test_parse_message_extracts_multiword_masked_brand() -> None:
    _reset_brand_caches()
    try:
        with patch(
            "controller.data_controller.list_brand_names",
            return_value=["New Balance"],
        ):
            parsed = dc.parse_message(
                "New B4lance 530\n"
                "Жіночі кросівки\n"
                "Розмір: 39\n"
                "Ціна: 3400 грн\n"
            )
    finally:
        _reset_brand_caches()

    assert parsed["brand"] == "New Balance"
    assert parsed["name"] == "New Balance 530"


@patch("controller.data_controller.find_slug_by_word", return_value="verhnyaya-odezhda/palto")
@patch("controller.data_controller.get_brand_id_by_name", return_value=321)
def test_build_product_raw_data_resolves_brand_for_clothing_catalog(
    _get_brand_id_by_name,
    _find_slug_by_word,
) -> None:
    product_raw_data = dc._build_product_raw_data(
        {
            "word_for_slack": "пальто",
            "name": "Пальто Zara",
            "description": "desc",
            "size": "",
            "additional_sizes": [],
            "price": "1200",
            "color": "чорний",
            "brand": "Zara",
        }
    )

    assert product_raw_data["brand"] == 321


@patch("controller.data_controller._build_product_raw_data", return_value={"brand": 321})
@patch("controller.data_controller.parse_message", return_value={"brand": "Zara"})
def test_rebuild_product_data_from_source_reparses_raw_message(
    parse_message,
    build_product_raw_data,
) -> None:
    parsed_data, product_raw_data = dc.rebuild_product_data_from_source(
        {
            "raw_message": "Неймовірне пальто Zara oversize",
            "parsed_data": {"brand": "oversize"},
        }
    )

    parse_message.assert_called_once_with("Неймовірне пальто Zara oversize")
    build_product_raw_data.assert_called_once_with({"brand": "Zara"})
    assert parsed_data == {"brand": "Zara"}
    assert product_raw_data == {"brand": 321}
