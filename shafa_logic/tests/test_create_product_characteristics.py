import _test_path  # noqa: F401
import unittest

from core.no_playwright import _build_create_product_payload
from core.requests.create_product import build_create_product_payload
from models.product import (
    DEMISEASON_CHARACTERISTIC_ID,
    HANDMADE_CHARACTERISTIC_ID,
)


def _base_product_raw_data(**overrides) -> dict:
    data = {
        "name": "Пальто",
        "description": "Описание",
        "category": "verhnyaya-odezhda/palto",
        "brand": 17,
        "size": 42,
        "price": 1500,
        "colors": ["BLACK"],
    }
    data.update(overrides)
    return data


class CreateProductCharacteristicsTests(unittest.TestCase):
    def test_playwright_payload_for_branded_clothing_excludes_handmade(self):
        payload = build_create_product_payload(
            ["photo-1"],
            _base_product_raw_data(),
            100,
        )

        self.assertEqual(
            payload["variables"]["characteristics"],
            [DEMISEASON_CHARACTERISTIC_ID],
        )

    def test_playwright_payload_for_clothing_without_brand_includes_handmade(self):
        payload = build_create_product_payload(
            ["photo-1"],
            _base_product_raw_data(brand=None),
            100,
        )

        self.assertEqual(
            payload["variables"]["characteristics"],
            [
                DEMISEASON_CHARACTERISTIC_ID,
                HANDMADE_CHARACTERISTIC_ID,
            ],
        )

    def test_no_playwright_payload_strips_handmade_for_non_clothing(self):
        payload = _build_create_product_payload(
            ["photo-1"],
            _base_product_raw_data(
                category="obuv/krossovki",
                characteristics=[HANDMADE_CHARACTERISTIC_ID, 555],
            ),
            100,
        )

        self.assertEqual(
            payload["variables"]["characteristics"],
            [555, DEMISEASON_CHARACTERISTIC_ID],
        )
