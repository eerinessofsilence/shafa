import _test_path  # noqa: F401
from unittest.mock import patch

import controller.data_controller as dc
from data.size_mapping import (
    SIZE_SYSTEM_INTERNATIONAL,
    build_size_mappings,
    flatten_v5_size_groups,
    normalize_size_text,
)


def _palto_alias_row() -> dict:
    return {
        "id_v3": 3,
        "international": "S",
        "eu": "36",
        "ua": "44",
        "id_v5_international": 833,
        "id_v5_eu": 814,
        "id_v5_ua": 781,
    }


def _palto_eu_44_row() -> dict:
    return {
        "id_v3": 7,
        "international": "XXL",
        "eu": "44",
        "ua": "52",
        "id_v5_international": 837,
        "id_v5_eu": 818,
        "id_v5_ua": 785,
    }


def _dress_xs_s_row() -> dict:
    return {
        "id_v3": None,
        "international": "XS-S",
        "eu": None,
        "ua": None,
        "id_v5_international": 867,
        "id_v5_eu": None,
        "id_v5_ua": None,
    }


def _dress_m_l_row() -> dict:
    return {
        "id_v3": None,
        "international": "M-L",
        "eu": None,
        "ua": None,
        "id_v5_international": 869,
        "id_v5_eu": None,
        "id_v5_ua": None,
    }


def test_build_size_mappings_pairs_v3_alias_rows_with_v5_ids():
    v3_sizes = [
        {"id": 3, "primarySizeName": "36", "secondarySizeName": "S/44"},
    ]
    v5_size_groups = [
        {
            "name": "Міжнародний",
            "sizes": [
                {"id": "833", "primarySizeName": "S"},
                {"id": "845", "primarySizeName": "One size"},
            ],
        },
        {
            "name": "Європейський",
            "sizes": [
                {"id": "814", "primarySizeName": "36"},
                {"id": "830", "primarySizeName": "One size"},
            ],
        },
        {
            "name": "🇺🇦 Український",
            "sizes": [
                {"id": "781", "primarySizeName": "44"},
                {"id": "810", "primarySizeName": "One size"},
            ],
        },
    ]

    mappings = build_size_mappings(v3_sizes, v5_size_groups)

    assert mappings[0] == _palto_alias_row()
    assert {
        "id_v3": None,
        "international": "ONE SIZE",
        "eu": "ONE SIZE",
        "ua": "ONE SIZE",
        "id_v5_international": 845,
        "id_v5_eu": 830,
        "id_v5_ua": 810,
    } in mappings


def test_flatten_v5_size_groups_normalizes_cyrillic_x_sizes():
    v5_size_groups = [
        {
            "name": "Міжнародний",
            "sizes": [
                {"id": "832", "primarySizeName": "ХS"},
                {"id": "829", "primarySizeName": "XХS"},
            ],
        }
    ]

    sizes = flatten_v5_size_groups(v5_size_groups)

    assert sizes == [
        {
            "id": 832,
            "primarySizeName": "XS",
            "secondarySizeName": None,
            "sizeSystem": "international",
            "__typename": "SizeType",
        },
        {
            "id": 829,
            "primarySizeName": "XXS",
            "secondarySizeName": None,
            "sizeSystem": "international",
            "__typename": "SizeType",
        },
    ]


def test_normalize_size_text_normalizes_adjacent_alpha_slash_range():
    assert normalize_size_text("Xs/S") == "XS-S"
    assert normalize_size_text("M/L") == "M-L"


@patch("controller.data_controller.get_size_id_by_name", return_value=None)
def test_resolve_size_id_prefers_alias_from_same_target_system(_get_size_id_by_name):
    row_s = _palto_alias_row()
    row_eu_44 = _palto_eu_44_row()

    with patch(
        "controller.data_controller.find_size_mapping_candidates",
        return_value=[
            {"matched_system": "ua", "matched_id": 781, "row": row_s},
            {"matched_system": "eu", "matched_id": 818, "row": row_eu_44},
        ],
    ):
        resolved = dc._resolve_size_id(
            "44",
            catalog_slug="verhnyaya-odezhda/palto",
            preferred_system=SIZE_SYSTEM_INTERNATIONAL,
        )

    assert resolved == 833


@patch("controller.data_controller.find_slug_by_word", return_value="verhnyaya-odezhda/palto")
@patch("controller.data_controller.get_size_id_by_name", return_value=None)
def test_build_product_raw_data_deduplicates_cross_system_aliases(
    _get_size_id_by_name,
    _find_slug_by_word,
):
    row_s = _palto_alias_row()
    row_eu_44 = _palto_eu_44_row()

    def fake_candidates(value, catalog_slug=None):
        if value == "S":
            return [
                {
                    "matched_system": "international",
                    "matched_id": 833,
                    "row": row_s,
                }
            ]
        if value == "44":
            return [
                {"matched_system": "ua", "matched_id": 781, "row": row_s},
                {"matched_system": "eu", "matched_id": 818, "row": row_eu_44},
            ]
        return []

    parsed = {
        "word_for_slack": "пальто",
        "name": "Пальто",
        "description": "desc",
        "size": "S",
        "additional_sizes": ["44"],
        "price": "1200",
        "color": "білий",
        "brand": None,
    }

    with patch(
        "controller.data_controller.find_size_mapping_candidates",
        side_effect=fake_candidates,
    ):
        product_raw_data = dc._build_product_raw_data(parsed)

    assert product_raw_data["size"] == 833
    assert "additional_sizes" not in product_raw_data


@patch("controller.data_controller.find_slug_by_word", return_value="platya/maksi")
def test_parse_message_keeps_clothing_alpha_ranges(_find_slug_by_word):
    parsed = dc.parse_message(
        "Сукня\n"
        "Розмір: Xs/S M/L\n"
        "Ціна 530 грн"
    )

    assert parsed["size"] == "XS-S"
    assert parsed["additional_sizes"] == ["M-L"]


@patch("controller.data_controller.get_size_id_by_name", return_value=None)
@patch("controller.data_controller.find_slug_by_word", return_value="platya/maksi")
def test_build_product_raw_data_uses_combined_clothing_range_ids(
    _find_slug_by_word,
    _get_size_id_by_name,
):
    xs_s_row = _dress_xs_s_row()
    m_l_row = _dress_m_l_row()

    def fake_candidates(value, catalog_slug=None):
        if value == "XS-S":
            return [
                {
                    "matched_system": "international",
                    "matched_id": 867,
                    "row": xs_s_row,
                }
            ]
        if value == "M-L":
            return [
                {
                    "matched_system": "international",
                    "matched_id": 869,
                    "row": m_l_row,
                }
            ]
        return []

    parsed = {
        "word_for_slack": "сукня",
        "name": "Сукня",
        "description": "desc",
        "size": "XS-S",
        "additional_sizes": ["M-L"],
        "price": "530",
        "color": "чорний",
        "brand": None,
    }

    with patch(
        "controller.data_controller.find_size_mapping_candidates",
        side_effect=fake_candidates,
    ):
        product_raw_data = dc._build_product_raw_data(parsed)

    assert product_raw_data["size"] == 867
    assert product_raw_data["additional_sizes"] == [869]
