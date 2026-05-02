from data.const import DEFAULT_MARKUP, get_price_markup


def test_price_markup_uses_default_when_env_is_empty(monkeypatch):
    monkeypatch.delenv("SHAFA_PRICE_MARKUP", raising=False)

    assert get_price_markup(DEFAULT_MARKUP) == DEFAULT_MARKUP


def test_price_markup_uses_account_env_value(monkeypatch):
    monkeypatch.setenv("SHAFA_PRICE_MARKUP", "650")

    assert get_price_markup(DEFAULT_MARKUP) == 650


def test_price_markup_clamps_negative_env_value(monkeypatch):
    monkeypatch.setenv("SHAFA_PRICE_MARKUP", "-50")

    assert get_price_markup(DEFAULT_MARKUP) == 0
