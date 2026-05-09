import _test_path  # noqa: F401

import controller.data_controller as dc


def test_selected_name_rejects_price_line() -> None:
    assert dc._is_valid_selected_name("Ціна - 330 грн.") is False


def test_extract_name_skips_price_line_after_article_and_uses_clothing_title() -> None:
    lines = [
        "Арт: 1234",
        "Ціна - 330 грн.",
        "Футболка жіноча oversize",
        "Розмір: S M L",
    ]

    name, word_for_slack = dc.extract_name(lines)

    assert name == "Футболка жіноча oversize"
    assert word_for_slack == "футболка"


def test_extract_name_can_use_brand_model_line_for_shoes() -> None:
    lines = [
        "Арт: 7788",
        "Ціна - 330 грн.",
        "Nike V2K Run",
        "Жіночі кросівки",
        "Розмір 41",
    ]

    name, word_for_slack = dc.extract_name(lines)

    assert name == "Nike V2K Run"
    assert word_for_slack == ""
