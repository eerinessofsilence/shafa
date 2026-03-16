import unittest
from unittest.mock import patch, Mock
import json

from core.create_product import build_create_product_payload, create_product
from data.const import ORDINARY_CLOTHES_SIZES

class CreateProductPayloadTests(unittest.TestCase):
    def setUp(self):
        # Хардкодированные размеры
        ORDINARY_CLOTHES_SIZES.clear()
        ORDINARY_CLOTHES_SIZES.extend([833, 834])

        self.photo_ids = ["photo1", "photo2"]
        self.markup = 400
        self.product_raw_data = {
            "name": "Мод 462-43",
            "description": "Тестовое описание",
            "translation_enabled": True,
            "category": "verhnyaya-odezhda/palto",
            "condition": "new",
            "brand": "TestBrand",
            "colors": ["WHITE"],
            "size": None,
            "additional_sizes": [],
            "characteristics": [],
            "amount": 1,
            "selling_condition": "retail",
            "price": 530,
            "keywords": ["тест"],
        }

    def test_payload_contains_hardcoded_size(self):
        payload = build_create_product_payload(self.photo_ids, self.product_raw_data, self.markup)
        variables = payload["variables"]

        self.assertEqual(variables["nameUk"], self.product_raw_data["name"])
        self.assertEqual(variables["price"], self.product_raw_data["price"] + self.markup)
        self.assertEqual(variables["size"], 833)
        self.assertEqual(variables["additionalSizes"], [834])
        self.assertEqual(variables["photosStr"], self.photo_ids)

    @patch("core.create_product.BrowserContext")
    def test_create_product_mocked(self, mock_ctx_class):
        mock_ctx = mock_ctx_class.return_value
        mock_post = mock_ctx.request.post.return_value

        # resp.text должен быть callable, возвращаем строку JSON
        mock_post.text = lambda: '{"data": {"createProduct": {"id": 123}}}'
        mock_post.json = lambda: json.loads(mock_post.text())

        result = create_product(mock_ctx, "csrftoken", self.photo_ids, self.product_raw_data, self.markup)
        self.assertEqual(result["id"], 123)

if __name__ == "__main__":
    unittest.main()