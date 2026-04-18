import _test_path  # noqa: F401
from unittest.mock import patch

from data.db import get_size_id_by_name, size_id_exists


@patch("data.db._load_sizes_cache")
def test_get_size_id_by_name_does_not_fallback_to_global_mapping_for_catalog(
    load_sizes_cache,
):
    load_sizes_cache.return_value = (
        {"36": 171},
        {("obuv/krossovki", "36"): 171},
        {171},
        {"obuv/krossovki": {171}},
    )

    assert get_size_id_by_name("36", catalog_slug="zhenskaya-obuv/krossovki") is None


@patch("data.db._load_sizes_cache")
def test_size_id_exists_does_not_fallback_to_global_ids_for_catalog(load_sizes_cache):
    load_sizes_cache.return_value = (
        {"36": 171},
        {("obuv/krossovki", "36"): 171},
        {171},
        {"obuv/krossovki": {171}},
    )

    assert size_id_exists(171, catalog_slug="zhenskaya-obuv/krossovki") is False
