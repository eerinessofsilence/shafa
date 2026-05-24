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


def test_extract_name_prefers_clothing_title_over_promotional_header() -> None:
    lines = [
        "New collection❤️‍🔥",
        "Новинка❤️",
        "Реальні огляди😍",
        "Костюм 3-ка 🤩",
        "Мод. 045-119",
        "Кольори: вершкове масло, чорний, шоколад, айворі",
        "Тканина: сатин преміальної якості (Туреччина)",
        "Розмір: 42-44, 46-48",
        "Ціна: 1230 грн 🔥",
        "Сатиновий костюм, що виглядає дорого без зайвих зусиль✨",
    ]

    name, word_for_slack = dc.extract_name(lines)

    assert name == "Костюм 3-ка"
    assert word_for_slack == "костюм"


def test_extract_name_ignores_model_code_and_uses_clothing_sentence() -> None:
    parsed = dc.parse_message(
        "Новинка 💕\n"
        "Мод: 227-31\n"
        "Розмір: S(42); M(44);L(46)\n"
        "Тканина: костюмка , рукава шифон\n"
        "Ціна : 680 грн\n"
        "Ефектна міні сукня з шифоновими рукавами в білому та в чорному кольорі ! "
        "Бездоганно сідає по фігурі\n"
    )

    assert (
        parsed["name"]
        == "Ефектна міні сукня з шифоновими рукавами в білому та в чорному кольорі"
    )
    assert parsed["brand"] == ""


def test_extract_name_returns_empty_when_only_model_code_is_present() -> None:
    parsed = dc.parse_message(
        "Новинка\n"
        "Мод: 227-31\n"
        "Розмір: S M L\n"
        "Ціна: 680 грн\n"
    )

    assert parsed["name"] == ""


def test_extract_name_ignores_dense_size_details_line_for_shoes() -> None:
    parsed = dc.parse_message(
        "👉зниження ціни👉нова СУПЕр ціна 1650 грн⭐️чоловічі арт 11692\n"
        "Adidas Climacool Ventania темно сірі з чорним\n"
        "Виробник В'єтнам, якість ТОП\n"
        "Ціна на дроп - 1650 грн\n"
        "Верх текстиль/сітка, підошва піна\n"
        "Розміри 41-45\n"
        "41й(26см), 42й(26,5см), 43й(27,5см), 44й(28см), 45й(28,5см)\n"
    )

    assert parsed["name"] == "Adidas Climacool Ventania темно сірі з чорним"


def test_extract_name_rejects_generic_line_without_clothing_word_or_brand() -> None:
    parsed = dc.parse_message(
        "Новинка\n"
        "Дуже стильна модель у топовому кольорі\n"
        "Ціна: 1650 грн\n"
        "Розміри 41-45\n"
    )

    assert parsed["name"] == ""
