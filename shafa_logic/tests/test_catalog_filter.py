import _test_path

from controller.catalog_filter import find_slug_by_word, find_word


def test_find_slug_by_word_matches_blouse_keywords() -> None:
    assert find_slug_by_word("Женская блузка") == "rubashki-i-bluzy/bluzy"


def test_find_slug_by_word_matches_multilingual_keyword() -> None:
    assert find_slug_by_word("Light blouse with buttons") == "rubashki-i-bluzy/bluzy"


def test_find_word_prefers_exact_keyword_not_random_substring() -> None:
    assert find_word("Стильная блузка oversize") == "блузка"


def test_find_slug_by_word_prefers_earlier_keyword_when_scores_tie() -> None:
    assert (
        find_slug_by_word("Футболка-туніка з льону з подовженою спинкою")
        == "mayki-i-futbolki/futbolki"
    )


def test_find_word_prefers_earlier_keyword_when_scores_tie() -> None:
    assert find_word("Футболка-туніка з льону з подовженою спинкою") == "футболка"


def test_find_slug_by_word_matches_ukrainian_leggings_phrase() -> None:
    assert (
        find_slug_by_word("Ці легінси створені, щоб підкреслити твою форму")
        == "shtany/losiny-i-legginsy"
    )
