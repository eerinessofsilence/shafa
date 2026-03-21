import json

with open("materials.txt", "r", encoding="utf-8") as f:
    data = json.load(f)

materials = {}

for item in data:
    mat_id = item["id"]
    title = item["title"]
    slug = item["slug"]

    if mat_id not in materials:
        materials[mat_id] = {"title": title, "slugs": [slug]}
    else:
        # Добавляем только уникальные slugs для этого id
        if slug not in materials[mat_id]["slugs"]:
            materials[mat_id]["slugs"].append(slug)

# Сохраняем итоговый сокращённый JSON
with open("materials_compact.json", "w", encoding="utf-8") as f:
    json.dump(materials, f, ensure_ascii=False, indent=2)

print(f"Готово! {len(materials)} уникальных id сохранено в materials_compact.json")