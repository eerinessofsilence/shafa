import _test_path  # noqa: F401

from core.requests.deactivate_product import deactivate_product


def test_deactivate_product_is_disabled_noop() -> None:
    assert deactivate_product("208499836") is None
