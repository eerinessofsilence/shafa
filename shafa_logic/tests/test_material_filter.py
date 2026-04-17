import _test_path
import unittest

from controller.material_filter import MATERIALS_PATH, extract_fabric_ids_from_description


class MaterialFilterTests(unittest.TestCase):
    def test_materials_compact_json_exists(self):
        self.assertTrue(MATERIALS_PATH.exists())

    def test_extracts_exact_material_by_slug(self):
        description = "Тканина: Бавовна\nКолір: чорний"

        result = extract_fabric_ids_from_description(
            description,
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1822])

    def test_supports_material_label_variants(self):
        description = "Матеріал: Бавовна\nКолір: чорний"

        result = extract_fabric_ids_from_description(
            description,
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1822])

    def test_maps_russian_wool_to_vovna_for_slug(self):
        result = extract_fabric_ids_from_description(
            "Тканина: шерсть\n",
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1824])

    def test_maps_wool_adjective_to_vovna_for_slug(self):
        result = extract_fabric_ids_from_description(
            "Тканина: шерстяна\n",
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1824])

    def test_does_not_return_random_material_for_unknown_value(self):
        result = extract_fabric_ids_from_description(
            "Тканина: abc\n",
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [])

    def test_extracts_material_with_percentage_prefix(self):
        result = extract_fabric_ids_from_description(
            "Тканина: 100% бавовна\n",
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1822])

    def test_maps_russian_skin_variant(self):
        result = extract_fabric_ids_from_description(
            "Тканина: искусственная кожа\n",
            slug="verhnyaya-odezhda/palto",
        )

        self.assertEqual(result, [1811])
