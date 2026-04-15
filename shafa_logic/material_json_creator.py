import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MATERIALS_TXT_PATH = BASE_DIR / "data" / "materials.txt"
MATERIALS_COMPACT_PATH = BASE_DIR / "data" / "materials_compact.json"


def create_materials_compact_json(
    source_path: Path = MATERIALS_TXT_PATH,
    output_path: Path = MATERIALS_COMPACT_PATH,
) -> dict[str, dict[str, list[str] | str]]:
    with source_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    materials: dict[str, dict[str, list[str] | str]] = {}
    for item in data:
        mat_id = str(item["id"])
        title = item["title"]
        slug = item["slug"]

        if mat_id not in materials:
            materials[mat_id] = {"title": title, "slugs": [slug]}
            continue

        slugs = materials[mat_id]["slugs"]
        if slug not in slugs:
            slugs.append(slug)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(materials, f, ensure_ascii=False, indent=2)

    return materials


def main() -> None:
    materials = create_materials_compact_json()
    print(
        f"Done! {len(materials)} unique ids saved to {MATERIALS_COMPACT_PATH}"
    )


if __name__ == "__main__":
    main()
